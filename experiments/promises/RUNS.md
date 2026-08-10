# RUNS — exactly how each experiment was run

A tracked log of every run so results are reproducible. All runs are 8 sellers ×
16 buyers × 12 rounds (`--sellers 8 --buyers 16 --rounds 12`) unless noted, with the
standard flags (`single_good=True`, `single_round_lock=True` → a closed deal blocks the
buyer for that round **and the next**, i.e. `lock_rounds=1`, 96 deals, deals close in
odd rounds). Supply is a geometric draw with rate `p` (`--p`, default **0.6**);
`p/(1-p)` is mean goods/round. Output file: `results/<arm>_s<seed>[_<tag>][_p<NN>]_<timestamp>.json`
(no `_pNN` when p=0.6). Result JSONs are gitignored.

Arms (`--scenario`): `baseline`, `attributor`, `lawyer_attributor`, `contract_attributor`.

## Models

Set via `.env` (`BaseLLMConfig`): `LLM_PROVIDER=openai` (OpenRouter base_url),
`LLM_REASONING_EFFORT=minimal`, `LLM_MAX_CONCURRENCY=1`.

| label | model id | how selected |
|---|---|---|
| **llama** (default) | `meta-llama/llama-3.3-70b-instruct` | `.env` `LLM_MODEL` |
| **gpt-4o** | `openai/gpt-4o` | `--buyer-model/--seller-model` (agents only) or `LLM_MODEL=openai/gpt-4o` (all incl. judge) |
| **gpt-5** | `openai/gpt-5` | `--buyer-model/--seller-model` |

The **vagueness judge** (the vague/true/false measurement) runs **inline** at the end of
each market run, using the process's default model (`LLM_MODEL`). So a run's verdicts
are judged by whatever `LLM_MODEL` is set for that run.

---

## 1. Main experiment — llama, supply sweep (p = 0.6 / 0.4 / 0.5)

Model **llama** (default `.env`), 8×16×12, arms × seeds as below. Per-arm command:

```bash
python -m experiments.promises.run --scenario <arm> --sellers 8 --buyers 16 --rounds 12 \
    --p <p> --seed <seed> --quiet
```

| supply | `--p` | seeds | notes |
|---|---|---|---|
| standard (supply > demand) | 0.6 (default, omit `--p`) | 0, 1, 2 | **predate the per-deal delivery fix** — buyer holdings are corrected in analysis (delivered-deal count) |
| scarce (demand > supply) | 0.4 | 0, 1, 2 | post-fix |
| stalemate (supply ≈ demand) | 0.5 | 0, 1, 2 | post-fix; run via `results/_p05_watchdog.sh` (resumable, sequential) |

## 2. Post-hoc measurement passes (on the llama runs, default model)

```bash
# buyer trust (0–100, blind to outcome) — seeds 0–2 of p=0.6 and p=0.4
python -m experiments.promises.trust --study p06-standard
python -m experiments.promises.trust --study p04-scarce
# (p=0.5 and other seeds: python -m experiments.promises.trust <run.json> ...)

# seller deception (private reasoning vs public words) — all runs
python -m experiments.promises.deception <run.json> ...   # driver: scratchpad dec_all.py

# deterministic measures (feasibility/breach/over-commit) — no run, computed in analysis
#   experiments.promises.truthfulness.analyze(run)
```

Tables/figures are generated locally by `latex_tables.py` / `latex_figures.py`
(not committed) into `results/studies/*.tex`.

## 3. Model probes — does a stronger model change the behavior? (single seed, small)

Small scale **8 × 4 × 6**, seed **99**, judge left on default (llama) for comparable
measurement. Scenarios: `baseline` (buyer-exploration test) and `attributor`
(seller-under-fines test).

```bash
# gpt-4o agents (driver: results/_probes_watchdog.sh)
python -m experiments.promises.run --scenario <baseline|attributor> \
    --sellers 8 --buyers 4 --rounds 6 --seed 99 \
    --buyer-model openai/gpt-4o --seller-model openai/gpt-4o --tag gpt4o --quiet

# gpt-5 agents (driver: results/_probes5_watchdog.sh)
python -m experiments.promises.run --scenario <baseline|attributor> \
    --sellers 8 --buyers 4 --rounds 6 --seed 99 \
    --buyer-model openai/gpt-5 --seller-model openai/gpt-5 --tag gpt5 --quiet
```

Findings: buyers close on the 1st seller ~100% for llama **and** gpt-4o **and** gpt-5
(no exploration — structural). Under the attributor, gpt-4o/gpt-5 sellers pay **0 fines**
(dodge via vagueness / only-keepable promises); llama's fines were weak-model naivety.

## 4. Full gpt-4o sweep — 3 p × 2 seeds × 4 arms (running)

**Everything on gpt-4o** (agents AND judge) via `LLM_MODEL=openai/gpt-4o`, 8×16×12,
tag `gpt4o`, seeds 0–1, p ∈ {0.6, 0.5, 0.4}. Portable, resumable, 4 arms in parallel
per (seed,p):

```bash
# launch (detached, survives sleep, auto-resumes):
cd <repo>
setsid nohup bash experiments/promises/run_gpt4o_watchdog.sh \
    > experiments/promises/results/_gpt4o_sweep.log 2>&1 < /dev/null &
# the underlying per-run command it issues:
LLM_MODEL=openai/gpt-4o python -m experiments.promises.run --scenario <arm> \
    --sellers 8 --buyers 16 --rounds 12 --p <p> --seed <seed> --tag gpt4o --quiet
```

Files: `results/<arm>_s<seed>_gpt4o[_p<NN>]_<ts>.json`. These are **excluded** from the
llama analysis selectors (`dynamics.newest_fair` / `studies._select` skip `_gpt` names).
