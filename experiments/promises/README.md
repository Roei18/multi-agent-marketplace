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

## The setting

A market of **sellers** who supply one generic good and **buyers** who want to own
as much of it as possible. Over **N rounds**, each buyer and seller negotiate
one-to-one in free text and close **deals** — every deal is for **one good**, and
what's negotiated is **when** it will arrive.

A seller's goods arrive **randomly after each round**; only then can it fulfill its
open deals, and if it can't cover them all, it picks whom to serve. It doesn't know
how much it will get while it's still talking — so it has to **promise before it
knows**.

- **Sellers** compete to close the most deals.
- **Buyers** compete to own the most goods by the end.

A deal closes when **both sides declare a DEAL**. The DEAL itself carries no delivery
time — **whether, and for which round, the seller committed lives in the words**.

**Measuring a deal.** Afterwards we sort every deal into three groups by what the
seller actually committed to:
- **Vague** — never pinned a delivery round; nothing was promised, so the deal isn't binding.
- **True** — committed to a round *and* delivered the good by it.
- **False** — committed to a round but missed it (late or never).

## Roles and protocols

Every protocol runs the **same market on the same supply** (matched RNG), every deal
is for **one good**, and a closed deal blocks the buyer from dealing again **for that
round and the next** (so each buyer closes one deal every two rounds) — so they are
apples-to-apples. They differ only by two optional roles.

**Roles**
- **Attributor** — after all rounds, reviews the record and **voids** every concrete
  promise not delivered **on time** (late or never), striking it from the seller's
  score.
- **Lawyer** — at the point a DEAL would close, reviews the conversation and lets it
  close **only if the seller made a concrete promise**; a vague one is blocked, with
  one chance to pin a round.

**Protocols**

| protocol | what it is |
|---|---|
| **baseline** | all free talk; a deal is just both sides declaring DEAL, no format. |
| **attributor** | baseline + the attributor. |
| **attributor + lawyer** | + the lawyer. |
| **attributor + contract** | the deal is a **formatted contract for the one good by a round the seller drafts** — the buyer accepts it or not. Vagueness is impossible by construction. |

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

Every arm produces exactly **96 deals** (a closed deal blocks the buyer for that round
and the next, so each of 16 buyers closes one deal every 2 rounds — deals land in the
6 odd rounds), so deal volume is a constant and the columns are a clean
apples-to-apples comparison. Supply is identical across arms within a seed
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

### Market dynamics (averages over seeds 0–2)

Three views of *how* the market runs, not just its end state — all mechanical
post-hoc analysis, re-derivable with `python -m experiments.promises.dynamics`.

**Deal distribution per round.** Deals close only in the 6 odd rounds (the 2-round
block). Free-text arms are flat — ~86% vague every round, no trend toward honesty;
lawyer/contract are concrete from round 1, their true-vs-false wobbling with each
round's supply luck. Read as vague / true / false:

| round | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| 1 | 13.7 / 1.3 / 1.0 | 14.0 / 1.3 / 0.7 | 1.0 / 8.7 / 6.3 | 0 / 12.0 / 4.0 |
| 3 | 14.3 / 1.3 / 0.3 | 14.3 / 0.7 / 1.0 | 1.3 / 11.7 / 2.7 | 0 / 13.3 / 2.7 |
| 5 | 13.3 / 2.7 / 0 | 12.7 / 2.7 / 0.7 | 1.0 / 10.7 / 4.0 | 0 / 12.0 / 4.0 |
| 7 | 13.7 / 1.7 / 0.7 | 13.0 / 2.0 / 1.0 | 1.7 / 11.0 / 3.0 | 0 / 13.7 / 2.3 |
| 9 | 14.0 / 2.0 / 0 | 15.0 / 0.7 / 0.3 | 0.3 / 12.3 / 3.0 | 0 / 15.3 / 0.7 |
| 11 | 13.3 / 2.7 / 0 | 10.7 / 4.7 / 0.7 | 0.3 / 10.7 / 4.7 | 0 / 15.0 / 1.0 |

**Social welfare — top vs. average agent.** Seller score = net deals (closed − voided);
buyer score = goods owned. The market is fairly egalitarian; no runaway winner.

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| seller top / average | 18.7 / 12.0 | 17.0 / 11.5 | 16.3 / 9.0 | 17.0 / 10.2 |
| seller top ÷ avg | 1.56 | 1.49 | **1.84** | 1.66 |
| buyer top / average | 7.0 / 5.7 | 6.7 / 5.8 | 6.0 / 5.5 | 6.0 / 5.1 |
| buyer top ÷ avg | 1.22 | 1.15 | 1.09 | 1.18 |

The **seller** winner runs ~1.5–1.8× ahead of the pack (widest under the lawyer, which
thins the average by voiding more); the **buyer** champion only ~1.1–1.2× ahead — goods
are spread thin (supply ≈ 145 over 16 buyers).

**Negotiations.** A buyer essentially closes with the **first seller it approaches** —
a near-benign game for sellers (no real seller-vs-seller competition for a buyer).

| | baseline | attributor | lawyer+attr | contract+attr |
|---|---|---|---|---|
| attempts to close (mean, ≤3) | 1.00 | 1.00 | 1.08 | 1.03 |
| closed on 1st seller | 100% | 100% | 92% | 97% |
| distinct sellers/buyer over game (of 8) | 4.4 | 4.6 | 4.6 | 4.8 |
| conversation length (mean turns, cap 12) | 8.5 | 8.6 | 8.5 | **7.2** |
| close rate | 99.7% | 99.7% | 92% | 97% |
| walked away (no deal, per seed) | 0.3 | 0.3 | 8.7 | 2.7 |
| attributor fines given (deals voided) | 0 | 4.3 | 24 | 14.7 |

Conversations run **~8–9 turns** in free text, **faster (~7)** under a contract
(draft-and-accept beats open haggling). A *walk-away* is a conversation where the two
talked but never both declared DEAL. In free text they almost never walk away
(≈99.7% close); the **lawyer** arm walks away most (8.7/seed) — that is the mechanism
working, blocking vague commitments that never get pinned to a round — and the
**contract** arm walks when the buyer declines the seller's draft.

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
