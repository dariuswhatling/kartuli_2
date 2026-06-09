"""Ingestion pipeline: PDF -> text -> categorised chunks -> embeddings."""
from __future__ import annotations

import json
import logging
import re

from pypdf import PdfReader

from accounts.models import get_user_settings
from core import embeddings, openrouter

from .models import Chunk, Lesson

logger = logging.getLogger(__name__)

# Roughly how much text to hand the parser model per request.
PARSE_WINDOW_CHARS = 14000

PARSE_SYSTEM_PROMPT = (
    "You are an expert Georgian (Kartuli) language teaching assistant. "
    "You receive raw text extracted from a student's lesson document. "
    "Break it into small, self-contained study chunks and categorise each. "
    "Return STRICT JSON only, no prose, no markdown fences."
)

PARSE_USER_TEMPLATE = """Split the following lesson text into study chunks.

For EACH chunk return an object with:
- "text": the chunk content, kept verbatim (preserve Georgian script).
- "section": short label for what kind of content it is (e.g. "vocabulary", "verb conjugation", "dialogue", "grammar note", "exercise").
- "topics": array of lowercase tags from this set when relevant: ["alphabet","vocabulary","verbs","nouns","adjectives","cases","tenses","pronouns","numbers","phrases","grammar","dialogue","pronunciation","exercise"]. Add others if clearly needed.
- "grammar_points": array of short strings describing any grammar rules present (may be empty).
- "vocab": array of {{"ka": "...", "translit": "...", "en": "..."}} for vocabulary items present (may be empty).

Return STRICT JSON: {{"chunks": [ ... ]}}

LESSON TEXT:
\"\"\"
{text}
\"\"\"
"""

SUMMARY_TEMPLATE = """Summarise this Georgian lesson in 2-3 sentences and list its main topics.
Return STRICT JSON: {{"summary": "...", "topics": ["...", ...]}}

LESSON TEXT (may be truncated):
\"\"\"
{text}
\"\"\"
"""


def extract_text(file_obj) -> str:
    reader = PdfReader(file_obj)
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            continue
    return "\n\n".join(parts).strip()


def _parse_json(raw: str) -> dict:
    """Best-effort JSON extraction from a model response."""
    raw = raw.strip()
    # Strip ```json ... ``` fences if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {}


def _windows(text: str, size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # Try to break on a paragraph boundary for cleaner splits.
        if end < len(text):
            boundary = text.rfind("\n\n", start, end)
            if boundary > start + size // 2:
                end = boundary
        chunks.append(text[start:end])
        start = end
    return chunks


def _categorise(model: str, text: str) -> list[dict]:
    prompt = PARSE_USER_TEMPLATE.format(text=text)
    response = openrouter.chat(
        model,
        [
            {"role": "system", "content": PARSE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=4000,
    )
    data = _parse_json(response)
    chunks = data.get("chunks", [])
    return chunks if isinstance(chunks, list) else []


def _summarise(model: str, text: str) -> dict:
    prompt = SUMMARY_TEMPLATE.format(text=text[:PARSE_WINDOW_CHARS])
    response = openrouter.chat(
        model,
        [{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=600,
    )
    return _parse_json(response)


def process_lesson(lesson: Lesson) -> None:
    """Run the full ingestion pipeline for an uploaded lesson."""
    lesson.status = Lesson.Status.PROCESSING
    lesson.error = ""
    lesson.save(update_fields=["status", "error"])

    try:
        if not lesson.raw_text and lesson.file:
            lesson.file.open("rb")
            try:
                lesson.raw_text = extract_text(lesson.file)
            finally:
                lesson.file.close()
            lesson.save(update_fields=["raw_text"])

        if not lesson.raw_text.strip():
            raise ValueError(
                "No extractable text found in this PDF. It may be a scanned "
                "image; OCR is not enabled."
            )

        user_settings = get_user_settings(lesson.user)
        parser_model = user_settings.parser_model

        # Categorise into chunks, window by window.
        raw_chunks: list[dict] = []
        for window in _windows(lesson.raw_text, PARSE_WINDOW_CHARS):
            raw_chunks.extend(_categorise(parser_model, window))

        if not raw_chunks:
            # Fallback: store the raw text as a single chunk so search still works.
            raw_chunks = [{"text": lesson.raw_text, "section": "", "topics": []}]

        # Summary + lesson-level topics.
        meta = _summarise(parser_model, lesson.raw_text)
        lesson.summary = (meta.get("summary") or "")[:2000]
        lesson_topics = meta.get("topics") or []

        # Embed all chunk texts in one batch.
        texts = [str(c.get("text", "")).strip() for c in raw_chunks]
        texts = [t for t in texts if t]
        vectors = embeddings.embed_texts(texts)

        lesson.chunks.all().delete()
        seen_topics: set[str] = set(lesson_topics)
        vi = 0
        for order, c in enumerate(raw_chunks):
            text = str(c.get("text", "")).strip()
            if not text:
                continue
            topics = c.get("topics") or []
            if isinstance(topics, list):
                seen_topics.update(str(t).lower() for t in topics)
            Chunk.objects.create(
                lesson=lesson,
                user=lesson.user,
                order=order,
                text=text,
                topics=topics if isinstance(topics, list) else [],
                section=str(c.get("section", ""))[:200],
                grammar_points=c.get("grammar_points") or [],
                vocab=c.get("vocab") or [],
                embedding=vectors[vi] if vi < len(vectors) else [],
            )
            vi += 1

        lesson.topics = sorted(t for t in seen_topics if t)
        lesson.status = Lesson.Status.READY
        lesson.save(update_fields=["summary", "topics", "status"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Lesson processing failed for %s", lesson.pk)
        lesson.status = Lesson.Status.FAILED
        lesson.error = str(exc)[:2000]
        lesson.save(update_fields=["status", "error"])
