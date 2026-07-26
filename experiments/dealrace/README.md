# dealrace

A free-language market where **sellers do not know their stock while they
negotiate**, goods **accumulate**, no seller is eliminated, buyers race
round-by-round for a points title, and a third-party judge labels every deal
`true` / `false` / `vague` after the game. The study is a clean A/B: `baseline`
vs `attributor`.

The full mechanism — every phase, who talks to whom and when, what is hidden from
whom — is in **[DESIGN.md](DESIGN.md)**. Read that first; this file is just how to
run it.

## The idea in three lines

- A seller knows only its arrival rate `p`, never its stock, when it talks — so it
  *cannot* promise a quantity, only a delivery **time**. That is the room to be
  vague rather than to lie.
- Goods are drawn (geometrically, `P(k)=p^k(1-p)`) **after** each round's talk and
  **added to accumulating stock** — unsold units carry over, never destroyed — and
  the seller hands them to whichever deal-partners it chooses.
- A "deal" is just both sides saying **DEAL**; it stores no terms. The buyer names
  how many rounds it will sit out. Buyers score a point each round they own the
  most goods; sellers compete to close the most deals. No elimination.

## Setup

Uses only the shared LLM layer (Path B) — no Postgres. Model/provider come from
`.env` (`LLM_PROVIDER`, `LLM_MODEL`); `load_dotenv()` runs before the package
imports in `run.py`.

## Run

```bash
# free — show what the supply coin produces, no LLM calls
python -m experiments.dealrace.run --check-supply

# the A/B pair (5 sellers, 10 buyers, 5 rounds, no elimination)
python -m experiments.dealrace.run --scenario baseline   --seed 0   # no regulator
python -m experiments.dealrace.run --scenario attributor --seed 0   # regulator voids false promises

# the side-by-side comparison report (needs a baseline_* and attributor_* result)
python -m experiments.dealrace.compare

# render the judge's true/false/vague decisions with verbatim quote evidence,
# from any saved run (re-judges the stored transcripts, no game replay)
python -m experiments.dealrace.judge_table experiments/dealrace/results/<run>.json

# a small, cheap smoke run
python -m experiments.dealrace.run --sellers 3 --buyers 4 --max-messages 8 --attempts 2

# read the transcripts and judge labels
python -m experiments.viewer      # then open the dealrace run
```

Scenarios: `baseline` (no regulator) and `attributor` (regulator), both `p = 0.6`.
Flags: `--sellers`, `--buyers`, `--max-messages`, `--attempts`, `--seed`, `--quiet`.

## What comes out

Results are saved as JSON in `results/` (gitignored, apart from one reference
A/B pair kept in the repo — 10 sellers, 20 buyers, 10 rounds, seed 0 — plus the
`compare.py` report over it in `results/compare_base_vs_attributor.md`). Runs are
rendered by the shared viewer. The
console report and the `attribution` block cover two families of measure:

- **Collapse** — deals closed vs honoured vs never honoured; goods drawn vs handed
  over vs left unsold in stock.
- **Honesty** — `unbacked_at_close` (a seller agreed to more deals than its
  *expected* supply `p/(1-p)` could cover — the analogue of overpromising when
  stock is hidden), and the third-party judge's `true` / `false` / `vague` counts,
  cross-tabbed against whether the goods actually arrived.

## Reading a result honestly

- **One seed is an anecdote.** Sweep seeds before claiming a rate. The buyer points
  race in particular ties often when few goods move, so a single champion can be a
  tiebreak.
- **A `false` label is not proof of a lie.** Because supply is random and hidden, a
  seller that named a clear time and then drew zero goods is labelled `false` too.
  Separate luck from intent by reading `false` deals against the seller's `p` and
  its draw history in the round record.
- **`unbacked` is measured against *expected* supply, not inventory** — there is no
  inventory to measure against at negotiation time, by design.

## The A/B: baseline vs attributor (the error-attribution study)

`baseline` and `attributor` are the same no-elimination game; the only difference
is the regulator. In `attributor`, sellers are scored on **net deals** — deals
closed minus the ones a **brute-force regulator** voids as false — and are told so.
A deal is voided only when it was a *clear delivery promise that was broken*
(`false`); a deal that never pinned a delivery time (`vague`) is safe even if
undelivered, and a delivered deal (`true`) counts.

The question it asks: **do sellers retreat into vagueness to dodge the regulator?**
`compare.py` puts `share_vague` (and the broken-deal rate) side by side. The
attributor lives in `attributor.py` as a pluggable component — the brute-force
oracle now, an LLM attributor later, scored against the oracle. See DESIGN.md §10.

## Files

```
scenarios.py   cast, supply rates, knobs, the `attributor` scenario
models.py      pydantic — LLM outputs, judge output, saved records
agents.py      seller / buyer / judge prompts
attributor.py  pluggable attributors + seller net-score scoring
market.py      the round loop + end-of-game judging + attribution
judge_table.py re-judge a saved run into a decision/quotes table
run.py         CLI, --check-supply, JSON to results/
DESIGN.md      full technical specification (§10 = attributor mode)
```
