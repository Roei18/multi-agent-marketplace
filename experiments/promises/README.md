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
  sides declare a **DEAL** (for **one good**). A buyer that closes a deal is locked
  out of new deals for **one round** (an anti-spam guard, so a buyer can't sign
  every round).
- Nothing is structurally written down — no price or date, and **every deal is for
  one good**. Whether a seller pins a **delivery time**, and how firmly, lives only
  in the words. Unsold stock accumulates; no seller is ever eliminated.

Because supply is genuinely uncertain, a seller can be honestly *vague* ("as soon
as I can, depending on my stock") instead of lying. Telling vagueness, a kept
promise, and a broken promise apart is the whole game.

## The four arms

All four are the **same market on the same supply** (matched RNG), every deal is for
**one good**, and a closed deal locks the buyer for **one round** — so the arms are
apples-to-apples. They differ only in how a promise is made and policed:

| arm | what it adds |
|---|---|
| **baseline** | free talk, no regulator. The natural rate of promising, breaking, vagueness. |
| **attributor** | a regulator reads the record afterwards and **voids broken promises** (committed to a round, missed it) from the seller's score. Sellers know. |
| **lawyer + attributor** | plus a **lawyer** that inspects each commitment *before the deal closes* and **blocks vague ones** — pin a round or no deal. |
| **contract + attributor** | the deal is a **written contract for the one good by a round the seller drafts**; vagueness is impossible by construction. |

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

## Results (8 sellers × 16 buyers × 12 rounds, seeds 0, 1, 2)

Every arm produces exactly **96 deals** (the single-round lock lets each of 16 buyers
close one deal every 2 rounds), so deal volume is a constant and the columns are a
clean apples-to-apples comparison. Supply is identical across arms within a seed
(135 / 149 / 152 units drawn at seeds 0 / 1 / 2); determinism verified on all twelve
runs. Values are the **average over seeds 0–2**.

### Promise distribution + welfare (supply-independent)

| metric | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| **vague %** | 86 | 83 | 6 | 0 |
| **true (on-time) %** | 12 | 12 | 69 | **85** |
| false % | 2 | 5 | 25 | 15 |
| kept-of-concrete %* | 88 | 76 | 74 | 85 |
| **true deals (of 96)** | 12 | 12 | 66 | **81** |
| seller-winner profit (net deals) | 19 | 17 | 16 | 17 |
| buyer-champion profit (goods) | 7 | 7 | 6 | 6 |

\*share of *concrete* promises kept on time; the free-text arms have few concrete deals, so this is a small-denominator ratio there.

### Deal counts — real vs false vs vague (average per seed)

| variant | real (kept, on-time) | false (broken) | vague (no time pinned) | total |
|---|---|---|---|---|
| baseline | 11.7 | 2.0 | **82.3** | 96 |
| attributor | 12.0 | 4.3 | **79.7** | 96 |
| lawyer+attr | 66.3 | 24.0 | 5.7 | 96 |
| contract+attr | **81.3** | 14.7 | 0.0 | 96 |

### Equilibrium — what the market converged to (seed 0)

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| vagueness, early→late third | 84%→75% | 91%→75% | 6%→3% | 0→0 |
| truthfulness, early→late | 12%→25% | 6%→22% | 56%→62% | 66%→**97%** |
| **return-to-deliverer**, early→late | 0→31% | 0→41% | 3%→44% | 0→21% |

### What the fair (one-good) comparison shows

- **Forcing concreteness produces kept promises; free text does not.** Free-text
  arms stay ~**85% vague** and make only ~12 real promises of 96. Both the **lawyer**
  (69% true, 66 kept) and the **contract** (85% true, 81 kept) flip the market to
  real, mostly-kept promises.
- **The contract is now the *most reliable* arm (85% true), not the worst.** With one
  good, a written contract is almost always kept. The earlier "contracts break
  34–73%" was **purely a quantity artifact** — multi-unit contracts (~3 goods) against
  a supply averaging 1.5. Remove the quantity and the hard contract wins.
- **The attributor barely moves anything — and the "dodge" does NOT replicate.**
  Attributor vagueness (83%) ≈ baseline (86%), if anything *lower*. The earlier
  "regulator pushes sellers to vagueness" result (seen under the old multi-round
  lock) does not hold here; a post-hoc regulator on free speech has almost nothing to
  grab once vagueness is already the equilibrium.
- **Given a concrete 1-good promise, ~75–88% are kept in every arm** — the mechanism
  barely changes keep-rate *conditional on committing*; what differs wildly is how
  many concrete promises exist at all (12 vs 66 vs 81 of 96).
- **Equilibrium:** vagueness still falls and truthfulness rises over the game, and
  **return-to-deliverer rises in every arm** (buyers learn to return to sellers who
  delivered). Winner profits are stable across arms.

> **Three seeds, 8×16×12.** This **supersedes the earlier multi-unit results**, which
> conflated the contract's breach rate with its (larger) committed quantity.

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
