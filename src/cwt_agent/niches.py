"""Deterministic niche tagging from market/event text."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

NICHE_KEYWORDS: dict[str, list[str]] = {
    "politics": [
        "election",
        "president",
        "senate",
        "congress",
        "trump",
        "biden",
        "democrat",
        "republican",
        "parliament",
        "prime minister",
        "vote",
    ],
    "nba": ["nba", "lakers", "celtics", "basketball", "playoffs", "finals mvp"],
    "nfl": ["nfl", "super bowl", "touchdown", "quarterback"],
    "weather": ["hurricane", "temperature", "snow", "rain", "cyclone", "tornado"],
    "crypto": ["bitcoin", "ethereum", "btc", "eth", "solana", "defi", "etf"],
    "macro": ["fed", "interest rate", "cpi", "gdp", "recession", "inflation"],
}


def _normalize(text: str) -> str:
    return text.lower()


def score_text_for_niches(text: str) -> dict[str, float]:
    t = _normalize(text)
    scores: dict[str, float] = defaultdict(float)
    for niche, kws in NICHE_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                scores[niche] += 1.0
            if len(kw) <= 5 and re.search(rf"\b{re.escape(kw)}\b", t):
                scores[niche] += 0.5
    return dict(scores)


def dominant_niches(scores: dict[str, float], top_k: int = 3) -> list[tuple[str, float]]:
    if not scores:
        return []
    ordered = sorted(scores.items(), key=lambda x: -x[1])
    return ordered[:top_k]


def tag_trader_from_markets(wallet: str, market_texts: Iterable[str]) -> dict:
    agg: dict[str, float] = defaultdict(float)
    for mt in market_texts:
        for niche, w in score_text_for_niches(mt).items():
            agg[niche] += w
    return {
        "wallet": wallet,
        "niche_scores": dict(agg),
        "top_niches": dominant_niches(dict(agg)),
    }
