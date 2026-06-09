"""Mem0-backed learner memory — the tutor's long-term picture of each student.

All progress tracking lives here as natural-language memories (strengths,
weaknesses, confusions, preferences), recalled contextually each session.
There is no separate structured score table.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)

TUTORING_RECALL_LIMIT = 14
GENERAL_RECALL_LIMIT = 6


def _pg_config() -> dict | None:
    db = settings.DATABASES["default"]
    if "postgresql" not in db.get("ENGINE", "") and "postgres" not in db.get("ENGINE", ""):
        return None
    return {
        "host": db.get("HOST") or "localhost",
        "port": int(db.get("PORT") or 5432),
        "dbname": db.get("NAME"),
        "user": db.get("USER"),
        "password": db.get("PASSWORD"),
    }


@lru_cache(maxsize=1)
def _get_memory():
    if not settings.MEM0_ENABLED:
        return None
    if not settings.OPENAI_API_KEY or not settings.OPENROUTER_API_KEY:
        logger.info("Mem0 disabled: missing OPENAI_API_KEY or OPENROUTER_API_KEY.")
        return None
    pg = _pg_config()
    if pg is None:
        logger.info("Mem0 disabled: a Postgres database is required (pgvector).")
        return None
    try:
        from mem0 import Memory

        config = {
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "dbname": pg["dbname"],
                    "user": pg["user"],
                    "password": pg["password"],
                    "host": pg["host"],
                    "port": pg["port"],
                    "collection_name": "mem0_learner",
                    "embedding_model_dims": 1536,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "api_key": settings.OPENAI_API_KEY,
                    "model": settings.OPENAI_EMBEDDING_MODEL,
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "api_key": settings.OPENROUTER_API_KEY,
                    "model": "openai/gpt-4o-mini",
                    "openai_base_url": settings.OPENROUTER_BASE_URL,
                },
            },
        }
        return Memory.from_config(config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mem0 unavailable, continuing without it: %s", exc)
        return None


def is_enabled() -> bool:
    return _get_memory() is not None


def _search(user_id: int, query: str, limit: int) -> list[str]:
    mem = _get_memory()
    if mem is None:
        return []
    try:
        results = mem.search(query, user_id=str(user_id), limit=limit)
        items = results.get("results", results) if isinstance(results, dict) else results
        return [r.get("memory", "") for r in items if r.get("memory")]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mem0 search failed: %s", exc)
        return []


def recall(user_id: int, query: str, limit: int = 8) -> list[str]:
    return _search(user_id, query, limit)


def recall_for_tutoring(
    user_id: int,
    message: str,
    *,
    lesson_ids: list[int] | None = None,
    topics: list[str] | None = None,
    mode: str = "chat",
) -> list[str]:
    """Pull memories relevant to this turn — scoped + general profile."""
    scoped_parts = [message]
    if topics:
        scoped_parts.append("focus: " + ", ".join(topics))
    if lesson_ids:
        scoped_parts.append("lessons: " + ", ".join(str(i) for i in lesson_ids))
    scoped_parts.append(f"mode: {mode}")
    scoped_parts.append("strengths weaknesses mistakes confusions progress")

    scoped = _search(user_id, " | ".join(scoped_parts), TUTORING_RECALL_LIMIT)
    general = _search(
        user_id,
        "Georgian Kartuli student overall strengths weaknesses learning progress preferences",
        GENERAL_RECALL_LIMIT,
    )

    seen: set[str] = set()
    merged: list[str] = []
    for item in scoped + general:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            merged.append(item.strip())
    return merged


def remember(
    user_id: int,
    content: str,
    metadata: dict | None = None,
) -> None:
    """Store a natural-language observation about the student."""
    mem = _get_memory()
    if mem is None or not content.strip():
        return
    try:
        mem.add(content.strip(), user_id=str(user_id), metadata=metadata or {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mem0 add failed: %s", exc)


def remember_many(
    user_id: int,
    memories: list[str],
    metadata: dict | None = None,
) -> None:
    for item in memories:
        remember(user_id, item, metadata=metadata)
