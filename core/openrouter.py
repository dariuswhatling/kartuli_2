"""Thin client around the OpenRouter API.

OpenRouter is OpenAI-compatible, so we use the `openai` SDK for chat
completions and a plain HTTP request for the public model catalogue.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import requests
from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

MODELS_URL = "https://openrouter.ai/api/v1/models"


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter is misconfigured or returns an error."""


def _api_key() -> str:
    key = settings.OPENROUTER_API_KEY
    if not key:
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file."
        )
    return key


def _extra_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.OPENROUTER_SITE_URL:
        headers["HTTP-Referer"] = settings.OPENROUTER_SITE_URL
    if settings.OPENROUTER_APP_NAME:
        headers["X-Title"] = settings.OPENROUTER_APP_NAME
    return headers


def get_client() -> OpenAI:
    return OpenAI(base_url=settings.OPENROUTER_BASE_URL, api_key=_api_key())


@lru_cache(maxsize=1)
def _cached_models(_cache_token: int) -> list[dict[str, Any]]:
    resp = requests.get(MODELS_URL, timeout=20)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    models = []
    for item in data:
        pricing = item.get("pricing", {}) or {}
        models.append(
            {
                "id": item.get("id"),
                "name": item.get("name") or item.get("id"),
                "context_length": item.get("context_length"),
                "prompt_price": pricing.get("prompt"),
                "completion_price": pricing.get("completion"),
                "description": (item.get("description") or "")[:280],
            }
        )
    models.sort(key=lambda m: (m["name"] or "").lower())
    return models


def list_models(cache_token: int = 0) -> list[dict[str, Any]]:
    """Return available OpenRouter models. `cache_token` busts the cache."""
    try:
        return _cached_models(cache_token)
    except Exception as exc:  # noqa: BLE001 - surface a clean message to the UI
        logger.warning("Failed to fetch OpenRouter models: %s", exc)
        return []


def chat(
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> str:
    """Run a chat completion and return the assistant text."""
    client = get_client()
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_headers=_extra_headers(),
        )
    except Exception as exc:  # noqa: BLE001
        raise OpenRouterError(f"OpenRouter chat request failed: {exc}") from exc
    return (completion.choices[0].message.content or "").strip()
