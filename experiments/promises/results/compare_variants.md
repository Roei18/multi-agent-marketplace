# promises — four-way comparison (ratio-based)

`baseline` seed 0, `attributor` seed 0, `lawyer_attributor` seed 0, `contract_attributor` seed 0 · 12 rounds each. One seed — direction, not effect size.

All comparison metrics are ratios in [0,1], so arms are comparable regardless of deal count. Every number is mechanical (LLM extracts the promised round + a verified quote; the verdict is arithmetic) and reproducible via `rescore.py`.

## Promise distribution (share of all deals — supply-independent)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| **vague rate** | **78%** | **88%** | **5%** | **0%** |
| concrete rate | 22% | 12% | 95% | 100% |
| true (on-time) rate | 14% | 11% | 79% | 27% |
| false rate | 8% | 2% | 16% | 73% |
|   · false-late | 5% | 2% | 16% | 0% |
|   · false-never | 3% | 0% | 0% | 73% |

## Honesty among sellers who committed to a round (supply-independent)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| **kept-of-concrete** | **64%** | **88%** | **83%** | **27%** |
| broken-of-concrete | 36% | 12% | 17% | 73% |

## Regulation intensity

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| voided rate | 0% | 2% | 16% | 73% |
| lawyer-block rate | — | — | 34% | — |

## Volume & delivery (context — delivered/deal is SUPPLY-BOUND, not a regime metric)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| deals made | 65 | 65 | 62 | 60 |
| delivered / deal (supply-bound) | 92% | 100% | 100% | 137% |
