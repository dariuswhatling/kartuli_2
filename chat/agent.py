"""Tutoring agent: scope -> retrieve lesson chunks -> reply using Mem0 memory."""
from __future__ import annotations

import logging

from accounts.models import get_user_settings
from core import memory, openrouter
from core.json_utils import parse_json
from core.openrouter import OpenRouterError

from .models import Conversation, Message
from .retrieval import retrieve_chunks
from .widgets import WIDGET_TOOLS, _normalize_widget, parse_reply, widgets_from_tool_calls

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

TOOL_GUIDE = """
INTERACTIVE TOOLS — you MUST use these when quizzing, reviewing, or when the student asks
to be tested ("quiz me", "multiple choice", "flashcard", "test me", etc.).

Call one or two tool functions to show interactive cards in the chat UI:
- show_mcq — multiple choice (tap an option)
- show_true_false — true/false statement
- show_translate_pick — Georgian word/phrase, pick English translation
- show_flashcard — tap to reveal, then self-grade
- show_fill_blank — sentence with blank, pick the word
- show_conjugate — pick the correct verb form
- show_self_rating — confidence rating 1–5 after teaching

Rules:
- When testing, ALWAYS call at least one tool. Plain-text quizzes are not allowed.
- Put at most 1–2 tools per turn (one question at a time).
- All quiz content MUST come from LESSON CONTEXT below.
- Write brief instructional prose in your message AND call the tool(s).
- Never reveal correct answers in prose — only in tool arguments.
- After the student answers via a widget, continue the lesson; do not ask what they want next.
"""

TUTOR_SYSTEM = """You are a professional Georgian (Kartuli) language tutor in an ongoing
one-on-one lesson. Your job is to keep teaching, drilling, and checking understanding
continuously — as a skilled classroom tutor would, not as a chatbot waiting for instructions.

TEACHING STYLE:
- Direct, economical language. No filler, flattery, or cheerleading ("Great job!", "You're
  doing amazing!", "I'm so proud of you", etc.). Acknowledge errors plainly and move on.
- Never end with open questions like "What would you like to do next?", "Shall we continue?",
  or "Would you like to…". YOU decide the next step and state it.
- After every exchange, proactively continue: explain the next point, drill the next item,
  revisit a weak area, or launch the next question. The lesson does not pause for direction.
- Tone: patient and clear, like teaching a focused student — professional, not sentimental.
- Keep Georgian script accurate. Add transliteration when it aids learning.

HARD RULES:
- Use ONLY the lesson context below. Never quiz on material outside it. If scope has no
  context, say so briefly and direct them to upload a lesson via Settings.
- When testing or reviewing, you MUST call the interactive tools described below.
- Use what you remember about THIS student to prioritise weak areas and skip mastered
  material — unless they narrowed the scope.
{tool_guide}
SESSION SCOPE: mode={mode}; lessons={lesson_scope}; topics={topic_scope}

WHAT YOU REMEMBER ABOUT THIS STUDENT (from past sessions — adapt using this):
{memories}

LESSON CONTEXT (the only material you may use):
{context}
"""

WIDGET_SYNTH_PROMPT = """You build ONE interactive tutoring widget for a Georgian lesson.

Student said:
\"\"\"{student}\"\"\"

Tutor is about to show:
\"\"\"{assistant}\"\"\"

Session mode: {mode}
Lesson context:
{context}

Return STRICT JSON with a single widget object. Pick the best type for this moment.
Supported types and fields:

mcq: {{"type":"mcq","prompt":"...","options":["..."],"answer":0,"explanation":"..."}}
true_false: {{"type":"true_false","statement":"...","answer":true,"explanation":"..."}}
translate_pick: {{"type":"translate_pick","georgian":"...","translit":"...","options":["..."],"answer":0,"explanation":"..."}}
flashcard: {{"type":"flashcard","front":"...","back":"...","hint":"..."}}
fill_blank: {{"type":"fill_blank","before":"...","after":"...","options":["..."],"answer":0,"explanation":"..."}}
conjugate: {{"type":"conjugate","verb":"...","tense":"...","subject":"...","options":["..."],"answer":0,"explanation":"..."}}
self_rating: {{"type":"self_rating","prompt":"...","scale":5}}

Content MUST come from the lesson context. "answer" is 0-based index into "options".
Return: {{"widget": {{ ... }} }}
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


def _wants_interactive(message: str, scope: dict) -> bool:
    if scope.get("mode") in {"quiz", "review"}:
        return True
    lowered = message.lower()
    triggers = (
        "quiz",
        "test me",
        "multiple choice",
        "flashcard",
        "flash card",
        "mcq",
        "drill",
        "practice",
        "true or false",
        "true/false",
    )
    return any(t in lowered for t in triggers)


def _run_tutor(
    model: str,
    messages: list[dict],
    *,
    force_tools: bool,
) -> tuple[str, list[dict]]:
    """Call the tutor model; prefer tool calls for widgets."""
    tool_choice = "required" if force_tools else "auto"
    try:
        result = openrouter.chat_completion(
            model,
            messages,
            temperature=0.5,
            max_tokens=1400,
            tools=WIDGET_TOOLS,
            tool_choice=tool_choice,
        )
        widgets = widgets_from_tool_calls(result.tool_calls)
        display = result.content
        if not widgets and display:
            display, md_widgets = parse_reply(display)
            widgets = md_widgets
        return display.strip(), widgets
    except OpenRouterError as exc:
        logger.warning("Tool-calling tutor failed, falling back to text: %s", exc)

    reply_text = openrouter.chat(model, messages, temperature=0.5, max_tokens=1400)
    return parse_reply(reply_text)


def _synthesize_widget(
    *,
    model: str,
    student_message: str,
    assistant_text: str,
    scope: dict,
    context: str,
) -> list[dict]:
    """Dedicated widget agent when the main tutor did not emit tools."""
    try:
        raw = openrouter.chat(
            model,
            [
                {
                    "role": "user",
                    "content": WIDGET_SYNTH_PROMPT.format(
                        student=student_message[:1500],
                        assistant=assistant_text[:1500] or "(widget only — no prose)",
                        mode=scope["mode"],
                        context=context[:6000],
                    ),
                }
            ],
            temperature=0.2,
            max_tokens=700,
        )
        data = parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Widget synthesis failed: %s", exc)
        return []

    widget = data.get("widget")
    if not isinstance(widget, dict):
        return []
    normalized = _normalize_widget(widget)
    return [normalized] if normalized else []


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
    context = _context_block(chunks)

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
        tool_guide=TOOL_GUIDE,
        memories=_format_memories(memories),
        context=context,
    )

    messages = [{"role": "system", "content": system}]
    messages.extend(_history_messages(conversation))
    messages.append({"role": "user", "content": user_message})

    force_tools = _wants_interactive(user_message, scope)
    display_text, widgets = _run_tutor(model, messages, force_tools=force_tools)

    if not widgets and force_tools and chunks:
        widgets = _synthesize_widget(
            model=model,
            student_message=user_message,
            assistant_text=display_text,
            scope=scope,
            context=context,
        )

    assistant_msg = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=display_text,
        metadata={"scope": scope, "widgets": widgets},
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
