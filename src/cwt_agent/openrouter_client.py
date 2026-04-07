"""OpenRouter via OpenAI-compatible client (chat + embeddings)."""

from __future__ import annotations

import os
from typing import Any, Sequence

import httpx
from openai import OpenAI

from cwt_agent.config import Settings


def resolve_openrouter_key(settings: Settings) -> str:
    k = (settings.openrouter_api_key or "").strip()
    if not k:
        k = (os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    return k


def openrouter_extra_headers(settings: Settings) -> dict[str, str]:
    ref = (getattr(settings, "openrouter_http_referer", None) or "https://openrouter.ai/").strip()
    title = (getattr(settings, "openrouter_app_title", None) or "CWT Prediction Agent").strip()
    return {
        "HTTP-Referer": ref or "https://openrouter.ai/",
        "X-Title": title or "CWT Prediction Agent",
    }


def make_client(settings: Settings) -> OpenAI:
    key = resolve_openrouter_key(settings)
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is empty. Put it in .env next to pyproject.toml as OPENROUTER_API_KEY=sk-or-..."
        )
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
        default_headers=openrouter_extra_headers(settings),
    )


def _embed_openrouter_http(
    api_key: str,
    model: str,
    texts: list[str],
    *,
    extra_headers: dict[str, str] | None = None,
) -> list[list[float]]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **(extra_headers or {}),
    }
    r = httpx.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers=headers,
        json={"model": model, "input": texts, "encoding_format": "float"},
        timeout=120.0,
    )
    if r.status_code >= 400:
        snippet = (r.text or "")[:1200]
        raise RuntimeError(
            f"OpenRouter embeddings HTTP {r.status_code} for model {model!r}. "
            f"Body (truncated): {snippet!r}. "
            "Regenerate key at https://openrouter.ai/keys — use the OpenRouter key, not only BYOK provider keys."
        )
    j = r.json()
    err = j.get("error")
    if err:
        raise RuntimeError(f"OpenRouter embeddings error: {err!r}")
    rows = j.get("data") or []
    if len(rows) != len(texts):
        raise RuntimeError(
            f"Embedding row count mismatch: got {len(rows)}, expected {len(texts)}; keys={list(j.keys())!r}."
        )
    rows.sort(key=lambda x: x.get("index", 0))
    out: list[list[float]] = []
    for row in rows:
        vec = row.get("embedding")
        if not isinstance(vec, list) or not vec:
            raise RuntimeError(f"Invalid embedding vector in row keys={list(row.keys())!r}")
        out.append([float(x) for x in vec])
    return out


def embed_texts(
    client: OpenAI,
    model: str,
    texts: Sequence[str],
    *,
    settings: Settings | None = None,
    fallback_model: str | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    texts_l = list(texts)
    key = (getattr(client, "api_key", None) or "").strip()
    if not key:
        key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()

    extra = openrouter_extra_headers(settings) if settings is not None else {}

    models: list[str] = []
    m0 = (model or "").strip()
    if m0:
        models.append(m0)
    fb = (fallback_model or "").strip()
    if fb and fb not in models:
        models.append(fb)

    errors: list[str] = []
    for m in models:
        try:
            return _embed_openrouter_http(key, m, texts_l, extra_headers=extra)
        except Exception as e:
            errors.append(f"{m!r}: {e}")

    def try_sdk(m: str) -> list[list[float]] | None:
        try:
            resp = client.embeddings.create(
                model=m,
                input=texts_l,
                encoding_format="float",
            )
            data = sorted(resp.data or [], key=lambda d: d.index)
            if len(data) != len(texts_l):
                return None
            vecs: list[list[float]] = []
            for d in data:
                e = d.embedding
                if e is None or (isinstance(e, list) and len(e) == 0):
                    return None
                vecs.append([float(x) for x in e])
            return vecs
        except Exception:
            return None

    for m in models:
        v = try_sdk(m)
        if v is not None:
            return v

    raise RuntimeError(
        "Could not obtain embeddings. Attempts:\n  - "
        + "\n  - ".join(errors)
        + "\nCheck OPENROUTER_EMBEDDING_MODEL / OPENROUTER_EMBEDDING_FALLBACK_MODEL and https://openrouter.ai/keys"
    )


def chat_complete(
    client: OpenAI,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.3,
) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    choice = resp.choices[0]
    return (choice.message.content or "").strip()
