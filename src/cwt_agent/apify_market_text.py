"""Turn Apify Polymarket market dataset items (e.g. fatihtahta) into plain text for RAG."""

from __future__ import annotations

import json
from typing import Any


def _tag_labels(tags: Any) -> str:
    if not isinstance(tags, list):
        return ""
    labs: list[str] = []
    for t in tags:
        if isinstance(t, dict) and isinstance(t.get("label"), str):
            labs.append(t["label"])
        elif isinstance(t, str):
            labs.append(t)
    return ", ".join(labs)


def _flatten_one(item: dict[str, Any]) -> str:
    lines: list[str] = []
    if isinstance(item.get("query"), str):
        lines.append(f"search_query: {item['query']}")
    if isinstance(item.get("source"), str):
        lines.append(f"source: {item['source']}")

    pm = item.get("parentMarket")
    if isinstance(pm, dict):
        for k in ("title", "slug", "eventUrl"):
            v = pm.get(k)
            if isinstance(v, str) and v.strip():
                lines.append(f"event_{k}: {v}")
        tl = _tag_labels(pm.get("tags"))
        if tl:
            lines.append(f"event_tags: {tl}")

    m = item.get("market")
    if isinstance(m, dict):
        q = m.get("question")
        if isinstance(q, str) and q.strip():
            lines.append(f"market_question: {q}")
        outs = m.get("outcomes")
        if isinstance(outs, list) and outs:
            lines.append("outcomes: " + ", ".join(str(x) for x in outs[:12]))
        add = m.get("additionalFields")
        if isinstance(add, dict):
            desc = add.get("description")
            if isinstance(desc, str) and desc.strip():
                lines.append(f"description: {desc[:4000]}")

    # dadhalfdev / other flat rows
    for key in (
        "market_question",
        "market_description",
        "event_title",
        "event_category",
        "title",
        "question",
        "description",
    ):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            lines.append(f"{key}: {v[:4000]}")

    if not lines:
        lines.append(json.dumps(item, default=str)[:8000])
    return "\n".join(lines).strip()


def apify_dataset_items_to_document(items: list[dict[str, Any]], *, separator: str = "\n\n---\n\n") -> str:
    parts = [_flatten_one(row) for row in items if isinstance(row, dict)]
    return separator.join(p for p in parts if p)


def text_from_apify_saved_json(raw: dict[str, Any]) -> str:
    items = raw.get("dataset_items")
    if not isinstance(items, list):
        return ""
    dict_items = [x for x in items if isinstance(x, dict)]
    return apify_dataset_items_to_document(dict_items)
