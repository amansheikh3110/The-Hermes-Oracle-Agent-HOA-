"""Run Apify Polymarket Scraper actor (see APIFY_POLYMARKET_ACTOR in .env)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apify_client import ApifyClient
from tenacity import retry, stop_after_attempt, wait_exponential

from cwt_agent.config import Settings


class ApifyPolymarketError(RuntimeError):
    pass


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def run_polymarket_scraper(
    settings: Settings,
    run_input: dict[str, Any],
    *,
    timeout_secs: int = 3600,
) -> dict[str, Any]:
    if not settings.apify_token:
        raise ApifyPolymarketError("APIFY_TOKEN is not set in .env")

    client = ApifyClient(settings.apify_token)
    actor_id = settings.apify_polymarket_actor

    run = client.actor(actor_id).call(
        run_input=run_input,
        wait_secs=timeout_secs,
    )

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise ApifyPolymarketError(f"Run finished but no dataset id: {run}")

    items: list[dict[str, Any]] = list(client.dataset(dataset_id).iterate_items())
    return {"run": run, "dataset_items": items}


def save_apify_result(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def load_apify_result(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_run_input(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Apify run input JSON must be an object at the root")
    return data
