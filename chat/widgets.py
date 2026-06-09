"""Interactive tutoring widgets embedded in assistant messages."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

WIDGET_BLOCK_RE = re.compile(
    r"```kartuli-widgets\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)

SUPPORTED_TYPES = {
    "mcq",
    "true_false",
    "translate_pick",
    "flashcard",
    "fill_blank",
    "conjugate",
    "self_rating",
}

TOOL_TO_TYPE = {
    "show_mcq": "mcq",
    "show_true_false": "true_false",
    "show_translate_pick": "translate_pick",
    "show_flashcard": "flashcard",
    "show_fill_blank": "fill_blank",
    "show_conjugate": "conjugate",
    "show_self_rating": "self_rating",
}

CLIENT_HIDDEN = {"answer", "back", "explanation"}

WIDGET_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "show_mcq",
            "description": "Show a multiple-choice question card the student taps to answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The question text"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "description": "Answer choices",
                    },
                    "answer": {
                        "type": "integer",
                        "description": "0-based index of the correct option",
                    },
                    "explanation": {"type": "string", "description": "Feedback after answering"},
                },
                "required": ["prompt", "options", "answer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_true_false",
            "description": "Show a true/false statement card.",
            "parameters": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "answer": {"type": "boolean"},
                    "explanation": {"type": "string"},
                },
                "required": ["statement", "answer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_translate_pick",
            "description": "Show Georgian text; student picks the English translation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "georgian": {"type": "string"},
                    "translit": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                    "answer": {"type": "integer"},
                    "explanation": {"type": "string"},
                },
                "required": ["georgian", "options", "answer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_flashcard",
            "description": "Show a flashcard: front visible, student reveals back and self-grades.",
            "parameters": {
                "type": "object",
                "properties": {
                    "front": {"type": "string"},
                    "back": {"type": "string"},
                    "hint": {"type": "string"},
                },
                "required": ["front", "back"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_fill_blank",
            "description": "Show a sentence with a blank; student picks the missing word.",
            "parameters": {
                "type": "object",
                "properties": {
                    "before": {"type": "string"},
                    "after": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                    "answer": {"type": "integer"},
                    "explanation": {"type": "string"},
                },
                "required": ["before", "after", "options", "answer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_conjugate",
            "description": "Show a verb conjugation drill with multiple choice.",
            "parameters": {
                "type": "object",
                "properties": {
                    "verb": {"type": "string"},
                    "tense": {"type": "string"},
                    "subject": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}, "minItems": 2},
                    "answer": {"type": "integer"},
                    "explanation": {"type": "string"},
                },
                "required": ["options", "answer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_self_rating",
            "description": "Ask the student to rate confidence 1–5 after teaching.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "scale": {"type": "integer", "minimum": 3, "maximum": 5},
                },
                "required": ["prompt"],
            },
        },
    },
]


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def _parse_widget_list(raw: str) -> list[dict]:
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        data = data.get("widgets", [])
    if not isinstance(data, list):
        return []
    return [w for w in data if isinstance(w, dict)]


def _normalize_widget(raw: dict) -> dict | None:
    wtype = str(raw.get("type", "")).lower().strip()
    if wtype not in SUPPORTED_TYPES:
        return None

    widget: dict[str, Any] = {"id": _new_id(), "type": wtype}

    if wtype == "mcq":
        options = raw.get("options") or []
        if not isinstance(options, list) or len(options) < 2:
            return None
        answer = raw.get("answer")
        if not isinstance(answer, int) or not (0 <= answer < len(options)):
            return None
        widget.update(
            prompt=str(raw.get("prompt", "")).strip(),
            options=[str(o) for o in options],
            answer=answer,
            explanation=str(raw.get("explanation", "")).strip(),
        )

    elif wtype == "true_false":
        answer = raw.get("answer")
        if not isinstance(answer, bool):
            if str(answer).lower() in {"true", "yes", "1"}:
                answer = True
            elif str(answer).lower() in {"false", "no", "0"}:
                answer = False
            else:
                return None
        widget.update(
            statement=str(raw.get("statement", "")).strip(),
            answer=answer,
            explanation=str(raw.get("explanation", "")).strip(),
        )

    elif wtype == "translate_pick":
        options = raw.get("options") or []
        if not isinstance(options, list) or len(options) < 2:
            return None
        answer = raw.get("answer")
        if not isinstance(answer, int) or not (0 <= answer < len(options)):
            return None
        widget.update(
            georgian=str(raw.get("georgian", "")).strip(),
            translit=str(raw.get("translit", "")).strip(),
            options=[str(o) for o in options],
            answer=answer,
            explanation=str(raw.get("explanation", "")).strip(),
        )

    elif wtype == "flashcard":
        front = str(raw.get("front", "")).strip()
        back = str(raw.get("back", "")).strip()
        if not front or not back:
            return None
        widget.update(
            front=front,
            back=back,
            hint=str(raw.get("hint", "")).strip(),
        )

    elif wtype == "fill_blank":
        options = raw.get("options") or []
        if not isinstance(options, list) or len(options) < 2:
            return None
        answer = raw.get("answer")
        if not isinstance(answer, int) or not (0 <= answer < len(options)):
            return None
        widget.update(
            before=str(raw.get("before", "")).strip(),
            after=str(raw.get("after", "")).strip(),
            options=[str(o) for o in options],
            answer=answer,
            explanation=str(raw.get("explanation", "")).strip(),
        )

    elif wtype == "conjugate":
        options = raw.get("options") or []
        if not isinstance(options, list) or len(options) < 2:
            return None
        answer = raw.get("answer")
        if not isinstance(answer, int) or not (0 <= answer < len(options)):
            return None
        widget.update(
            verb=str(raw.get("verb", "")).strip(),
            tense=str(raw.get("tense", "")).strip(),
            subject=str(raw.get("subject", "")).strip(),
            options=[str(o) for o in options],
            answer=answer,
            explanation=str(raw.get("explanation", "")).strip(),
        )

    elif wtype == "self_rating":
        widget.update(
            prompt=str(raw.get("prompt", "How confident do you feel about this?")).strip(),
            scale=int(raw.get("scale", 5)),
        )

    return widget


def widgets_from_tool_calls(tool_calls: list[Any]) -> list[dict]:
    """Convert model tool calls into validated widget payloads."""
    widgets: list[dict] = []
    for tc in tool_calls:
        name = getattr(tc, "name", None) or ""
        args = getattr(tc, "arguments", None) or {}
        wtype = TOOL_TO_TYPE.get(name)
        if not wtype or not isinstance(args, dict):
            continue
        raw = {"type": wtype, **args}
        normalized = _normalize_widget(raw)
        if normalized:
            widgets.append(normalized)
        if len(widgets) >= 2:
            break
    return widgets


def parse_reply(text: str) -> tuple[str, list[dict]]:
    """Split assistant text into display prose + validated widgets."""
    match = WIDGET_BLOCK_RE.search(text)
    if not match:
        return text.strip(), []

    widgets: list[dict] = []
    for raw in _parse_widget_list(match.group(1)):
        normalized = _normalize_widget(raw)
        if normalized:
            widgets.append(normalized)

    display = WIDGET_BLOCK_RE.sub("", text).strip()
    return display, widgets


def client_payload(widget: dict) -> dict:
    """Strip grading secrets before sending to the browser."""
    out = {k: v for k, v in widget.items() if k not in CLIENT_HIDDEN}
    if widget.get("type") == "flashcard" and "back" in widget:
        out.pop("back", None)
    return out


def grade_widget(widget: dict, response: str) -> dict:
    """Grade a widget interaction. `response` encoding varies by type."""
    wtype = widget["type"]
    correct = False
    feedback = widget.get("explanation", "")
    label = ""

    if wtype in {"mcq", "translate_pick", "fill_blank", "conjugate"}:
        try:
            chosen = int(response)
        except (TypeError, ValueError):
            return {"correct": False, "feedback": "Invalid answer.", "label": ""}
        correct = chosen == widget["answer"]
        label = widget["options"][chosen] if 0 <= chosen < len(widget["options"]) else ""
        if not feedback:
            feedback = (
                "Correct!" if correct else f"The answer is: {widget['options'][widget['answer']]}"
            )

    elif wtype == "true_false":
        val = str(response).lower()
        if val in {"true", "1", "yes"}:
            chosen = True
        elif val in {"false", "0", "no"}:
            chosen = False
        else:
            return {"correct": False, "feedback": "Invalid answer.", "label": ""}
        correct = chosen == widget["answer"]
        label = "True" if chosen else "False"
        if not feedback:
            feedback = "Correct!" if correct else f"The answer is {'True' if widget['answer'] else 'False'}."

    elif wtype == "flashcard":
        val = str(response).lower()
        if val == "knew":
            correct = True
            feedback = widget.get("explanation") or f"Nice — the answer is: {widget['back']}"
            label = "Knew it"
        elif val == "practice":
            correct = False
            feedback = widget.get("explanation") or f"Keep practising — answer: {widget['back']}"
            label = "Needs practice"
        else:
            return {"correct": False, "feedback": "Invalid response.", "label": ""}

    elif wtype == "self_rating":
        try:
            rating = int(response)
        except (TypeError, ValueError):
            return {"correct": True, "feedback": "Thanks for rating.", "label": ""}
        correct = True
        label = f"{rating}/{widget.get('scale', 5)}"
        feedback = "Noted — I'll adjust accordingly."
        if rating <= 2:
            feedback = "Got it — we'll revisit this more."
        elif rating >= 4:
            feedback = "Great confidence — I'll move you forward."

    out = {"correct": correct, "feedback": feedback, "label": label}
    if wtype in {"mcq", "translate_pick", "fill_blank", "conjugate"}:
        out["correct_index"] = widget["answer"]
    if wtype == "true_false":
        out["correct_value"] = widget["answer"]
    return out


def memory_note(widget: dict, result: dict) -> str:
    wtype = widget["type"]
    topic = widget.get("prompt") or widget.get("statement") or widget.get("georgian") or wtype
    topic = str(topic)[:80]
    verdict = "handled well" if result["correct"] else "needs more practice on"
    return f"Student {verdict} ({wtype}): {topic} — {result.get('label', '')}"
