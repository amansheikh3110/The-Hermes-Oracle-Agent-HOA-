"""Build traders_digest.json from Apify dataset + niche tagging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cwt_agent.niches import score_text_for_niches
from cwt_agent.scoring import rank_wallets, trades_from_apify_items


def _text_blob(row: dict[str, Any]) -> str:
    """Concatenate human-readable market/event fields for niche keyword scoring."""
    parts: list[str] = []
    for key in (
        "title",
        "question",
        "description",
        "market",
        "name",
        "text",
        # dadhalfdev / market-style actors
        "market_question",
        "market_description",
        "event_title",
        "event_category",
        "event_subcategory",
    ):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    return " ".join(parts)


def build_digest(apify_items: list[dict[str, Any]]) -> dict[str, Any]:
    trades = trades_from_apify_items(apify_items)
    ranked = rank_wallets(trades, top_n=30)

    wallet_texts: dict[str, list[str]] = {}
    wallet_source_row: dict[str, dict[str, Any]] = {}
    for row in apify_items:
        blob = _text_blob(row)
        w = str(row.get("wallet") or row.get("address") or row.get("proxyWallet") or "")
        if w:
            if w not in wallet_source_row:
                wallet_source_row[w] = row
        if w and blob:
            wallet_texts.setdefault(w, []).append(blob)

    corpus = " ".join(_text_blob(r) for r in apify_items)
    corpus_niches = score_text_for_niches(corpus) if corpus.strip() else {}

    digest_mode = "market_trades"
    if apify_items and all(
        (r.get("proxyWallet") or r.get("wallet"))
        and not (r.get("marketId") or r.get("market_id") or r.get("slug"))
        for r in apify_items
    ):
        if any(r.get("rank") is not None for r in apify_items):
            digest_mode = "leaderboard_aggregate"

    enriched = []
    for r in ranked:
        w = r["wallet"]
        texts = wallet_texts.get(w, [])
        niche_scores: dict[str, float] = {}
        for t in texts:
            for k, v in score_text_for_niches(t).items():
                niche_scores[k] = niche_scores.get(k, 0.0) + v
        top = sorted(niche_scores.items(), key=lambda x: -x[1])[:5]
        row0 = wallet_source_row.get(w) or {}
        lb_extra: dict[str, Any] = {}
        if row0.get("rank") is not None:
            lb_extra = {
                "leaderboard_rank": row0.get("rank"),
                "pnl_usd": row0.get("pnl"),
                "volume_usd": row0.get("vol"),
                "display_name": row0.get("userName") or row0.get("user_name"),
            }
        enriched.append({**r, "niche_scores": niche_scores, "top_niches": top, **lb_extra})

    return {
        "source": "apify_polymarket_scraper",
        "digest_mode": digest_mode,
        "digest_notes": (
            "Per-trader niche tags (NBA, politics, …) need market/event text per wallet. "
            "Leaderboard actors only return aggregate PnL/volume — run a market scraper "
            "(e.g. dadhalfdev/polymarket-scraper) for rows with market_question/event_title, "
            "or merge data in a follow-up step. "
            "corpus_niche_scores reflects all market text in this dataset (often empty for leaderboard-only runs)."
        ),
        "corpus_niche_scores": corpus_niches,
        "trader_count": len({t.wallet for t in trades}),
        "ranked_traders": enriched,
    }


def save_digest(path: Path, digest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(digest, indent=2), encoding="utf-8")
