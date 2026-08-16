# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Magentic Marketplace is a Python framework (`packages/magentic-marketplace`) for simulating AI-powered two-sided markets: LLM-backed Customer and Business agents interact through a central platform server following a defined marketplace protocol, with all activity recorded to a database (Postgres or SQLite) for analysis. A React/Vite visualizer (`packages/marketplace-visualizer`) renders simulation traces. `experiments/` holds research studies built on top of the framework (each with its own README/DESIGN doc), and `data/` holds the business/customer datasets those experiments and demos load.

This is a `uv` workspace with one Python member: `packages/magentic-marketplace`. Root-level `pyproject.toml` and the package's own `pyproject.toml` both define `poe` tasks and ruff/pyright config — most commands can be run from repo root.

## Setup

```bash
uv sync --all-extras
source .venv/bin/activate
cp sample.env .env   # then fill in API keys / provider config
docker compose up -d # starts Postgres (+ pgadmin) used by experiments and most tests
```

`.env` configures `LLM_PROVIDER` (`openai` | `gemini` | `anthropic`), `LLM_MODEL`, and Postgres credentials. `dev.env` is a lighter env file specifically for running the `postgres`-marked pytest tests locally (`env_files = ["dev.env"]` in pytest config).

## Common commands

Run all from repo root (uv workspace) unless noted.

```bash
# Quality checks (mirrors CI: ruff.yml, pyright.yml, test.yml)
uv run poe format          # ruff format --check --diff
uv run poe format-fix      # ruff format
uv run poe lint            # ruff check
uv run poe lint-fix        # ruff check --fix --unsafe-fixes
uv run poe type            # pyright packages
uv run poe spell           # codespell
uv run poe check-all       # format + lint + type + spell
uv run poe fix-all         # format-fix + lint-fix

# Tests (from packages/magentic-marketplace, or use testpaths from root)
uv run pytest tests
uv run pytest tests/protocol/test_search.py            # single file
uv run pytest tests/protocol/test_search.py::test_name # single test
uv run pytest -m "not skip_ci and not rnr and not postgres" packages/magentic-marketplace/tests/  # what CI runs

# Run a marketplace experiment via CLI
magentic-marketplace run data/mexican_3_9 --experiment-name test_exp
magentic-marketplace analyze test_exp
magentic-marketplace ui test_exp             # launch visualizer against results
magentic-marketplace list                    # list stored experiments
magentic-marketplace export test_exp -o out/ # Postgres schema -> SQLite file
magentic-marketplace --help                  # full CLI reference

# Visualizer (packages/marketplace-visualizer)
npm run dev / npm run build / npm run check  # type-check + lint + format:check
```

Pytest markers: `skip_ci` (skipped in CI), `rnr` (needs the `rnr` optional extra — sentence-transformers/torch), `postgres` (needs a live Postgres, i.e. `docker compose up -d` + `dev.env` sourced). CI runs everything except those three.

## Architecture

The Python package is split into two layers:

- **`platform/`** — generic, protocol-agnostic infrastructure: `BaseAgent` (registration + step loop), the FastAPI `server/`, the pluggable `database/` controller (postgresql/sqlite backends behind one interface), `MarketplaceLauncher` (wires server + database + lifecycle), and the base `client/` used by agents to talk to the server over HTTP.
- **`marketplace/`** — the concrete marketplace built on that platform: `agents/business` and `agents/customer` (LLM-driven `CustomerAgent`/`BusinessAgent` implementing `step()`), `actions/` (the action types — `Search`, `FetchMessages`, `SendMessage` with `TextMessage`/`OrderProposal`/`Payment` payloads), `protocol/` (the `SimpleMarketplaceProtocol` plus `protocol/search/` algorithms: simple, filtered, lexical, optimal), `llm/` (provider clients for openai/gemini/anthropic), and `shared/models.py` (the `Business`/`Customer`/profile pydantic models).

Flow: an experiment loads business/customer data → `MarketplaceLauncher` starts a FastAPI server backed by a database controller and registers the protocol → each agent (`platform/agent/base.py`) registers itself via `/agents/register` then loops `step()`, executing actions through `/actions/execute` (protocol validates and applies them, e.g. search results, message delivery, payment settlement) → every action, message, and LLM interaction is persisted (`agents`, `actions`, `logs` tables) → `experiments/run_analytics.py` / the `analyze`/`audit`/`extract-traces` CLI subcommands read that data back out for welfare/fairness metrics, prompt-injection audits, and LLM trace extraction.

`experiments/<name>/` directories are standalone research studies (each defines its own runner scripts, results, and README/DESIGN docs) that depend on the `magentic_marketplace` package rather than living inside it — read the experiment's own README before modifying it, since conventions vary per study.

See `docs/concepts/` (overview, platform, agents, marketplace-protocol, experiment-data) for the fuller narrative version of the above, and `docs/usage/` for CLI/env/Python-API reference.
