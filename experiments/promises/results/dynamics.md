# promises — market dynamics (4-arm, lock=1 version)

8×16×12, averaged over seeds [0, 1, 2]. **2-round-blocked: a closed deal also blocks the next round → 96 deals, closes odd rounds only.** Pure post-hoc, no LLM; `python -m experiments.promises.dynamics`.

## 1 — Deal distribution (vague / true / false)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| total deals | 96 | 96 | 96 | 96 |
| vague % | 86 | 83 | 6 | 0 |
| true % | 12 | 12 | 69 | 85 |
| false % | 2 | 4 | 25 | 15 |

## 2 — Social welfare (top vs average agent)

*Seller score = net deals (closed − voided); buyer score = goods owned. Gap = how far the winner runs from the average.*

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| seller: top | 18.67 | 17 | 16.33 | 17 |
| seller: average | 12 | 11.46 | 9.0 | 10.17 |
| seller: gap (top−avg) | 6.67 | 5.54 | 7.34 | 6.83 |
| seller: top/avg | 1.56 | 1.49 | 1.84 | 1.66 |
| buyer: top | 7 | 6.67 | 6 | 6 |
| buyer: average | 5.71 | 5.77 | 5.5 | 5.08 |
| buyer: gap (top−avg) | 1.29 | 0.9 | 0.5 | 0.92 |
| buyer: top/avg | 1.22 | 1.15 | 1.09 | 1.18 |
| true deals (welfare good) | 11.7 | 12 | 66.3 | 81.3 |

## 3 — Negotiations & trust

*A buyer gets ≤3 approaches/round, one seller each; closing locks it for the round (so attempts-to-close ≤ 3 by design).*

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| attempts to close (mean) | 1.0 | 1.0 | 1.08 | 1.03 |
| closed on 1st seller % | 100 | 100 | 92 | 97 |
| distinct sellers/buyer over game (of 8) | 4.35 | 4.62 | 4.6 | 4.77 |
| conversation length (mean turns, cap 12) | 8.47 | 8.58 | 8.53 | 7.2 |
|   — closed-with-deal | 8.47 | 8.58 | 8.4 | 7.19 |
| close rate | 1.0 | 1.0 | 0.92 | 0.97 |
| walked away (no deal, count) | 0.3 | 0.3 | 8.7 | 2.7 |
| attributor fines given (deals voided) | 0 | 4.33 | 24 | 14.67 |

### Trust — do buyers reward deliverers and avoid let-downs?

*return-to-X rate = share of ALL approaches that go to a seller who had already X'd this buyer in an earlier round. re-approach-after-X = of (seller,buyer) pairs where X happened, share the buyer approached that seller again afterward. delivery = got a good; let-down = a prior deal that never delivered.*

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| return-to-deliverer rate | 0.23 | 0.2 | 0.23 | 0.17 |
| return-to-let-down rate | 0.02 | 0.01 | 0.02 | 0.06 |
| re-approach AFTER a delivery | 0.27 (n=67) | 0.22 (n=72) | 0.31 (n=66) | 0.21 (n=67) |
| re-approach AFTER a let-down | 0.12 (n=5) | 0.1 (n=4) | 0.2 (n=8) | 0.39 (n=13) |

## Per-round deal distribution

### baseline (seed avg, 96 deals)

| round | deals | vague | true | false |
|---|---|---|---|---|
| 1 | 16 | 13.7 | 1.3 | 1 |
| 2 | 0 | 0 | 0 | 0 |
| 3 | 16 | 14.3 | 1.3 | 0.3 |
| 4 | 0 | 0 | 0 | 0 |
| 5 | 16 | 13.3 | 2.7 | 0 |
| 6 | 0 | 0 | 0 | 0 |
| 7 | 16 | 13.7 | 1.7 | 0.7 |
| 8 | 0 | 0 | 0 | 0 |
| 9 | 16 | 14 | 2 | 0 |
| 10 | 0 | 0 | 0 | 0 |
| 11 | 16 | 13.3 | 2.7 | 0 |
| 12 | 0 | 0 | 0 | 0 |

### attributor (seed avg, 96 deals)

| round | deals | vague | true | false |
|---|---|---|---|---|
| 1 | 16 | 14 | 1.3 | 0.7 |
| 2 | 0 | 0 | 0 | 0 |
| 3 | 16 | 14.3 | 0.7 | 1 |
| 4 | 0 | 0 | 0 | 0 |
| 5 | 16 | 12.7 | 2.7 | 0.7 |
| 6 | 0 | 0 | 0 | 0 |
| 7 | 16 | 13 | 2 | 1 |
| 8 | 0 | 0 | 0 | 0 |
| 9 | 16 | 15 | 0.7 | 0.3 |
| 10 | 0 | 0 | 0 | 0 |
| 11 | 16 | 10.7 | 4.7 | 0.7 |
| 12 | 0 | 0 | 0 | 0 |

### lawyer+attr (seed avg, 96 deals)

| round | deals | vague | true | false |
|---|---|---|---|---|
| 1 | 16 | 1 | 8.7 | 6.3 |
| 2 | 0 | 0 | 0 | 0 |
| 3 | 15.7 | 1.3 | 11.7 | 2.7 |
| 4 | 0.3 | 0 | 0.3 | 0 |
| 5 | 15.7 | 1 | 10.7 | 4 |
| 6 | 0.3 | 0 | 0.3 | 0 |
| 7 | 15.7 | 1.7 | 11 | 3 |
| 8 | 0.3 | 0 | 0.3 | 0 |
| 9 | 15.7 | 0.3 | 12.3 | 3 |
| 10 | 0.3 | 0 | 0.3 | 0 |
| 11 | 15.7 | 0.3 | 10.7 | 4.7 |
| 12 | 0.3 | 0 | 0 | 0.3 |

### contract+attr (seed avg, 96 deals)

| round | deals | vague | true | false |
|---|---|---|---|---|
| 1 | 16 | 0 | 12 | 4 |
| 2 | 0 | 0 | 0 | 0 |
| 3 | 16 | 0 | 13.3 | 2.7 |
| 4 | 0 | 0 | 0 | 0 |
| 5 | 16 | 0 | 12 | 4 |
| 6 | 0 | 0 | 0 | 0 |
| 7 | 16 | 0 | 13.7 | 2.3 |
| 8 | 0 | 0 | 0 | 0 |
| 9 | 16 | 0 | 15.3 | 0.7 |
| 10 | 0 | 0 | 0 | 0 |
| 11 | 16 | 0 | 15 | 1 |
| 12 | 0 | 0 | 0 | 0 |

