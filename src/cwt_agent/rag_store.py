"""Chroma persistent store + OpenRouter embeddings."""

from __future__ import annotations

from typing import Sequence
from uuid import uuid4

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from cwt_agent.config import Settings
from cwt_agent.openrouter_client import embed_texts, make_client, resolve_openrouter_key


class OpenRouterEmbeddingFn(EmbeddingFunction):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = make_client(settings)
        self._model = settings.openrouter_embedding_model

    def __call__(self, input: Documents) -> Embeddings:
        if not resolve_openrouter_key(self._settings):
            raise RuntimeError("OPENROUTER_API_KEY required for embeddings")
        texts: list[str] = list(input)
        fb = (self._settings.openrouter_embedding_fallback_model or "").strip() or None
        return embed_texts(
            self._client,
            self._model,
            texts,
            settings=self._settings,
            fallback_model=fb,
        )


def _probe_embedding_dimension(settings: Settings) -> int:
    """Current model output size (changes if you switch OPENROUTER_EMBEDDING_MODEL)."""
    c = make_client(settings)
    fb = (settings.openrouter_embedding_fallback_model or "").strip() or None
    vecs = embed_texts(
        c,
        settings.openrouter_embedding_model,
        ["dimension-probe"],
        settings=settings,
        fallback_model=fb,
    )
    return len(vecs[0])


def delete_chroma_collection(settings: Settings) -> None:
    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    try:
        client.delete_collection(name=settings.chroma_collection)
    except Exception:
        pass


def get_collection(settings: Settings) -> chromadb.Collection:
    """
    Recreate the collection if the embedding dimension changed (e.g. switched from 2048-dim to 1536-dim model).
    """
    client = chromadb.PersistentClient(path=str(settings.chroma_path))
    name = settings.chroma_collection
    dim = _probe_embedding_dimension(settings)
    emb = OpenRouterEmbeddingFn(settings)

    try:
        col = client.get_collection(name=name)
        md = col.metadata or {}
        stored = md.get("embedding_dim")
        if stored is not None and int(stored) != dim:
            client.delete_collection(name=name)
    except Exception:
        pass

    return client.get_or_create_collection(
        name=name,
        embedding_function=emb,
        metadata={
            "description": "CWT event enrichment for RAG",
            "embedding_dim": str(dim),
        },
    )


def ingest_text_chunks(
    settings: Settings,
    chunks: Sequence[str],
    *,
    source: str,
    event_slug: str,
) -> int:
    col = get_collection(settings)
    ids = [f"{event_slug}-{uuid4().hex[:12]}" for _ in chunks]
    metadatas = [{"source": source, "event_slug": event_slug} for _ in chunks]
    try:
        col.add(ids=ids, documents=list(chunks), metadatas=metadatas)
    except Exception as e:
        err = str(e).lower()
        if "dimension" in err or "2048" in err or "1536" in err:
            delete_chroma_collection(settings)
            col = get_collection(settings)
            col.add(ids=ids, documents=list(chunks), metadatas=metadatas)
        else:
            raise
    return len(ids)


def query_rag(settings: Settings, question: str, n_results: int = 5) -> list[dict]:
    try:
        col = get_collection(settings)
        res = col.query(query_texts=[question], n_results=n_results)
    except Exception as e:
        err = str(e).lower()
        if "dimension" in err or "embedding" in err:
            delete_chroma_collection(settings)
            col = get_collection(settings)
            res = col.query(query_texts=[question], n_results=n_results)
        else:
            raise
    out = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0] if res.get("distances") else []
    for i, doc in enumerate(docs):
        out.append(
            {
                "text": doc,
                "metadata": metas[i] if i < len(metas) else {},
                "distance": dists[i] if i < len(dists) else None,
            }
        )
    return out
