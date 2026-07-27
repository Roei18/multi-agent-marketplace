# promises — equilibrium (4-arm)

12 rounds each, seed 0. Pure post-hoc analysis (no LLM); re-run with `python -m experiments.promises.equilibrium`.

## Convergence (first-third → last-third)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| deals (early→late window) | 21→20 | 25→18 | 21→19 | 17→22 |
| vague rate (early→late) | 0.952→0.65 | 0.96→0.778 | 0.0→0.105 | 0.0→0.0 |
| true rate (early→late) | 0.048→0.25 | 0.04→0.222 | 0.81→0.842 | 0.294→0.227 |

## Buyer trust — return-to-deliverer rate

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| **early → late** | **0.048→0.25** | **0.0→0.389** | **0.042→0.348** | **0.0→0.087** |

## Social welfare

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| true deals (count) | 9 | 7 | 49 | 16 |
| true rate | 0.138 | 0.108 | 0.79 | 0.267 |
| seller-winner profit (net deals) | 15 | 17 | 11 | 5 |
| buyer-champion profit (goods) | 5 | 5 | 4 | 9 |

## Per-arm round-by-round

### baseline (seed 0, 12 rounds)

| round | deals | vague | true | false | return-to-deliverer |
|---|---|---|---|---|---|
| 1 | 16 | 0.938 | 0.062 | 0.0 | 0.0 |
| 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 3 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 4 | 5 | 1.0 | 0.0 | 0.0 | 0.2 |
| 5 | 9 | 0.667 | 0.111 | 0.222 | 0.333 |
| 6 | 2 | 0.5 | 0.0 | 0.5 | 0.0 |
| 7 | 5 | 1.0 | 0.0 | 0.0 | 0.0 |
| 8 | 8 | 0.75 | 0.25 | 0.0 | 0.0 |
| 9 | 3 | 1.0 | 0.0 | 0.0 | 0.333 |
| 10 | 6 | 0.667 | 0.333 | 0.0 | 0.0 |
| 11 | 6 | 0.5 | 0.5 | 0.0 | 0.167 |
| 12 | 5 | 0.6 | 0.0 | 0.4 | 0.6 |

- **converged toward** fewer deals/round-window (21→20); vagueness ↓ (0.952→0.65); truthfulness ↑ (0.048→0.25)
- **return-to-deliverer** ↑ (0.048→0.25) early→late
- **welfare:** 9 true deals (0.138); seller winner Marrow & Vance profit 15 net deals; buyer champion Quill & Basket profit 5 goods

### attributor (seed 0, 12 rounds)

| round | deals | vague | true | false | return-to-deliverer |
|---|---|---|---|---|---|
| 1 | 16 | 0.938 | 0.062 | 0.0 | 0.0 |
| 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 3 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 4 | 9 | 1.0 | 0.0 | 0.0 | 0.0 |
| 5 | 7 | 0.857 | 0.0 | 0.143 | 0.143 |
| 6 | 1 | 1.0 | 0.0 | 0.0 | 0.0 |
| 7 | 6 | 1.0 | 0.0 | 0.0 | 0.0 |
| 8 | 8 | 0.75 | 0.25 | 0.0 | 0.25 |
| 9 | 2 | 1.0 | 0.0 | 0.0 | 0.0 |
| 10 | 5 | 1.0 | 0.0 | 0.0 | 0.6 |
| 11 | 8 | 0.625 | 0.375 | 0.0 | 0.25 |
| 12 | 3 | 0.667 | 0.333 | 0.0 | 0.667 |

- **converged toward** fewer deals/round-window (25→18); vagueness ↓ (0.96→0.778); truthfulness ↑ (0.04→0.222)
- **return-to-deliverer** ↑ (0.0→0.389) early→late
- **welfare:** 7 true deals (0.108); seller winner Orenda Supply profit 17 net deals; buyer champion Tobias Market profit 5 goods

### lawyer_attributor (seed 0, 12 rounds)

| round | deals | vague | true | false | return-to-deliverer |
|---|---|---|---|---|---|
| 1 | 16 | 0.0 | 0.75 | 0.25 | 0.0 |
| 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 3 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 4 | 5 | 0.0 | 1.0 | 0.0 | 0.2 |
| 5 | 8 | 0.0 | 0.625 | 0.375 | 0.25 |
| 6 | 3 | 0.333 | 0.333 | 0.333 | 0.0 |
| 7 | 2 | 0.0 | 1.0 | 0.0 | 0.0 |
| 8 | 9 | 0.0 | 0.889 | 0.111 | 0.2 |
| 9 | 3 | 0.0 | 0.667 | 0.333 | 0.333 |
| 10 | 4 | 0.0 | 1.0 | 0.0 | 0.2 |
| 11 | 8 | 0.25 | 0.75 | 0.0 | 0.545 |
| 12 | 4 | 0.0 | 1.0 | 0.0 | 0.0 |

- **converged toward** fewer deals/round-window (21→19); vagueness ↑ (0.0→0.105); truthfulness ↑ (0.81→0.842)
- **return-to-deliverer** ↑ (0.042→0.348) early→late
- **welfare:** 49 true deals (0.79); seller winner Orenda Supply profit 11 net deals; buyer champion Wexler Provisions profit 4 goods

### contract_attributor (seed 0, 12 rounds)

| round | deals | vague | true | false | return-to-deliverer |
|---|---|---|---|---|---|
| 1 | 16 | 0.0 | 0.312 | 0.688 | 0.0 |
| 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 3 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 4 | 1 | 0.0 | 0.0 | 1.0 | 0.0 |
| 5 | 3 | 0.0 | 1.0 | 0.0 | 0.0 |
| 6 | 8 | 0.0 | 0.0 | 1.0 | 0.125 |
| 7 | 7 | 0.0 | 0.429 | 0.571 | 0.143 |
| 8 | 3 | 0.0 | 0.0 | 1.0 | 0.0 |
| 9 | 5 | 0.0 | 0.2 | 0.8 | 0.2 |
| 10 | 6 | 0.0 | 0.333 | 0.667 | 0.0 |
| 11 | 7 | 0.0 | 0.143 | 0.857 | 0.143 |
| 12 | 4 | 0.0 | 0.25 | 0.75 | 0.0 |

- **converged toward** more deals/round-window (17→22); vagueness → (0.0→0.0); truthfulness ↓ (0.294→0.227)
- **return-to-deliverer** ↑ (0.0→0.087) early→late
- **welfare:** 16 true deals (0.267); seller winner Redmond Wholesale profit 5 net deals; buyer champion Tobias Market profit 9 goods

