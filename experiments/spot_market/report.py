"""Auto-generated, strict report for a saved spot_market run.

    python -m experiments.spot_market.report experiments/spot_market/results/<run>.json

Produces one Markdown file with four fixed sections, built from the code itself
wherever possible (never hand-retyped, so it can't drift out of sync):

  1. Header       -- scenario, seed, scale, model config, the commit this was rendered from.
  2. Game rules    -- verbatim from RunResult.load_bearing_assumptions.
  3. Prompts       -- one captioned, real example of each of the 4 prompt shapes in the
                      game, regenerated at zero cost (a mocked call_llm, this run's actual
                      scale) -- never hand-copied from a previous run.
  4. Metrics       -- the same 3-section breakdown run.py prints (deterministic /
                      LLM-assisted / equilibrium), each paired with a one-line definition
                      of how it's computed, not just the number.

This is a READ-ONLY report over an already-finished run -- it makes no LLM calls that
affect the game, only the 4 zero-cost example-prompt captures below.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import experiments.spot_market.agents as agents_mod
from experiments.spot_market.agents import BuyerAgent, SellerAgent, judge_seller_vagueness
from experiments.spot_market.market import (
    BuyerState,
    SellerState,
    buyer_rows,
    buyer_status_view,
    public_board,
    seller_rows,
    seller_status_view,
)
from experiments.spot_market.models import (
    ApproachChoice,
    BuyerTurn,
    RunResult,
    SellerTurn,
    SellerVaguenessJudgment,
    Utterance,
)
from experiments.spot_market.scenarios import SELLERS

# --------------------------------------------------------------------------
# 3. Prompts -- captions explain WHAT each shape represents and WHEN it fires
# --------------------------------------------------------------------------

_CAPTIONS = [
    ("Buyer chooses which seller to approach", "ApproachChoice",
     "Shown to a BUYER at the start of every attempt within its own turn -- before it "
     "has said anything to anyone this round. Fires once per attempt (up to "
     "`max_attempts_per_turn` times in one turn) whenever the buyer isn't yet convinced "
     "and needs to pick its next seller to try."),
    ("Seller's opening turn", "SellerTurn",
     "Shown to the SELLER a buyer just approached, on the very first message of a fresh "
     "attempt (message index 0) -- no conversation history exists yet. This is the "
     "seller's opening pitch; it has no declare/accept action of its own, only talk."),
    ("Buyer's reply turn", "BuyerTurn",
     "Shown to the BUYER immediately after the seller speaks, deciding what to say back "
     "and whether to set `declare_deal=true` -- the ONLY action that can close a deal in "
     "this game. Fires on every buyer message within an attempt (indices 1, 3, 5, ...) "
     "until it declares, gives up, or the message cap is hit."),
    ("Post-hoc vagueness judge", "SellerVaguenessJudgment",
     "Shown to NEITHER buyer nor seller. Fires once per finished attempt, AFTER the "
     "entire run completes, reading the full transcript back with zero effect on the "
     "game itself -- purely the LLM-assisted measurement in section 4.2 below."),
]


async def capture_example_prompts(r: RunResult) -> list[tuple[str, str, str]]:
    """Regenerates one real prompt per shape at zero cost (mocked call_llm), using this
    run's actual scale/model config. Returns (caption, response_format, prompt_text)."""
    captured: list[tuple[str, str]] = []
    real_call_llm = agents_mod.call_llm

    async def fake_call_llm(prompt, response_format, model=None, reasoning_effort=None, **kw):
        captured.append((response_format.__name__, prompt))
        if response_format is SellerTurn:
            return SellerTurn(private_reasoning="", updated_note="", message="")
        if response_format is BuyerTurn:
            return BuyerTurn(private_reasoning="", updated_note="", message="", declare_deal=False)
        if response_format is ApproachChoice:
            return ApproachChoice(private_reasoning="", seller=r.sellers[0].id)
        if response_format is SellerVaguenessJudgment:
            return SellerVaguenessJudgment(private_reasoning="", vague=False, reason="")
        raise AssertionError(response_format)

    blurb_by_id = {sid: blurb for sid, _, blurb in SELLERS}
    agents_mod.call_llm = fake_call_llm
    try:
        sellers = {
            s.id: SellerState(SellerAgent(
                s.id, s.name, blurb_by_id.get(s.id, ""), s.arrival_prob,
                n_sellers=r.n_sellers, n_buyers=r.n_buyers, n_rounds=r.n_rounds))
            for s in r.sellers
        }
        buyers = {
            b.id: BuyerState(BuyerAgent(
                b.id, b.name, n_sellers=r.n_sellers, n_buyers=r.n_buyers, n_rounds=r.n_rounds))
            for b in r.buyers
        }
        for s in sellers.values():
            s.agent.model = r.seller_model
            s.agent.reasoning_effort = r.seller_reasoning_effort
        for b in buyers.values():
            b.agent.model = r.buyer_model
            b.agent.reasoning_effort = r.buyer_reasoning_effort

        s1 = sellers[r.sellers[0].id]
        b1 = buyers[r.buyers[0].id]
        seller_board = public_board(seller_lines=seller_rows(list(sellers.values())))
        buyer_board = public_board(buyer_lines=buyer_rows(list(buyers.values())))

        await b1.agent.choose(board=buyer_board, status=buyer_status_view(b1), tried=[],
                              sellers=list(sellers))
        await s1.agent.turn(board=seller_board, status=seller_status_view(s1),
                            buyer_name=b1.agent.name, buyer_id=b1.id, messages=[],
                            opening=True, max_messages=r.max_messages)
        opener = Utterance(speaker=s1.id, private_reasoning="...",
                           message="Hello! I might have a good for you this cycle.")
        await b1.agent.turn(board=buyer_board, status=buyer_status_view(b1),
                            seller_name=s1.agent.name, seller_id=s1.id, messages=[opener],
                            opening=False, max_messages=r.max_messages)
        fake_transcript = (f"{s1.agent.name}: Hello! I might have a good for you this cycle.\n"
                          f"{b1.agent.name}: Can you tell me more?")
        await judge_seller_vagueness(fake_transcript)
    finally:
        agents_mod.call_llm = real_call_llm

    return [(cap, fmt, prompt) for (cap, _fmt, _desc), (fmt, prompt) in zip(_CAPTIONS, captured, strict=True)]


