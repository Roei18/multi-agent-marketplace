# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Magentic Marketplace is a Python framework for simulating AI-powered two-sided markets: LLM-driven Customer and Business agents interact through a central platform server following a defined protocol (search, messaging, payments), with all activity persisted to a database for analysis. It's a `uv` workspace with one Python package (`packages/magentic-marketplace`) plus a separate React/TypeScript visualizer (`packages/marketplace-visualizer`).

## Setup

```bash
uv sync --all-extras
source .venv/bin/activate
cp sample.env .env   # fill in OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY etc.
docker compose up -d  # starts Postgres (+ pgAdmin) used by experiments
```

## Common commands

Run from the repo root (poe tasks operate on `packages`):

```bash
# Formatting / linting / types / spelling (Python, packages/magentic-marketplace)
uv run poe format        # ruff format --check --diff
uv run poe format-fix    # ruff format
uv run poe lint          # ruff check
uv run poe lint-fix      # ruff check --fix --unsafe-fixes
uv run poe type          # pyright packages
uv run poe spell         # codespell packages docs
uv run poe check-all     # format + lint + type + spell
uv run poe fix-all       # format-fix + lint-fix

# Tests (pytest config lives in root pyproject.toml; testpaths = packages/magentic-marketplace/tests)
uv run pytest tests
uv run pytest tests/protocol/test_search.py        # single file
uv run pytest tests/protocol/test_search.py::TestX::test_y  # single test
uv run pytest -m "not postgres"                     # skip tests needing a live Postgres
uv run pytest -m "not rnr"                           # skip tests needing rnr extras

# Run an experiment
magentic-marketplace run data/mexican_3_9 --experiment-name test_exp
magentic-marketplace analyze test_exp
magentic-marketplace --help                          # run, analyze, audit, extract-traces, export, list, ui
uv run experiments/example.py                        # scripted experiment + analytics (see this file for the Python API)
```

`packages/marketplace-visualizer` (React/Vite UI, also reachable via `magentic-marketplace ui`):

```bash
cd packages/marketplace-visualizer
npm run dev            # vite dev server
npm run check           # type-check + lint + format:check
npm run fix              # lint:fix + format
```

## Architecture

The package (`packages/magentic-marketplace/src/magentic_marketplace`) has three layers, in order of dependency:

- **`platform/`** — transport-agnostic infra: `MarketplaceLauncher` (starts the server, connects to the DB, ensures init order), the FastAPI `server/` (routes: `/agents/register`, `/actions/protocol`, `/actions/execute`), `database/` (backend-agnostic controller with `postgresql/` and `sqlite/` implementations), `client/` (`MarketplaceClient` used by agents to talk to the server over HTTP), and `agent/base.py` (`BaseAgent`: register → loop calling `step()` → shutdown).
- **`marketplace/`** — the actual marketplace domain built on top of `platform/`: `protocol/` (the `Protocol` implementation and its `search/` algorithms: simple, filtered, lexical, optimal), `actions/` (`Search`, `FetchMessages`, `SendMessage` and the `TextMessage | OrderProposal | Payment` message types), and `agents/` (`CustomerAgent` and `BusinessAgent`, both `BaseSimpleMarketplaceAgent` subclasses implementing `step()` — customer: search → message businesses → evaluate proposals → pay; business: fetch messages → respond / propose / confirm payment).
- **`experiments/`** — orchestration and analysis on top of `marketplace/`: `run_experiment.py` (wires up launcher + agents from a data dir and runs the simulation), `run_analytics.py`/`run_audit.py` (post-hoc analysis of a completed run), `export_experiment.py` (Postgres → SQLite), `extract_agent_llm_traces.py`.

Route handlers in `platform/server` delegate to the configured `Protocol`, which uses the database controller to persist state — so a new action type or search algorithm is added in `marketplace/`, while transport/persistence concerns stay in `platform/`.

Agents are LLM-backed: `marketplace/llm/` wraps provider clients (`clients/`, OpenAI/Anthropic/Gemini) behind a common `base.py`/`functional.py` interface, configured via `LLM_PROVIDER`/`LLM_MODEL`/`LLM_REASONING_EFFORT` env vars (see `sample.env`).

`packages/marketplace-visualizer` is an independent React/Vite/Tailwind app that reads marketplace run data directly from the database (`src/services/database.ts`) to render conversations and agent state; it does not go through the platform server's HTTP API.

### Experiment data layout

`magentic-marketplace run <data_dir>` expects `<data_dir>/businesses/*.yaml` and `<data_dir>/customers/*.yaml` (see `data/mexican_3_9` for a minimal example). Larger generated datasets and the generation scripts live under `data/` (`data_generation_scripts/`); `experiments/` at the repo root holds experiment configs/results per study (`competitive`, `malicious`, `position`, `promises`, `dealrace`, `consideration_set_size`), distinct from the `magentic_marketplace.experiments` Python submodule.

## Testing notes

- `pytest-dotenv` loads `dev.env`; Postgres-dependent tests are marked `postgres` and LLM-provider tests live under `tests/llm/`.
- `skip_ci` marks tests to skip in CI; `rnr` marks tests needing the `rnr` extra.
