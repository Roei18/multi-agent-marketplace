# Standard supply — p = 0.6

The reference setting. Each seller draws goods geometrically with arrival probability **p = 0.6** (mean 1.5 goods/round, ~40% empty rounds). Over the game ~144 goods are produced against a maximum buyer demand of 96 (16 buyers × 6 deals), so **supply exceeds demand** — goods are not scarce, and a seller can be late at little cost to the buyer.

> Note: these runs predate the per-deal delivery fix, so a few free-text buyers were over-served — `buyer top` here is inflated by ≤1 (true ceiling is 6). Re-run at p = 0.6 to refresh if an exact baseline is needed.

**Setup:** 8 sellers × 16 buyers × 12 rounds, averaged over seeds [0, 1, 2]. Four arms; matched supply across arms within a seed. Pure post-hoc measurement — `python -m experiments.promises.studies`.

## Deterministic market measurements (no LLM)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| total deals made | 96 | 96 | 96 | 96 |
| seller score — top | 18.67 | 17 | 16.33 | 17 |
| seller score — average | 12 | 11.46 | 9.0 | 10.17 |
| buyer score — top | 7 | 6.67 | 6 | 6 |
| buyer score — average | 5.71 | 5.77 | 5.5 | 5.08 |

*Seller score = net deals (closed − voided); buyer score = goods owned. Top = the winner; average = across all 8 sellers / 16 buyers.*

## LLM-assisted measurements (vagueness judge)

How the closed deals split into vague / true / false. `true`/`false` need the judge to rule the commitment concrete and pin its round; the kept-vs-broken step is then arithmetic over the delivery log.

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| vague % | 86 | 83 | 6 | 0 |
| true % | 12 | 12 | 69 | 85 |
| false % | 2 | 4 | 25 | 15 |

**Per-round distribution** (deals close in odd rounds only; read vague / true / false):

| round | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| 1 | 13.7 / 1.3 / 1 | 14 / 1.3 / 0.7 | 1 / 8.7 / 6.3 | 0 / 12 / 4 |
| 3 | 14.3 / 1.3 / 0.3 | 14.3 / 0.7 / 1 | 1.3 / 11.7 / 2.7 | 0 / 13.3 / 2.7 |
| 4 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0.3 / 0 | 0 / 0 / 0 |
| 5 | 13.3 / 2.7 / 0 | 12.7 / 2.7 / 0.7 | 1 / 10.7 / 4 | 0 / 12 / 4 |
| 6 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0.3 / 0 | 0 / 0 / 0 |
| 7 | 13.7 / 1.7 / 0.7 | 13 / 2 / 1 | 1.7 / 11 / 3 | 0 / 13.7 / 2.3 |
| 8 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0.3 / 0 | 0 / 0 / 0 |
| 9 | 14 / 2 / 0 | 15 / 0.7 / 0.3 | 0.3 / 12.3 / 3 | 0 / 15.3 / 0.7 |
| 10 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0.3 / 0 | 0 / 0 / 0 |
| 11 | 13.3 / 2.7 / 0 | 10.7 / 4.7 / 0.7 | 0.3 / 10.7 / 4.7 | 0 / 15 / 1 |
| 12 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0.3 | 0 / 0 / 0 |

## Attributor

Fines = concrete promises the attributor voided (delivered late or never). Lying dynamics = the false and vague share among each round's deals.

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| fines given (deals voided) | 0 | 4.33 | 24 | 14.67 |

**Lying dynamics — the *attributor* arm, per round** (share of that round's deals that are false / vague):

| round | 1 | 3 | 5 | 7 | 9 | 11 |
|---|---|---|---|---|---|---|
| false % | 4 | 6 | 4 | 6 | 2 | 4 |
| vague % | 88 | 89 | 79 | 81 | 94 | 67 |
