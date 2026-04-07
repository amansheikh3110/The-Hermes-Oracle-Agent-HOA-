"""Kalshi integration placeholder."""

from __future__ import annotations

from cwt_agent.config import Settings


def kalshi_configured(settings: Settings) -> bool:
    return bool(settings.kalshi_api_key_id and settings.kalshi_private_key_path)


def fetch_kalshi_trader_snapshot(settings: Settings) -> dict:
    if not kalshi_configured(settings):
        return {"error": "Kalshi not configured", "traders": []}
    return {
        "error": "Kalshi fetch not implemented yet — add SDK calls in kalshi_stub.py",
        "traders": [],
    }
