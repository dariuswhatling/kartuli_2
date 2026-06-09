"""Mem0-backed learner memory (self-hosted).

Stores soft, cross-session facts about the user ("prefers romanization",
"keeps confusing future vs present tense"). It is intentionally optional:
if Mem0 or its dependencies are unavailable, every call degrades to a no-op
so the rest of the app keeps working.

Structured mastery scores live in the database (see chat.models), not here.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)


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


def add_interaction(user_id: int, content: str, metadata: dict | None = None) -> None:
    mem = _get_memory()
    if mem is None:
        return
    try:
        mem.add(content, user_id=str(user_id), metadata=metadata or {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mem0 add failed: %s", exc)


def recall(user_id: int, query: str, limit: int = 5) -> list[str]:
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