# --------------------------------------------------------------------------
# 4. Metrics -- one-line definitions, paired with this run's actual numbers
# --------------------------------------------------------------------------

_DETERMINISTIC_DEFS = {
    "attempts_total": "Total buyer<->seller negotiation attempts across the whole run "
                      "(one buyer turn may contain several, if it tries more than one seller).",
    "closed_total": "Attempts where the buyer declared a deal -- the sole closing action.",
    "true": "Closed deals that were actually delivered: the buyer was the FIRST to close "
           "with that seller that cycle, AND the seller's cycle draw was a hit.",
    "false": "Closed deals that were NOT delivered -- either the seller's cycle draw "
            "missed, or another buyer had already closed with that seller earlier the "
            "same cycle.",
    "true_rate": "true / attempts_total.",
    "false_rate": "false / attempts_total.",
    "delivered_of_closed": "true / closed_total -- the deal's own success rate, ignoring "
                          "attempts that never closed at all.",
    "fooled_count": "How many closed deals were the 2nd (or later) closer with the same "
                    "seller in the same cycle -- structurally undeliverable no matter "
                    "what the seller draws, since it has at most one unit per cycle.",
    "vague": "Attempts where the buyer never declared at all (mechanical: declare_deal "
            "was never set true by either side reaching a close).",
    "vague_rate": "vague / attempts_total.",
}
_LLM_DEFS = {
    "llm_vague_judged": "How many attempts the post-hoc judge (judge_seller_vagueness) "
                        "actually rated.",
    "llm_vague_count": "Of those, how many were rated vague: the SELLER's language was "
                       "mostly empty reassurance with no real, checkable content -- "
                       "independent of whether a deal ever closed.",
    "llm_vague_rate": "llm_vague_count / llm_vague_judged.",
}


def _fmt(k: str, v: float) -> str:
    """Rate/fraction metrics (anything ending _rate, plus delivered_of_closed which is
    a fraction without that suffix) print as a percentage; counts print as an integer."""
    if k.endswith("_rate") or k == "delivered_of_closed":
        return f"{v:.1%}"
    return f"{v:.0f}"


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_REPO_ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "(unknown)"


