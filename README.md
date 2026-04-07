The Hermes Oracle Research Agent (HORA) 

Python CLI style prediction-market research: pull Polymarket data via **Apify**, rank traders into a **digest**, embed market text in **Chroma** for **RAG**, and chat with **OpenRouter** (optionally **Hermes**) to synthesize insights.

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [CLI reference](#cli-reference)
- [Data pipeline](#data-pipeline)
- [Project layout](#project-layout)
- [Examples](#examples)
- [Optional: Hermes](#optional-hermes)
- [Kalshi](#kalshi)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [License](#license)

---

## Features

- **Apify integration** — run Polymarket actors (leaderboard or market search) with JSON input from `examples/`.
- **Trader digest** — deterministic scoring and ranking from wallet-level Apify rows → `data/traders_digest.json`.
- **RAG** — Chroma persistent store; ingest plain `.txt` or saved Apify JSON (with `dataset_items`); embeddings via OpenRouter.
- **Chat** — single-shot `cwt chat` or interactive `cwt chat-repl`; digest + RAG injected into system context.
- **Verification** — `cwt verify` runs smoke checks for keys, embeddings, Apify, Chroma, and optional Hermes.

---

## Architecture

```
Apify (Polymarket actors)
        │
        ├─► data/raw/*.json (run + dataset_items)
        │
        ├─► build-digest ──► traders_digest.json (ranked traders, metadata)
        │
        └─► rag-ingest ──► Chroma (embedded chunks for semantic search)

OpenRouter (chat + embeddings) ◄── cwt chat / chat-repl
        │
        Hermes (optional) ──► AIAgent with memory not disabled
```

- **Digest** answers structured questions: *who* ranks well on heuristics (wallets, PnL/volume when present).
- **RAG** answers fuzzy questions: *what themes / markets* appear in ingested text.
- **Chat** combines both when both exist.

---

## Requirements

- **Python** 3.11+ (3.12 recommended)
- **Accounts / keys**
  - [OpenRouter](https://openrouter.ai/) API key for chat and embeddings
  - [Apify](https://apify.com/) token for actors (pricing depends on each actor)
- **Optional:** Hermes extra for agent-style chat (`pip install -e ".[hermes]"`)

---

## Installation

```bash
git clone <your-repo-url>
cd Internship_Project
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pip install -e ".[hermes]"  # optional
```

Copy `.env.example` to `.env` and set secrets (see [Configuration](#configuration)).

```bash
cwt doctor
cwt verify
```

---

## Configuration

Environment variables are loaded from the project `.env` (project root). See `.env.example` for all keys.

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | OpenRouter key (used for chat and embeddings). |
| `OPENROUTER_CHAT_MODEL` | Chat model id on OpenRouter. |
| `OPENROUTER_EMBEDDING_MODEL` | Embedding model id for Chroma. |
| `OPENROUTER_EMBEDDING_FALLBACK_MODEL` | Optional; if the primary embedding model fails. |
| `APIFY_TOKEN` | Apify API token. |
| `APIFY_POLYMARKET_ACTOR` | Actor id for `cwt apify-polymarket` (must match your input JSON). |
| `CWT_DATA_DIR` | Data root (default `./data`). |
| `CHROMA_COLLECTION` | Chroma collection name. |
| `KALSHI_*` | Optional Kalshi credentials (see [Kalshi](#kalshi)). |

---

## CLI reference

| Command | Description |
|---------|-------------|
| `cwt doctor` | Print project paths and config hints. |
| `cwt check-config` | Show non-secret config status. |
| `cwt verify` | Smoke tests (OpenRouter, embeddings, Apify, Chroma, Hermes if installed). |
| `cwt apify-polymarket <input.json> [--out path]` | Run configured Apify actor; save full payload + `dataset_items`. |
| `cwt build-digest [--from raw.json]` | Build `traders_digest.json` from saved Apify output. |
| `cwt rag-ingest <file>` | Ingest `.txt` or Apify JSON with `dataset_items` into Chroma. |
| `cwt chroma-reset` | Delete the Chroma collection (e.g. after embedding model change). |
| `cwt chat "message"` | Single-turn chat with digest + RAG in context. |
| `cwt chat-repl` | Multi-turn REPL (`/exit`, `/reset`). |
| `cwt kalshi-status` | Show Kalshi stub / config status. |

---

## Data pipeline

### Two complementary paths

You typically need **two Apify runs** (same or different actors), because **one** actor id is set in `APIFY_POLYMARKET_ACTOR` per run.

| Goal | Output | Command chain |
|------|--------|----------------|
| **Ranked traders** (wallets, PnL/volume when the actor provides them) | `data/traders_digest.json` | Apify (leaderboard) → `cwt build-digest` |
| **Market / event text** for themes and RAG | Chroma vectors | Apify (market search) → `cwt rag-ingest` |

### A — Leaderboard → digest

1. Set `APIFY_POLYMARKET_ACTOR` to a **leaderboard** actor (e.g. `saswave/polymarket-leaderboard-scraper`).
2. Run: `cwt apify-polymarket examples/apify_polymarket_input.json`  
   (Input shape: `leaderboard_categories`, `leaderboard_rangedate`, `leaderboard_section`, `max_results`.)
3. Run: `cwt build-digest`  
   (Reads default `data/raw/apify_polymarket_last.json` unless `--from` is set.)
4. Inspect `data/traders_digest.json` (`ranked_traders`, `digest_mode`, `digest_notes`).

### B — Market search → RAG

1. Set `APIFY_POLYMARKET_ACTOR` to your **market** actor (e.g. `fatihtahta/polymarket-scraper-mo`).
2. Edit `examples/apify_polymarket_input_fatihtahta.json` (`queries`, `startUrls`, `limit`, `status`, `sortBy`, `frequency`, `proxyConfiguration`).
3. Run: `cwt apify-polymarket examples/apify_polymarket_input_fatihtahta.json --out data/raw/apify_polymarket_markets.json`
4. Run: `cwt rag-ingest data/raw/apify_polymarket_markets.json --event polymarket-markets`  
   JSON files that include `dataset_items` are flattened to text automatically for embedding.

Repeat step 3–4 with different outputs and `--out` paths if you run multiple keyword batches.

### C — Chat

```bash
cwt chat "Summarize top traders from the digest and main themes from retrieved market context."
cwt chat-repl
```

### Digest vs RAG (why two steps)

- **`build-digest`** applies **structured ranking logic** to trader-shaped rows. It produces a **single JSON** digest for the “who to study” question.
- **`rag-ingest`** stores **semantic chunks** for “what markets / themes are discussed.” It does **not** replace the digest for wallet ranking.

### Niche-style keywords

`src/cwt_agent/niches.py` defines keyword buckets (e.g. politics, sports, macro). When Apify rows contain **market text fields**, digest can aggregate `corpus_niche_scores` and per-wallet hints when text is available. Pure leaderboard rows often lack per-market text; market scrapes improve theme coverage.

---

## Project layout

```
Internship_Project/
├── pyproject.toml
├── .env.example
├── README.md
├── src/cwt_agent/
│   ├── cli.py              # Typer entrypoint
│   ├── config.py           # Settings / paths
│   ├── openrouter_client.py
│   ├── rag_store.py        # Chroma + embeddings
│   ├── digest.py           # Digest from Apify items
│   ├── scoring.py          # Trader heuristics
│   ├── niches.py           # Keyword niches
│   ├── apify_polymarket.py
│   ├── apify_market_text.py # Flatten market JSON → text for RAG
│   ├── hermes_chat.py      # Optional Hermes
│   ├── kalshi_stub.py
│   └── verify_smoke.py
├── tests/
├── examples/
│   ├── apify_polymarket_input.json              # Leaderboard actor
│   ├── apify_polymarket_input_fatihtahta.json   # Market-search actor
│   ├── sample_event_notes.txt
│   ├── sample_session_input.json
│   └── sample_session_output.template.json
└── data/                   # gitignored except structure; created at runtime
    ├── raw/                # Apify JSON outputs (your runs)
    ├── chroma/             # Persistent vector store
    └── traders_digest.json
```

Additional documentation in the repo may include `SETUP_STEP_BY_STEP.txt`, `CWT_Internship_Build_Procedure.txt`, and project-specific reports.

---

## Examples

| File | Use |
|------|-----|
| `examples/apify_polymarket_input.json` | Input for **leaderboard** actors (wallet rankings). |
| `examples/apify_polymarket_input_fatihtahta.json` | Input for **market search** actors (`startUrls`, `queries`, `limit`, etc.). |
| `examples/sample_event_notes.txt` | Minimal text for testing `rag-ingest` without Apify. |
| `examples/sample_session_input.json` | Template for session metadata (if used in your workflow). |

---

## Optional: Hermes

Install with `pip install -e ".[hermes]"`. Chat uses Hermes `AIAgent` when available (`skip_memory=False`), delegating optional persistent memory to Hermes (`~/.hermes/` when enabled in Hermes config). This is separate from digest and Chroma.

---

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| `cwt chat` sees empty traders | Run `cwt build-digest` after the leaderboard Apify run; chat reads `traders_digest.json`, not raw Apify JSON alone. |
| Chroma / embedding dimension errors | After changing `OPENROUTER_EMBEDDING_MODEL`, run `cwt chroma-reset` and re-ingest. |
| `cwt verify` fails OpenRouter chat | Confirm `OPENROUTER_API_KEY`; try another `OPENROUTER_CHAT_MODEL` if a provider returns errors. |
| Apify actor fails | Check actor rental/trial, input JSON, and `APIFY_POLYMARKET_ACTOR` matches the input schema. |
| Hermes “No .env file found” | Often harmless if keys are in the environment; `cwt verify` should still pass. |

---

## Development

```bash
pytest
ruff check src tests
```

---

## Sample outputs (tracked)

Generated analysis from scraped data is kept under **`Output/`** (e.g. `final_report.md`, `polymarket_leaderboard_report.txt`) so clones include example deliverables. Reproduce or extend by following the [Data pipeline](#data-pipeline) with your own keys.

**Internship submission write-ups** (Word/PDF, screenshot appendices) are prepared **locally** and are **not** part of this repository.

## License

MIT
