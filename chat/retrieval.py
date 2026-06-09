"""Scoped semantic retrieval over a user's lesson chunks."""
from __future__ import annotations

from core import embeddings
from lessons.models import Chunk


def retrieve_chunks(
    user,
    query: str,
    *,
    lesson_ids: list[int] | None = None,
    topics: list[str] | None = None,
    limit: int = 6,
) -> list[Chunk]:
    qs = Chunk.objects.filter(user=user).select_related("lesson")
    if lesson_ids:
        qs = qs.filter(lesson_id__in=lesson_ids)
    if topics:
        topics_lower = [t.lower() for t in topics]
        # JSONField containment is backend-specific; filter in Python instead.
        candidates = [
            c
            for c in qs
            if any(str(t).lower() in topics_lower for t in (c.topics or []))
        ]
    else:
        candidates = list(qs)

    if not candidates:
        return []

    try:
        query_vec = embeddings.embed_text(query)
    except Exception:  # noqa: BLE001 - fall back to recency if embeddings fail
        return candidates[:limit]

    scored = []
    for chunk in candidates:
        if not chunk.embedding:
            continue
        sim = embeddings.cosine_similarity(query_vec, chunk.embedding)
        scored.append((sim, chunk))

    if not scored:
        return candidates[:limit]

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]