def render_report(r: RunResult, prompts: list[tuple[str, str, str]]) -> str:
    out = []
    out.append(f"# spot_market report -- {r.scenario} (seed {r.seed})\n")

    out.append("## 1. Header\n")
    out.append(f"- scenario: `{r.scenario}` -- {r.description}")
    out.append(f"- seed: {r.seed}")
    out.append(f"- scale: {r.n_sellers} sellers x {r.n_buyers} buyers x {r.k_cycles} cycles "
              f"= {r.n_rounds} rounds total")
    out.append(f"- max_attempts_per_turn: {r.max_attempts_per_turn}   max_messages: {r.max_messages}")
    out.append(f"- seller model: {r.seller_model or '(environment default)'}   "
              f"reasoning_effort: {r.seller_reasoning_effort or '(environment default)'}")
    out.append(f"- buyer model: {r.buyer_model or '(environment default)'}   "
              f"reasoning_effort: {r.buyer_reasoning_effort or '(environment default)'}")
    out.append(f"- report rendered from commit `{_git_commit()}` (reflects the CURRENT code "
              f"state, which may differ from the commit that actually produced this run "
              f"if the codebase changed since)")
    out.append(f"- seller winner (deals closed): {r.seller_winner_name} ({r.seller_winner})")
    out.append(f"- buyer champion (goods owned): {r.buyer_champion_name} ({r.buyer_champion})\n")

    out.append("## 2. Game rules\n")
    for a in r.load_bearing_assumptions:
        out.append(f"- {a}")
    out.append("")

    out.append("## 3. Prompts\n")
    out.append("One real, captioned example of each of the 4 prompt shapes in this game, "
              "regenerated at zero cost from this run's actual scale -- not hand-copied.\n")
    for caption, fmt, prompt in prompts:
        desc = next(d for c, _f, d in _CAPTIONS if c == caption)
        out.append(f"### {caption} (`{fmt}`)\n")
        out.append(f"{desc}\n")
        out.append("```")
        out.append(prompt)
        out.append("```\n")

    out.append("## 4. Metrics\n")
    m = r.measurements
    out.append("### 4.1 Deterministic (pure arithmetic, no LLM)\n")
    out.append("| metric | value | definition |")
    out.append("|---|---|---|")
    for k, desc in _DETERMINISTIC_DEFS.items():
        v = m.get(k, 0)
        out.append(f"| `{k}` | {_fmt(k, v)} | {desc} |")

    out.append("\n### 4.2 LLM-assisted\n")
    out.append("| metric | value | definition |")
    out.append("|---|---|---|")
    for k, desc in _LLM_DEFS.items():
        v = m.get(k, 0)
        out.append(f"| `{k}` | {_fmt(k, v)} | {desc} |")

    out.append("\n### 4.3 Equilibrium tracking\n")
    out.append("Two named candidate equilibria, tracked per cycle -- `close_rate` -> 0 is "
              "**equilibrium A** (\"no more deals\"); `top_seller_share` -> 1.0 is "
              "**equilibrium B** (\"one seller is fixed\"). Definitions: `close_rate` = "
              "fraction of that cycle's turns that ended in a closed deal. "
              "`top_seller_share` = of the deals closed that cycle, the share that went "
              "to the single most-favoured seller.\n")
    out.append("| cycle | close_rate | top_seller_share |")
    out.append("|---|---|---|")
    for row in r.equilibrium_series:
        out.append(f"| {row['cycle']:.0f} | {row['close_rate']:.3f} | {row['top_seller_share']:.3f} |")
    if len(r.equilibrium_series) < 8:
        out.append(f"\n*{len(r.equilibrium_series)} cycles is too few to conclude either "
                  f"equilibrium -- this is the raw series to extend, not a verdict.*")

    return "\n".join(out)


async def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m experiments.spot_market.report <run.json>")
    src = Path(sys.argv[1])
    r = RunResult.model_validate(json.loads(src.read_text()))
    prompts = await capture_example_prompts(r)
    text = render_report(r, prompts)
    out_path = src.with_name(src.stem + "_report.md")
    out_path.write_text(text)
    print(f"Report written: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
