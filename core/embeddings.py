"""OpenAI embeddings + lightweight in-Python similarity search.

Embeddings are stored as JSON arrays on the lesson chunks, so semantic
search works identically on SQLite (local dev) and Postgres (prod) without
needing a vector extension for the lesson store. Personal-scale data makes
in-memory cosine similarity perfectly fast.
"""
from __future__ import annotations

import logging

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    pass


def _client() -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise EmbeddingError(
            "OPENAI_API_KEY is not set. It is required for semantic search."
        )
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = _client()
    resp = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in resp.data]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / ((norm_a**0.5) * (norm_b**0.5))
