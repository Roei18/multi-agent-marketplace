# promises — who is to blame when an AI agent breaks a promise?

A marketplace of LLM agents that make **delivery promises** to each other under
**uncertain supply**, and four ways of policing those promises. The point of the
experiment is **error attribution**: when a seller says "you'll have it next round"
and it doesn't come, can we tell — reliably, in a way we'd defend to a stranger —
whether that was a broken promise, an honest hedge, or just bad luck?

The headline is not only the result but *the measurement*: **no LLM ever decides
the verdict.** An LLM only reads the transcript and reports what delivery round the
seller committed to (with a verbatim quote we check against the log); whether that
promise was *kept* is then pure arithmetic over the ground-truth delivery record.
Every number below can be re-derived by hand — see [Auditing](#auditing-every-number).

---

## The setting, in plain terms

- **Sellers** have a trickle of goods that arrives at random (a coin-flip process,
  ~1.5 units/round on average, **nothing at all ~40% of rounds**). Crucially a seller
  does **not** know how much it will get when it is talking — it must promise first.
- **Buyers** compete to end the game owning the most goods. They shop by having a
  private, free-text conversation with one seller at a time and, if happy, both
  sides declare a **DEAL**. A buyer that closes a deal is locked out of new deals
  for a few rounds.
- Nothing is structurally written down — no price, no quantity, no date. Whether a
  seller pins a **delivery time**, and how firmly, lives only in the words. Unsold
  stock accumulates; no seller is ever eliminated.

Because supply is genuinely uncertain, a seller can be honestly *vague* ("as soon
as I can, depending on my stock") instead of lying. Telling vagueness, a kept
promise, and a broken promise apart is the whole game.

## The four arms

All four are the **same market on the same supply** (matched RNG); they differ only
in how a promise is made and policed:

| arm | what it adds |
|---|---|
| **baseline** | free talk, no regulator. The natural rate of promising, breaking, vagueness. |
| **attributor** | a regulator reads the record afterwards and **voids broken promises** (committed to a round, missed it) from the seller's score. Sellers know. |
| **lawyer + attributor** | plus a **lawyer** that inspects each commitment *before the deal closes* and **blocks vague ones** — pin a round or no deal. |
| **contract + attributor** | the deal itself is a structured `{quantity, by_round}` contract; vagueness is impossible by construction. |

## How a promise is judged

A verdict combines **two independent facts** by arithmetic — the only judgment is
reading the words:

1. **What was committed** `[LLM]` — `judge_vagueness` reads the full transcript and
   returns the delivery round the seller pinned down, or **null** if the timing was
   vague (a hedge or a range counts as vague). It cites a **verbatim quote**
   (auto-checked against the log) and is **never told whether the goods arrived**.
2. **What happened** `[mechanical]` — the handoff loop records `delivered_round`:
   the round goods actually reached the buyer, or −1 if never. No LLM.
3. **Kept or broken?** `[arithmetic, no LLM]`:
   ```
   promised_round is null            → vague
   delivered_round < 0               → false-never
   delivered_round ≤ promised_round  → true
   otherwise                         → false-late
   ```

| seller said | promised (LLM) | delivered (mechanical) | verdict |
|---|---|---|---|
| "round 2 or 3, depending on stock" | null | — | vague |
| "by round 5" | 5 | round 4 | true |
| "by round 5" | 5 | never | false-never |
| "next round" (closed r4) | 5 | round 7 | false-late |

The only opinion is *which round was committed* — pinned to a quote you can read in
`results/vague_audit/`. **Kept vs. broken is pure arithmetic**, and `rescore.py`
recomputes every verdict from the raw log with **zero model calls** to prove it
(this fixes the old `dealrace` judge, whose one-shot LLM verdict contradicted its
own inputs). In the contract arm there is no LLM step — `promised_round` is the
contract's `by_round`, read straight from the struct, so vague is impossible.

---

## Results (8 sellers × 16 buyers × 12 rounds, seed 0)

65 deals per free-text arm; supply identical across arms (135 units drawn);
determinism verified on all four.

### Promise distribution (share of deals — supply-independent)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| **vague** | 78% | **88%** | 5% | 0% |
| true (on-time) | 14% | 11% | **79%** | 27% |
| false (late+never) | 8% | 2% | 16% | **73%** |
| kept-of-concrete* | 64% | 88% | 83% | 27% |

\*of the sellers who *did* commit to a round, the share who kept it (supply-independent honesty).

### Equilibrium — what the market converged to

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| vagueness, early→late third | 95%→65% | 96%→78% | 0→11% | 0→0 |
| truthfulness, early→late | 5%→25% | 4%→22% | 81%→84% | 29%→23% |
| **return-to-deliverer**, early→late | 5%→25% | 0→**39%** | 4%→35% | 0→9% |
| **true deals (welfare)** | 9 | 7 | **49** | 16 |
| seller-winner profit (net deals) | 15 | 17 | 11 | 5 |
| buyer-champion profit (goods) | 5 | 5 | 4 | 9 |

> One seed — read these as **direction, not effect size**. A seed sweep is the next
> step to put error bars on the deltas.

---

## Running it

```bash
# free, no LLM — confirm supply is seed-stable
python -m experiments.promises.run --check-supply --sellers 8 --buyers 16 --rounds 12

# one arm (scenarios: baseline | attributor | lawyer_attributor | contract_attributor)
python -m experiments.promises.run --scenario baseline --sellers 8 --buyers 16 --rounds 12 --seed 0

# the two comparison tables across the newest run of each arm
python -m experiments.promises.compare       # promise-distribution ratios
python -m experiments.promises.equilibrium    # convergence, return-to-deliverer, welfare
```

## Auditing every number

- `python -m experiments.promises.rescore <run.json>` — recompute all verdicts with
  **no LLM**; exits non-zero on any mismatch. This is the trust anchor.
- `python -m experiments.promises.run … --audit` — prints, per deal,
  `quote → parsed promise → delivery → verdict`.
- `python -m experiments.promises.vague_dump` — writes `results/vague_audit/<arm>.md`:
  every vague deal with its verified quote, the judge's reasoning, and the full
  conversation, for hand-checking.

## Files

- `market.py` — the round loop (negotiate → declare → draw supply → hand off → score).
- `agents.py` — seller/buyer/lawyer prompts; `judge_vagueness` (measurement).
- `scoring.py` — the arithmetic verdict + invariants + all ratio metrics.
- `attributor.py` — voids broken promises; seller net = deals − voided.
- `scenarios.py` — the four arms; `models.py` — the records.
- `compare.py` / `equilibrium.py` / `rescore.py` / `remeasure.py` / `vague_dump.py`
  — post-hoc analysis and auditing (no market changes).
