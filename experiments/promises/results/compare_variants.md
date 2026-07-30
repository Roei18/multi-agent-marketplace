# promises — four-way comparison (ratio-based)

`baseline` seed 0, `attributor` seed 0, `lawyer_attributor` seed 0, `contract_attributor` seed 0 · 12 rounds each. One seed — direction, not effect size.

All comparison metrics are ratios in [0,1], so arms are comparable regardless of deal count. Every number is mechanical (LLM extracts the promised round + a verified quote; the verdict is arithmetic) and reproducible via `rescore.py`.

## Promise distribution (share of all deals — supply-independent)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| **vague rate** | **77%** | **77%** | **6%** | **0%** |
| concrete rate | 23% | 23% | 94% | 100% |
| true (on-time) rate | 20% | 16% | 54% | 78% |
| false rate | 3% | 7% | 40% | 22% |
|   · false-late | 2% | 5% | 26% | 0% |
|   · false-never | 1% | 2% | 14% | 22% |

## Honesty among sellers who committed to a round (supply-independent)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| **kept-of-concrete** | **86%** | **68%** | **58%** | **78%** |
| broken-of-concrete | 14% | 32% | 42% | 22% |

## Regulation intensity

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| voided rate | 0% | 7% | 40% | 22% |
| lawyer-block rate | — | — | 34% | — |

## Volume & delivery (context — delivered/deal is SUPPLY-BOUND, not a regime metric)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| deals made | 96 | 96 | 96 | 96 |
| delivered / deal (supply-bound) | 86% | 88% | 86% | 78% |
