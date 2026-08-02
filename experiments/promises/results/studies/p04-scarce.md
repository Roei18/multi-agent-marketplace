# Scarce supply — p = 0.4

Lower the arrival probability to **p = 0.4** (mean 0.67 goods/round, ~60% empty rounds). 

**Setup:** 8 sellers × 16 buyers × 12 rounds, seed 0. Four arms; matched supply across arms within a seed. Pure post-hoc measurement — `python -m experiments.promises.studies`.

## Deterministic market measurements (no LLM)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| total deals made | 96 | 96 | 96 | 96 |
| seller score — top | 23 | 21 | 6 | 9 |
| seller score — average | 12 | 11.25 | 2.75 | 4.88 |
| buyer score — top | 4 | 4 | 5 | 4 |
| buyer score — average | 3 | 3 | 3 | 2.44 |

*Seller score = net deals (closed − voided); buyer score = goods owned. Top = the winner; average = across all 8 sellers / 16 buyers.*

## LLM-assisted measurements (vagueness judge)

How the closed deals split into vague / true / false. `true`/`false` need the judge to rule the commitment concrete and pin its round; the kept-vs-broken step is then arithmetic over the delivery log.

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| vague % | 79 | 92 | 4 | 0 |
| true % | 5 | 2 | 19 | 41 |
| false % | 16 | 6 | 77 | 59 |

**Per-round distribution** (deals close in odd rounds only; read vague / true / false):

| round | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| 1 | 12 / 2 / 2 | 16 / 0 / 0 | 0 / 5 / 11 | 0 / 8 / 8 |
| 3 | 16 / 0 / 0 | 15 / 1 / 0 | 0 / 4 / 12 | 0 / 5 / 11 |
| 5 | 12 / 2 / 2 | 16 / 0 / 0 | 1 / 1 / 14 | 0 / 7 / 9 |
| 7 | 12 / 0 / 4 | 13 / 0 / 3 | 3 / 3 / 10 | 0 / 5 / 11 |
| 9 | 13 / 1 / 2 | 13 / 0 / 3 | 0 / 3 / 13 | 0 / 4 / 12 |
| 11 | 11 / 0 / 5 | 15 / 1 / 0 | 0 / 2 / 14 | 0 / 10 / 6 |

## Attributor

Fines = concrete promises the attributor voided (delivered late or never). Lying dynamics = the false and vague share among each round's deals.

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| fines given (deals voided) | 0 | 6 | 74 | 57 |

**Lying dynamics — the *attributor* arm, per round** (share of that round's deals that are false / vague):

| round | 1 | 3 | 5 | 7 | 9 | 11 |
|---|---|---|---|---|---|---|
| false % | 0 | 0 | 0 | 19 | 19 | 0 |
| vague % | 100 | 94 | 100 | 81 | 81 | 94 |
