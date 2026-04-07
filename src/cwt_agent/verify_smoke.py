"""Non-destructive checks: OpenRouter, Apify, Chroma, Hermes."""

from __future__ import annotations

from dataclasses import dataclass, field

from apify_client import ApifyClient

from cwt_agent.config import Settings
from cwt_agent.hermes_chat import hermes_available, run_hermes_turn
from cwt_agent.openrouter_client import chat_complete, embed_texts, make_client, resolve_openrouter_key
from cwt_agent.rag_store import ingest_text_chunks, query_rag


@dataclass
class SmokeReport:
    ok: bool = True
    lines: list[str] = field(default_factory=list)

    def add(self, name: str, success: bool, detail: str = "") -> None:
        status = "PASS" if success else "FAIL"
        self.lines.append(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
        if not success:
            self.ok = False


def run_smoke_tests(settings: Settings) -> SmokeReport:
    r = SmokeReport()

    or_key = resolve_openrouter_key(settings)
    if not or_key:
        r.add("OpenRouter API key", False, "set OPENROUTER_API_KEY in .env")
        return r

    client = make_client(settings)

    try:
        reply = chat_complete(
            client,
            settings.openrouter_chat_model,
            [{"role": "user", "content": 'Reply with exactly one word: smoke_ok'}],
            temperature=0,
        )
        ok = "smoke_ok" in reply.lower() or (0 < len(reply) < 500)
        r.add("OpenRouter chat", ok, reply[:120])
    except Exception as e:
        r.add("OpenRouter chat", False, str(e))

    try:
        fb = (settings.openrouter_embedding_fallback_model or "").strip() or None
        vecs = embed_texts(
            client,
            settings.openrouter_embedding_model,
            ["embedding probe"],
            settings=settings,
            fallback_model=fb,
        )
        r.add(
            "OpenRouter embeddings",
            len(vecs) == 1 and len(vecs[0]) > 0,
            f"dim={len(vecs[0]) if vecs else 0}",
        )
    except Exception as e:
        r.add("OpenRouter embeddings", False, str(e))

    if not settings.apify_token:
        r.add("Apify token", False, "set APIFY_TOKEN in .env")
    else:
        try:
            me = ApifyClient(settings.apify_token).user().get()
            uid = me.get("id") or me.get("username") or "ok"
            r.add("Apify API (user)", True, str(uid)[:80])
        except Exception as e:
            r.add("Apify API (user)", False, str(e))

    try:
        n = ingest_text_chunks(
            settings,
            ["CWT chroma smoke test chunk about prediction markets."],
            source="smoke_test",
            event_slug="smoke",
        )
        hits = query_rag(settings, "prediction markets smoke", n_results=2)
        r.add("Chroma + RAG query", n > 0 and len(hits) > 0, f"ingested={n}, hits={len(hits)}")
    except Exception as e:
        r.add("Chroma + RAG query", False, str(e))

    if not hermes_available():
        r.add("Hermes import", False, "pip install -e '.[hermes]'")
    else:
        try:
            res = run_hermes_turn(
                model=settings.openrouter_chat_model,
                user_message='Output only the text: hermes_ping',
                system_message="You must output exactly: hermes_ping. No tools.",
                skip_memory=True,
                settings=settings,
                max_iterations=4,
            )
            text = (res.get("final_response") or "")[:200]
            r.add("Hermes + OpenRouter", len(text) > 0, text.replace("\n", " "))
        except Exception as e:
            r.add("Hermes + OpenRouter", False, str(e))

    return r
