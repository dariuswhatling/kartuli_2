"""Tutoring agent: scope -> retrieve lesson chunks -> reply using Mem0 memory."""
from __future__ import annotations

import logging

from accounts.models import get_user_settings
from core import memory, openrouter
from core.json_utils import parse_json

from .models import Conversation, Message
from .retrieval import retrieve_chunks

logger = logging.getLogger(__name__)

MAX_HISTORY = 12

SCOPE_PROMPT = """You route a Georgian (Kartuli) language tutoring request.

The student said:
\"\"\"{message}\"\"\"

Their available lessons (id: title -> topics):
{lessons}

Decide:
- "mode": one of "quiz" (test me), "explain" (teach/explain), "review" (go over), or "chat".
- "lesson_ids": array of lesson ids the request is scoped to. EMPTY array means all lessons.
- "topics": array of topic tags to focus on (e.g. ["verbs"]). EMPTY means any.

Only include a lesson id if the student clearly referred to it (by number, title, or content).
Return STRICT JSON: {{"mode": "...", "lesson_ids": [], "topics": []}}
"""

TUTOR_SYSTEM = """You are a focused, encouraging Georgian (Kartuli) language tutor.

HARD RULES:
- Use ONLY the lesson context provided below. Never test or quiz the student on
  material that is not in the context. If the requested scope has no context,
  say so and ask them to upload or pick a relevant lesson.
- When in quiz mode, ask ONE clear question at a time, then wait for the answer.
- When the student answers, mark it (correct / partly / incorrect), give the
  correct answer briefly, then continue.
- Adapt like an in-person tutor: use what you remember about THIS student below.
  Return to their weak spots, skip what they clearly know, notice patterns in
  their mistakes — unless they asked for a specific narrow scope.
- Keep Georgian script accurate. Offer transliteration when helpful.
- Be concise and warm.

SESSION SCOPE: mode={mode}; lessons={lesson_scope}; topics={topic_scope}

WHAT YOU REMEMBER ABOUT THIS STUDENT (from past sessions — adapt using this):
{memories}

LESSON CONTEXT (the only material you may use):
{context}
"""

MEMORY_EXTRACT_PROMPT = """You help a Georgian language tutor remember their student over time,
the way a human tutor would after a lesson.

Previous tutor message:
\"\"\"{assistant}\"\"\"

Student's latest message:
\"\"\"{student}\"\"\"

Session scope: mode={mode}; lessons={lessons}; topics={topics}

Write 0–3 short memory facts worth keeping for FUTURE sessions. Good memories are
specific and natural, e.g.:
- "Struggles with -ება verb endings in lesson 3 conjugation tables"
- "Confuses dative and genitive cases after ზე and ში"
- "Strong with basic greetings and numbers"
- "Prefers romanization alongside Georgian script"
- "Answered correctly on present-tense dialogue from lesson 2"

Only record real evidence from this exchange (answers, mistakes, things they said
about what they find hard). Skip filler ("thanks", "ok", "continue").

Return STRICT JSON: {{"memories": ["...", ...]}}
"""


def _lessons_block(user) -> str:
    from lessons.models import Lesson

    rows = []
    for lesson in Lesson.objects.filter(user=user, status=Lesson.Status.READY):
        topics = ", ".join(lesson.topics or []) or "?"
        rows.append(f"{lesson.id}: {lesson.title} -> {topics}")
    return "\n".join(rows) if rows else "(no lessons uploaded yet)"


def extract_scope(user, message: str, model: str) -> dict:
    lessons = _lessons_block(user)
    try:
        raw = openrouter.chat(
            model,
            [{"role": "user", "content": SCOPE_PROMPT.format(message=message, lessons=lessons)}],
            temperature=0.0,
            max_tokens=300,
        )
        data = parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scope extraction failed: %s", exc)
        data = {}
    mode = data.get("mode") if data.get("mode") in {"quiz", "explain", "review", "chat"} else "chat"
    lesson_ids = [int(x) for x in data.get("lesson_ids", []) if str(x).isdigit()]
    topics = [str(t).lower() for t in data.get("topics", []) if t]
    return {"mode": mode, "lesson_ids": lesson_ids, "topics": topics}


