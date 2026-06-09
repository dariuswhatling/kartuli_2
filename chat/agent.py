"""Tutoring agent: scope -> retrieve -> reply -> assess -> adapt."""
from __future__ import annotations

import logging

from accounts.models import get_user_settings
from core import memory, openrouter
from core.json_utils import parse_json

from .models import Attempt, Conversation, Message, Skill
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
- Adapt to the student's mastery: spend more time on weak areas, less on strong
  ones, unless the student asked for a specific scope.
- Keep Georgian script accurate. Offer transliteration when helpful.
- Be concise and warm.

SESSION SCOPE: mode={mode}; lessons={lesson_scope}; topics={topic_scope}

WHAT THE STUDENT IS GOOD/BAD AT:
{mastery}

THINGS TO REMEMBER ABOUT THIS STUDENT:
{memories}

LESSON CONTEXT (the only material you may use):
{context}
"""

ASSESS_PROMPT = """You are grading a Georgian tutoring exchange to track progress.

Assistant's previous message (may contain a question):
\"\"\"{assistant}\"\"\"

Student's reply:
\"\"\"{student}\"\"\"

Lesson topics in scope: {topics}

If the student's reply was an ANSWER to a question, assess it. Otherwise set assessed=false.
Return STRICT JSON:
{{"assessed": true/false, "topic": "single lowercase topic tag", "lesson_id": null or int,
  "correctness": 0.0 to 1.0, "note": "one short sentence on what they got right/wrong"}}
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


def _mastery_summary(user, lesson_ids: list[int] | None, topics: list[str] | None) -> str:
    qs = Skill.objects.filter(user=user)
    if lesson_ids:
        qs = qs.filter(lesson_id__in=lesson_ids)
    if topics:
        qs = qs.filter(topic__in=topics)
    qs = qs.order_by("score")[:12]
    if not qs:
        return "(no quiz history yet)"
    lines = []
    for s in qs:
        level = "weak" if s.score < 0.4 else "ok" if s.score < 0.7 else "strong"
        scope = s.lesson.title if s.lesson else "all"
        lines.append(f"- {s.topic} [{scope}]: {level} ({s.score:.2f}, {s.attempts} tries)")
    return "\n".join(lines)


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

    memories = memory.recall(user.id, user_message, limit=5)
    mastery = _mastery_summary(user, scope["lesson_ids"] or None, scope["topics"] or None)

    lesson_scope = scope["lesson_ids"] or "all"
    topic_scope = scope["topics"] or "any"
    system = TUTOR_SYSTEM.format(
        mode=scope["mode"],
        lesson_scope=lesson_scope,
        topic_scope=topic_scope,
        mastery=mastery,
        memories="\n".join(f"- {m}" for m in memories) if memories else "(none yet)",
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

    # Assess the student's answer (against the assistant's PREVIOUS question).
    _assess_and_adapt(conversation, user_message, scope, model)
    return assistant_msg


def _previous_assistant_message(conversation: Conversation) -> str:
    prev = (
        conversation.messages.filter(role=Message.Role.ASSISTANT)
        .order_by("-created_at")[1:2]
        .first()
    )
    return prev.content if prev else ""


def _assess_and_adapt(conversation, user_message, scope, model) -> None:
    prior_question = _previous_assistant_message(conversation)
    if not prior_question:
        return
    try:
        raw = openrouter.chat(
            model,
            [
                {
                    "role": "user",
                    "content": ASSESS_PROMPT.format(
                        assistant=prior_question[:1500],
                        student=user_message[:1500],
                        topics=", ".join(scope["topics"]) or "any",
                    ),
                }
            ],
            temperature=0.0,
            max_tokens=250,
        )
        data = parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Assessment failed: %s", exc)
        return

    if not data.get("assessed"):
        return

    topic = str(data.get("topic") or "general").lower()[:120]
    correctness = float(data.get("correctness") or 0.0)
    note = str(data.get("note") or "")[:500]
    lesson_id = data.get("lesson_id")
    lesson = None
    if isinstance(lesson_id, int):
        from lessons.models import Lesson

        lesson = Lesson.objects.filter(pk=lesson_id, user=conversation.user).first()

    skill, _ = Skill.objects.get_or_create(
        user=conversation.user, lesson=lesson, topic=topic
    )
    skill.register_attempt(correctness)
    Attempt.objects.create(
        user=conversation.user,
        skill=skill,
        question=prior_question[:2000],
        answer=user_message[:2000],
        correctness=correctness,
        note=note,
    )

    verdict = "got right" if correctness >= 0.7 else "partly knew" if correctness >= 0.4 else "struggled with"
    memory.add_interaction(
        conversation.user.id,
        f"Student {verdict} '{topic}': {note}",
        metadata={"topic": topic, "correctness": correctness},
    )
