"""CLI: config, Apify, digest, RAG, chat."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from cwt_agent import __version__
from cwt_agent.apify_market_text import text_from_apify_saved_json
from cwt_agent.apify_polymarket import (
    ApifyPolymarketError,
    load_apify_result,
    load_run_input,
    run_polymarket_scraper,
    save_apify_result,
)
from cwt_agent.config import _ROOT, get_settings, reload_settings
from cwt_agent.digest import build_digest, save_digest
from cwt_agent.hermes_chat import hermes_available, run_hermes_turn
from cwt_agent.kalshi_stub import fetch_kalshi_trader_snapshot, kalshi_configured
from cwt_agent.logging_setup import configure_logging, get_logger
from cwt_agent.openrouter_client import chat_complete, make_client, resolve_openrouter_key
from cwt_agent.rag_store import delete_chroma_collection, ingest_text_chunks, query_rag
from cwt_agent.verify_smoke import run_smoke_tests

app = typer.Typer(no_args_is_help=True, add_completion=False)
log = get_logger("cli")


@app.callback()
def main_callback() -> None:
    configure_logging()


@app.command()
def version() -> None:
    typer.echo(__version__)


def _openrouter_hint(value: str) -> str:
    if not value:
        return "empty"
    if value.startswith("sk-or"):
        return f"{len(value)} chars, looks like OpenRouter (sk-or…)"
    return f"{len(value)} chars — keys usually start with sk-or-"


def _apify_hint(value: str) -> str:
    if not value:
        return "empty"
    return f"{len(value)} chars"


@app.command("doctor")
def doctor_cmd() -> None:
    import os

    reload_settings()
    s = get_settings()
    env_file = _ROOT / ".env"
    typer.echo(f"project_root (pyproject.toml): {_ROOT}")
    typer.echo(f".env path: {env_file}  exists={env_file.is_file()}")
    typer.echo(f"os.environ OPENROUTER_API_KEY len: {len(os.environ.get('OPENROUTER_API_KEY') or '')}")
    typer.echo(f"os.environ APIFY_TOKEN len: {len(os.environ.get('APIFY_TOKEN') or '')}")
    typer.echo(f"Settings.openrouter_api_key len: {len(s.openrouter_api_key or '')}")
    typer.echo(f"Settings.apify_token len: {len(s.apify_token or '')}")


@app.command("check-config")
def check_config() -> None:
    reload_settings()
    env_path = _ROOT / ".env"
    typer.echo(f"Project root: {_ROOT}")
    typer.echo(f"Project .env path: {env_path} ({'exists' if env_path.is_file() else 'MISSING FILE'})")

    s = get_settings()
    or_key = s.openrouter_api_key
    apify = s.apify_token
    rows = [
        ("OPENROUTER_API_KEY", bool(or_key), _openrouter_hint(or_key)),
        ("APIFY_TOKEN", bool(apify), _apify_hint(apify)),
        ("APIFY_POLYMARKET_ACTOR", s.apify_polymarket_actor, ""),
        ("KALSHI_API_KEY_ID", bool(s.kalshi_api_key_id), ""),
        ("KALSHI_PRIVATE_KEY_PATH", bool(s.kalshi_private_key_path), ""),
        ("Hermes importable", hermes_available(), ""),
    ]
    for name, ok, hint in rows:
        status = "OK" if ok else "MISSING"
        extra = f" ({hint})" if hint else ""
        typer.echo(f"{name}: {status}{extra}")
    if kalshi_configured(s):
        typer.echo("Kalshi: configured (fetch still TODO in kalshi_stub.py)")
    else:
        typer.echo("Kalshi: not configured (optional)")


@app.command("chroma-reset")
def chroma_reset_cmd() -> None:
    """Delete the Chroma collection (e.g. after changing embedding model). Re-ingest RAG after."""
    reload_settings()
    s = get_settings()
    delete_chroma_collection(s)
    typer.echo(f"Deleted Chroma collection {s.chroma_collection!r} under {s.chroma_path}")


@app.command("verify")
def verify_cmd() -> None:
    reload_settings()
    s = get_settings()
    report = run_smoke_tests(s)
    for line in report.lines:
        typer.echo(line)
    if not report.ok:
        raise typer.Exit(code=1)
    typer.echo("\nAll checks passed. Next: cwt apify-polymarket examples/apify_polymarket_input.json")


@app.command("apify-polymarket")
def apify_polymarket(
    input_json: Path = typer.Argument(..., help="Path to Apify actor input JSON"),
    out: Path = typer.Option(
        Path("data/raw/apify_polymarket_last.json"),
        "--out",
        help="Where to save full run + dataset items",
    ),
    timeout: int = typer.Option(3600, "--timeout", help="Max wait seconds"),
) -> None:
    s = get_settings()
    run_input = load_run_input(input_json)
    log.info("apify.start", actor=s.apify_polymarket_actor)
    try:
        payload = run_polymarket_scraper(s, run_input, timeout_secs=timeout)
    except ApifyPolymarketError as e:
        log.error("apify.failed", err=str(e))
        raise typer.Exit(code=1) from e
    save_apify_result(out, payload)
    n = len(payload.get("dataset_items", []))
    log.info("apify.done", items=n, path=str(out))
    typer.echo(f"Saved {n} dataset rows to {out}")
    typer.echo("Next: cwt build-digest   (writes traders_digest.json for cwt chat)")


@app.command("build-digest")
def build_digest_cmd(
    apify_json: Path = typer.Option(
        Path("data/raw/apify_polymarket_last.json"),
        "--from",
        help="Saved Apify output",
    ),
) -> None:
    s = get_settings()
    raw = load_apify_result(apify_json)
    items = raw.get("dataset_items", [])
    digest = build_digest(items)
    save_digest(s.digest_path, digest)
    typer.echo(f"Digest written to {s.digest_path} ({len(digest['ranked_traders'])} ranked)")


@app.command("rag-ingest")
def rag_ingest(
    text_file: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Plain .txt or saved Apify JSON (with dataset_items) from cwt apify-polymarket",
    ),
    event_slug: str = typer.Option("manual-event", "--event", "-e"),
    source: str = typer.Option("user_file", "--source"),
    chunk_size: int = typer.Option(1200, "--chunk-size"),
) -> None:
    s = get_settings()
    raw_read = text_file.read_text(encoding="utf-8", errors="replace")
    text = raw_read
    if text_file.suffix.lower() == ".json":
        try:
            data = json.loads(raw_read)
            if isinstance(data, dict) and data.get("dataset_items"):
                flattened = text_from_apify_saved_json(data)
                if flattened.strip():
                    text = flattened
                    if source == "user_file":
                        source = "apify_markets"
        except json.JSONDecodeError:
            pass
    chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size) if text[i : i + chunk_size].strip()]
    if not resolve_openrouter_key(s):
        log.error("rag.no_key")
        raise typer.Exit(code=1)
    n = ingest_text_chunks(s, chunks, source=source, event_slug=event_slug)
    typer.echo(f"Ingested {n} chunks into Chroma collection {s.chroma_collection}")


@app.command("chat")
def chat_cmd(
    message: str = typer.Argument(..., help="User message"),
    use_hermes: bool = typer.Option(True, "--hermes/--no-hermes"),
) -> None:
    s = get_settings()
    if not resolve_openrouter_key(s):
        raise typer.Exit(code=1)

    digest_text = ""
    if s.digest_path.exists():
        digest_text = s.digest_path.read_text(encoding="utf-8")[:24000]

    rag_bits = query_rag(s, message, n_results=4)
    rag_text = "\n\n".join(b["text"][:1500] for b in rag_bits if b.get("text"))

    system = (
        "You are a prediction-market copy-trading research assistant. "
        "Ground answers ONLY in the DIGEST and RAG CONTEXT below. "
        "If DIGEST JSON contains ranked_traders with entries, that IS real Polymarket leaderboard data — "
        "summarize wallets, ranks, pnl_usd, volume_usd; do not call it empty or placeholder. "
        "RAG text may be user notes: say so if it looks like sample/placeholder text.\n\n"
        f"DIGEST (JSON excerpt):\n{digest_text or '(no digest file — run: cwt build-digest)'}\n\n"
        f"RAG CONTEXT:\n{rag_text or '(no chunks retrieved)'}\n"
    )

    if use_hermes and hermes_available():
        log.info("chat.engine", engine="hermes", model=s.openrouter_chat_model)
        res = run_hermes_turn(
            model=s.openrouter_chat_model,
            user_message=message,
            system_message=system,
            skip_memory=False,
            settings=s,
        )
        typer.echo(res.get("final_response", json.dumps(res, default=str)[:2000]))
    else:
        if use_hermes:
            log.warn("chat.hermes_missing", fallback="openrouter")
        client = make_client(s)
        out = chat_complete(
            client,
            s.openrouter_chat_model,
            [{"role": "system", "content": system}, {"role": "user", "content": message}],
        )
        typer.echo(out)


@app.command("chat-repl")
def chat_repl(
    use_hermes: bool = typer.Option(True, "--hermes/--no-hermes"),
) -> None:
    s = get_settings()
    if not resolve_openrouter_key(s):
        raise typer.Exit(code=1)
    if use_hermes and not hermes_available():
        typer.echo("Hermes not installed. Run: pip install -e '.[hermes]' or use --no-hermes")
        raise typer.Exit(code=1)

    history = None
    simple_msgs: list[dict] = []
    typer.echo("CWT chat-repl. /exit quit, /reset clear history.")
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            break
        if not line:
            continue
        if line == "/exit":
            break
        if line == "/reset":
            history = None
            simple_msgs.clear()
            typer.echo("(history reset)")
            continue

        digest_text = ""
        if s.digest_path.exists():
            digest_text = s.digest_path.read_text(encoding="utf-8")[:24000]
        rag_bits = query_rag(s, line, n_results=4)
        rag_text = "\n\n".join(b["text"][:1500] for b in rag_bits if b.get("text"))
        system = (
            "You are a prediction-market copy-trading research assistant. "
            "Ground answers in DIGEST and RAG. If DIGEST JSON has ranked_traders, treat it as real data. "
            "Remember user preferences across turns.\n\n"
            f"DIGEST:\n{digest_text or '(no digest — run cwt build-digest)'}\n\nRAG:\n{rag_text or '(none)'}\n"
        )

        if use_hermes:
            res = run_hermes_turn(
                model=s.openrouter_chat_model,
                user_message=line,
                system_message=system,
                conversation_history=history,
                skip_memory=False,
                settings=s,
                max_iterations=16,
            )
            history = res.get("messages")
            typer.echo(res.get("final_response", ""))
        else:
            client = make_client(s)
            simple_msgs.append({"role": "user", "content": line})
            msgs = [{"role": "system", "content": system}, *simple_msgs[-20:]]
            out = chat_complete(client, s.openrouter_chat_model, msgs)
            simple_msgs.append({"role": "assistant", "content": out})
            typer.echo(out)


@app.command("kalshi-status")
def kalshi_status() -> None:
    s = get_settings()
    typer.echo(json.dumps(fetch_kalshi_trader_snapshot(s), indent=2))


def entrypoint() -> None:
    app()


if __name__ == "__main__":
    app()
