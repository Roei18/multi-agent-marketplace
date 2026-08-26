"""One thin wrapper around the framework's LLM client.

`generate()` needs an explicit provider (resolved from `.env` via
`BaseLLMConfig`), and transient provider errors (rate limits, truncated JSON)
are worth a few retries with exponential backoff -- a tournament that makes
several hundred serial calls is a lot of traffic to let a single blip kill.
"""

from __future__ import annotations

import asyncio
from typing import TypeVar

from magentic_marketplace.marketplace.llm import generate
from magentic_marketplace.marketplace.llm.config import BaseLLMConfig
from pydantic import BaseModel

TModel = TypeVar("TModel", bound=BaseModel)

_kwargs: dict | None = None


def _llm_kwargs() -> dict:
    """Resolve provider/model lazily so importing this module needs no .env."""
    global _kwargs
    if _kwargs is None:
        cfg = BaseLLMConfig()
        _kwargs = {
            "provider": cfg.provider,
            "model": cfg.model,
            "reasoning_effort": cfg.reasoning_effort,
        }
        if cfg.temperature is not None:
            _kwargs["temperature"] = cfg.temperature
    return _kwargs


async def call_llm(prompt: str, response_format: type[TModel], attempts: int = 5,
                   model: str | None = None, reasoning_effort: str | int | None = None) -> TModel:
    kw = _llm_kwargs()
    if model:                      # per-call model override (e.g. a stronger buyer/seller)
        kw = {**kw, "model": model}
    if reasoning_effort is not None:   # per-call reasoning-effort override
        kw = {**kw, "reasoning_effort": reasoning_effort}
    delay = 3.0
    last: Exception | None = None
    for _ in range(attempts):
        try:
            result, _usage = await generate(
                prompt, response_format=response_format, **kw
            )
            return result
        except Exception as e:  # rate limits, malformed output, transient API errors
            last = e
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
    raise RuntimeError(f"LLM call failed after {attempts} attempts") from last