def _context_block(chunks) -> str:
    if not chunks:
        return "(no matching lesson content for this scope)"
    parts = []
    for c in chunks:
        head = f"[Lesson: {c.lesson.title}"
        if c.section:
            head += f" / {c.section}"
        head += "]"
        parts.append(f"{head}\n{c.text}")
    return "\n\n---\n\n".join(parts)


def _history_messages(conversation: Conversation) -> list[dict]:
    msgs = conversation.messages.order_by("-created_at")[:MAX_HISTORY]
    ordered = list(reversed(list(msgs)))
    return [{"role": m.role, "content": m.content} for m in ordered]


def _format_memories(memories: list[str]) -> str:
    if not memories:
        return "(no memories yet — this may be a new student, or Mem0 is not configured)"
    return "\n".join(f"- {m}" for m in memories)


def generate_reply(conversation: Conversation, user_message: str) -> Message:
    user = conversation.user
    settings_obj = get_user_settings(user)
    model = settings_obj.chat_model

    scope = extract_scope(user, user_message, model)
    chunks = retrieve_chunks(
        user,
        user_message,
        lesson_ids=scope["lesson_ids"] or None,
        topics=scope["topics"] or None,
        limit=6,
    )

    memories = memory.recall_for_tutoring(
        user.id,
        user_message,
        lesson_ids=scope["lesson_ids"] or None,
        topics=scope["topics"] or None,
        mode=scope["mode"],
    )

    lesson_scope = scope["lesson_ids"] or "all"
    topic_scope = scope["topics"] or "any"
    system = TUTOR_SYSTEM.format(
        mode=scope["mode"],
        lesson_scope=lesson_scope,
        topic_scope=topic_scope,
        memories=_format_memories(memories),
        context=_context_block(chunks),
    )

    messages = [{"role": "system", "content": system}]
    messages.extend(_history_messages(conversation))
    messages.append({"role": "user", "content": user_message})

    reply_text = openrouter.chat(model, messages, temperature=0.5, max_tokens=1200)

    assistant_msg = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=reply_text,
        metadata={"scope": scope},
    )
    conversation.save(update_fields=["updated_at"])

    _learn_from_exchange(conversation, user_message, scope, model)
    return assistant_msg


def _previous_assistant_message(conversation: Conversation) -> str:
    prev = (
        conversation.messages.filter(role=Message.Role.ASSISTANT)
        .order_by("-created_at")[1:2]
        .first()
    )
    return prev.content if prev else ""


def _learn_from_exchange(conversation, user_message, scope, model) -> None:
    """Extract tutor memories from the latest student turn and store in Mem0."""
    prior = _previous_assistant_message(conversation)
    if not prior:
        return
    try:
        raw = openrouter.chat(
            model,
            [
                {
                    "role": "user",
                    "content": MEMORY_EXTRACT_PROMPT.format(
                        assistant=prior[:2000],
                        student=user_message[:2000],
                        mode=scope["mode"],
                        lessons=scope["lesson_ids"] or "all",
                        topics=", ".join(scope["topics"]) or "any",
                    ),
                }
            ],
            temperature=0.1,
            max_tokens=400,
        )
        data = parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Memory extraction failed: %s", exc)
        return

    items = data.get("memories") or []
    if not isinstance(items, list):
        return

    meta = {
        "mode": scope["mode"],
        "lesson_ids": scope["lesson_ids"],
        "topics": scope["topics"],
    }
    memory.remember_many(
        conversation.user.id,
        [str(m).strip() for m in items if str(m).strip()],
        metadata=meta,
    )
