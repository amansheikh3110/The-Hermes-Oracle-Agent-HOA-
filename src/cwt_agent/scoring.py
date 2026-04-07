"""Deterministic trader consistency heuristics."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any, Iterable


@dataclass
class TradeLite:
    wallet: str
    market_id: str
    pnl_percent: float | None
    notional: float | None
    resolved_win: bool | None


def trades_from_apify_items(items: Iterable[dict[str, Any]]) -> list[TradeLite]:
    out: list[TradeLite] = []
    for row in items:
        wallet = str(
            row.get("wallet")
            or row.get("address")
            or row.get("user")
            or row.get("profileAddress")
            or row.get("proxyWallet")
            or "",
        )
        market_id = str(row.get("marketId") or row.get("market_id") or row.get("slug") or row.get("id") or "")
        # Leaderboard actors (e.g. fatihtahta/polymarket-scraper-mo) return one row per
        # trader with proxyWallet + pnl/vol but no per-market id — still rankable as one synthetic "trade".
        if wallet and not market_id:
            if row.get("rank") is not None and (
                row.get("pnl") is not None or row.get("vol") is not None or row.get("proxyWallet")
            ):
                market_id = f"leaderboard:{row.get('rank')}"
        pnl = row.get("percentPnl") or row.get("pnlPercent") or row.get("pnl")
        try:
            pnl_f = float(pnl) if pnl is not None else None
        except (TypeError, ValueError):
            pnl_f = None
        notional = row.get("notional") or row.get("size") or row.get("amount") or row.get("vol")
        try:
            n_f = float(notional) if notional is not None else None
        except (TypeError, ValueError):
            n_f = None
        resolved = row.get("resolvedWin")
        if resolved is None:
            resolved = row.get("win")
        rw: bool | None
        if resolved is None:
            rw = None
        else:
            rw = bool(resolved)
        if wallet and market_id:
            out.append(
                TradeLite(
                    wallet=wallet,
                    market_id=market_id,
                    pnl_percent=pnl_f,
                    notional=n_f,
                    resolved_win=rw,
                )
            )
    return out


def consistency_score(trades: list[TradeLite]) -> float:
    if not trades:
        return 0.0
    wins = [t for t in trades if t.resolved_win is not None]
    win_rate = (sum(1 for t in wins if t.resolved_win) / len(wins)) if wins else 0.5
    pnls = [t.pnl_percent for t in trades if t.pnl_percent is not None]
    if len(pnls) >= 2:
        vol = pstdev(pnls)
        stability = 1.0 / (1.0 + max(vol, 1e-6) / 10.0)
    elif len(pnls) == 1:
        stability = 0.6
    else:
        stability = 0.4
    size_bonus = min(len(trades) / 50.0, 1.0)
    return 0.45 * win_rate + 0.35 * stability + 0.20 * size_bonus


def aggregate_by_wallet(trades: list[TradeLite]) -> dict[str, list[TradeLite]]:
    buckets: dict[str, list[TradeLite]] = {}
    for t in trades:
        buckets.setdefault(t.wallet, []).append(t)
    return buckets


def rank_wallets(trades: list[TradeLite], top_n: int = 20) -> list[dict[str, Any]]:
    by_w = aggregate_by_wallet(trades)
    ranked: list[tuple[str, float, int]] = []
    for w, ts in by_w.items():
        ranked.append((w, consistency_score(ts), len(ts)))
    ranked.sort(key=lambda x: (-x[1], -x[2]))
    rows = []
    for wallet, score, n in ranked[:top_n]:
        pnls = [t.pnl_percent for t in by_w[wallet] if t.pnl_percent is not None]
        rows.append(
            {
                "wallet": wallet,
                "consistency_score": round(score, 4),
                "trade_rows": n,
                "mean_pnl_percent": round(mean(pnls), 4) if pnls else None,
            }
        )
    return rows
