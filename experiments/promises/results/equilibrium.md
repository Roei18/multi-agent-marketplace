# promises — equilibrium (4-arm)

12 rounds each, seed 0. Pure post-hoc analysis (no LLM); re-run with `python -m experiments.promises.equilibrium`.

## Convergence (first-third → last-third)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| deals (early→late window) | 32→32 | 32→32 | 32→32 | 32→32 |
| vague rate (early→late) | 0.844→0.75 | 0.906→0.75 | 0.062→0.031 | 0.0→0.0 |
| true rate (early→late) | 0.125→0.25 | 0.062→0.219 | 0.562→0.625 | 0.656→0.969 |

## Buyer trust — return-to-deliverer rate

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| **early → late** | **0.0→0.312** | **0.0→0.406** | **0.028→0.441** | **0.0→0.212** |

## Social welfare

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| true deals (count) | 19 | 15 | 52 | 75 |
| true rate | 0.198 | 0.156 | 0.542 | 0.781 |
| seller-winner profit (net deals) | 20 | 17 | 15 | 13 |
| buyer-champion profit (goods) | 6 | 6 | 6 | 6 |

## Per-arm round-by-round

### baseline (seed 0, 12 rounds)

| round | deals | vague | true | false | return-to-deliverer |
|---|---|---|---|---|---|
| 1 | 16 | 0.875 | 0.125 | 0.0 | 0.0 |
| 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 3 | 16 | 0.812 | 0.125 | 0.062 | 0.0 |
| 4 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 5 | 16 | 0.812 | 0.188 | 0.0 | 0.062 |
| 6 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 7 | 16 | 0.625 | 0.25 | 0.125 | 0.188 |
| 8 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 9 | 16 | 0.812 | 0.188 | 0.0 | 0.25 |
| 10 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 11 | 16 | 0.688 | 0.312 | 0.0 | 0.375 |
| 12 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |

- **converged toward** more deals/round-window (32→32); vagueness ↓ (0.844→0.75); truthfulness ↑ (0.125→0.25)
- **return-to-deliverer** ↑ (0.0→0.312) early→late
- **welfare:** 19 true deals (0.198); seller winner Marrow & Vance profit 20 net deals; buyer champion Merrick Grocery profit 6 goods

### attributor (seed 0, 12 rounds)

| round | deals | vague | true | false | return-to-deliverer |
|---|---|---|---|---|---|
| 1 | 16 | 0.875 | 0.125 | 0.0 | 0.0 |
| 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 3 | 16 | 0.938 | 0.0 | 0.062 | 0.0 |
| 4 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 5 | 16 | 0.688 | 0.188 | 0.125 | 0.062 |
| 6 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 7 | 16 | 0.625 | 0.188 | 0.188 | 0.125 |
| 8 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 9 | 16 | 0.875 | 0.125 | 0.0 | 0.312 |
| 10 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 11 | 16 | 0.625 | 0.312 | 0.062 | 0.5 |
| 12 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |

- **converged toward** more deals/round-window (32→32); vagueness ↓ (0.906→0.75); truthfulness ↑ (0.062→0.219)
- **return-to-deliverer** ↑ (0.0→0.406) early→late
- **welfare:** 15 true deals (0.156); seller winner Marrow & Vance profit 17 net deals; buyer champion Merrick Grocery profit 6 goods

### lawyer_attributor (seed 0, 12 rounds)

| round | deals | vague | true | false | return-to-deliverer |
|---|---|---|---|---|---|
| 1 | 16 | 0.0 | 0.5 | 0.5 | 0.0 |
| 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 3 | 16 | 0.125 | 0.625 | 0.25 | 0.056 |
| 4 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 5 | 16 | 0.062 | 0.438 | 0.5 | 0.125 |
| 6 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 7 | 16 | 0.125 | 0.438 | 0.438 | 0.222 |
| 8 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 9 | 16 | 0.062 | 0.562 | 0.375 | 0.444 |
| 10 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 11 | 16 | 0.0 | 0.688 | 0.312 | 0.438 |
| 12 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |

- **converged toward** more deals/round-window (32→32); vagueness ↓ (0.062→0.031); truthfulness ↑ (0.562→0.625)
- **return-to-deliverer** ↑ (0.028→0.441) early→late
- **welfare:** 52 true deals (0.542); seller winner Orenda Supply profit 15 net deals; buyer champion Tobias Market profit 6 goods

### contract_attributor (seed 0, 12 rounds)

| round | deals | vague | true | false | return-to-deliverer |
|---|---|---|---|---|---|
| 1 | 16 | 0.0 | 0.75 | 0.25 | 0.0 |
| 2 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 3 | 16 | 0.0 | 0.562 | 0.438 | 0.0 |
| 4 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 5 | 16 | 0.0 | 0.75 | 0.25 | 0.062 |
| 6 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 7 | 16 | 0.0 | 0.688 | 0.312 | 0.188 |
| 8 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 9 | 16 | 0.0 | 1.0 | 0.0 | 0.118 |
| 10 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 11 | 16 | 0.0 | 0.938 | 0.062 | 0.312 |
| 12 | 0 | 0.0 | 0.0 | 0.0 | 0.0 |

- **converged toward** more deals/round-window (32→32); vagueness → (0.0→0.0); truthfulness ↑ (0.656→0.969)
- **return-to-deliverer** ↑ (0.0→0.212) early→late
- **welfare:** 75 true deals (0.781); seller winner Orenda Supply profit 13 net deals; buyer champion Wexler Provisions profit 6 goods

