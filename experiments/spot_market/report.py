"""Auto-generated, strict report for a saved spot_market run.

    python -m experiments.spot_market.report experiments/spot_market/results/<run>.json

Produces one Markdown file with four fixed sections, built from the code itself
wherever possible (never hand-retyped, so it can't drift out of sync):

  1. Header    -- scenario, seed, scale, model config, the commit this was rendered from.
  2. Game rules -- short, curated restatement of the mechanism (full legal text lives in
                  the saved run's load_bearing_assumptions, for anyone who wants it).
  3. Prompts    -- the two shared headers (seller-facing, buyer-facing) shown ONCE, then
                  each of the 4 prompt shapes shown as just its distinguishing tail --
                  regenerated at zero cost (a mocked call_llm, this run's actual scale),
                  never hand-copied.
  4. Metrics    -- the same 3-section breakdown run.py prints (deterministic /
                  LLM-assisted / equilibrium), each paired with a short definition.

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
# 2. Game rules -- short, curated (full text is in the run JSON if needed)
# --------------------------------------------------------------------------

_GAME_RULES = [
    "Instant delivery: a deal is for THIS cycle's draw only -- no future rounds, no promises.",
    "Sellers can't stockpile: each cycle, every seller gets one good or none (a Bernoulli "
    "draw), decided before that cycle's talk starts.",
    "Declaring is buyer-only: the seller can't accept/refuse, only persuade. A seller may "
    "be closed with by many buyers in one cycle, but can fulfil only the FIRST.",
    "Sellers don't know their own draw while negotiating -- genuine uncertainty, same "
    "info timing as promises.",
    "One buyer acts per round, round-robin (buyer 1..M, repeating for K cycles) -- every "
    "round has the identical shape.",
    "A buyer may try several sellers per turn, but declaring locks its turn to that seller.",
    "Both sides keep a persistent free-text note across the whole run, revised on their "
    "own ordinary turn.",
]

# --------------------------------------------------------------------------
# 3. Prompts -- captions explain WHAT each shape represents and WHEN it fires
# --------------------------------------------------------------------------

_CAPTIONS = [
    ("Buyer picks a seller", "ApproachChoice",
     "buyer header +", "start of every attempt, before saying anything this round"),
    ("Seller's opening turn", "SellerTurn",
     "seller header +", "a fresh attempt's first message -- no history yet"),
    ("Buyer's reply turn", "BuyerTurn",
     "buyer header +", "every buyer message in an attempt; the ONLY place declare_deal fires"),
    ("Post-hoc vagueness judge", "SellerVaguenessJudgment",
     "standalone, no shared header --", "once per finished attempt, AFTER the run ends; no effect on the game"),
]


async def capture_example_prompts(r: RunResult) -> tuple[str, str, list[tuple[str, str, str]]]:
    """Regenerates real prompts at zero cost (mocked call_llm), using this run's actual
    scale/model config. Returns (seller_header, buyer_header, [(caption, format, tail)]) --
    `tail` is the prompt with its shared header stripped off, since sellers and buyers
    each see the SAME header on every one of their turns."""
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
        seller_status = seller_status_view(s1)
        buyer_status = buyer_status_view(b1)

        # the shared header every turn for this role opens with -- captured directly,
        # no LLM call, exactly the string turn()/choose() prepend to their own tail
        seller_header = s1.agent._base(seller_board, seller_status)
        buyer_header = b1.agent._base(buyer_board, buyer_status)

        await b1.agent.choose(board=buyer_board, status=buyer_status, tried=[],
                              sellers=list(sellers))
        await s1.agent.turn(board=seller_board, status=seller_status,
                            buyer_name=b1.agent.name, buyer_id=b1.id, messages=[],
                            opening=True, max_messages=r.max_messages)
        opener = Utterance(speaker=s1.id, private_reasoning="...",
                           message="Hello! I might have a good for you this cycle.")
        await b1.agent.turn(board=buyer_board, status=buyer_status,
                            seller_name=s1.agent.name, seller_id=s1.id, messages=[opener],
                            opening=False, max_messages=r.max_messages)
        fake_transcript = (f"{s1.agent.name}: Hello! I might have a good for you this cycle.\n"
                          f"{b1.agent.name}: Can you tell me more?")
        await judge_seller_vagueness(fake_transcript)
    finally:
        agents_mod.call_llm = real_call_llm

    results = []
    for (cap, fmt, _prefix, _when), (got_fmt, prompt) in zip(_CAPTIONS, captured, strict=True):
        header = buyer_header if "buyer" in _prefix else seller_header if "seller" in _prefix else None
        tail = prompt[len(header):].lstrip("\n") if header and prompt.startswith(header) else prompt
        results.append((cap, got_fmt, tail))
    return seller_header, buyer_header, results


# --------------------------------------------------------------------------
# 4. Metrics -- short definitions, paired with this run's actual numbers
# --------------------------------------------------------------------------

_DETERMINISTIC_DEFS = {
    "attempts_total": "total negotiation attempts",
    "closed_total": "attempts where the buyer declared",
    "true": "closed AND delivered (first closer that cycle + seller drew a good)",
    "false": "closed but not delivered (seller missed the draw, or wasn't first)",
    "true_rate": "true / attempts_total",
    "false_rate": "false / attempts_total",
    "delivered_of_closed": "true / closed_total -- success rate of closed deals only",
    "fooled_count": "closes that were the 2nd+ same-seller closer that cycle -- "
                    "structurally undeliverable regardless of the draw",
    "voided_total": "attributor arm only: closed deals denied from a seller's own score",
    "vague": "attempts where the buyer never declared at all",
    "vague_rate": "vague / attempts_total",
}
_LLM_DEFS = {
    "llm_vague_judged": "attempts the post-hoc judge rated",
    "llm_vague_count": "of those, rated vague -- seller's language was empty "
                       "reassurance, no real content",
    "llm_vague_rate": "llm_vague_count / llm_vague_judged",
}


def _fmt(k: str, v: float) -> str:
    if k.endswith("_rate") or k == "delivered_of_closed":
        return f"{v:.1%}"
    return f"{v:.0f}"


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_REPO_ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "(unknown)"


def render_report(r: RunResult, seller_header: str, buyer_header: str,
                  prompts: list[tuple[str, str, str]]) -> str:
    out = []
    out.append(f"# spot_market report -- {r.scenario} (seed {r.seed})\n")

    out.append("## 1. Header\n")
    out.append(f"`{r.scenario}` -- {r.n_sellers}S x {r.n_buyers}B x {r.k_cycles} cycles "
              f"({r.n_rounds} rounds) -- seed {r.seed} -- commit `{_git_commit()}`  ")
    out.append(f"seller: {r.seller_model or 'default'}/{r.seller_reasoning_effort or 'default'}   "
              f"buyer: {r.buyer_model or 'default'}/{r.buyer_reasoning_effort or 'default'}   "
              f"attempts/turn: {r.max_attempts_per_turn}   msg cap: {r.max_messages}  ")
    scored = "net score" if r.apply_attributor else "deals closed"
    out.append(f"winner ({scored}): {r.seller_winner_name} ({r.seller_winner})   "
              f"champion: {r.buyer_champion_name} ({r.buyer_champion})\n")

    out.append("## 2. Game rules\n")
    for a in _GAME_RULES:
        out.append(f"- {a}")
    if r.apply_attributor:
        out.append("- **Attributor (this arm):** a closed deal that's never delivered is "
                  "VOIDED from the seller's own score -- net_score = deals_closed - "
                  "deals_voided. Mechanical, no LLM; over-closing stops being free.")
    out.append("")

    out.append("## 3. Prompts\n")
    out.append("Every SELLER turn opens with this header:\n")
    out.append("```")
    out.append(seller_header)
    out.append("```\n")
    out.append("Every BUYER turn opens with this header:\n")
    out.append("```")
    out.append(buyer_header)
    out.append("```\n")
    out.append("Each prompt shape below is that header (or none, for the judge) plus:\n")
    for (caption, fmt, prefix, when), (_c, _f, tail) in zip(_CAPTIONS, prompts, strict=True):
        out.append(f"**{caption}** (`{fmt}`, {prefix} {when})")
        out.append("```")
        out.append(tail)
        out.append("```\n")

    out.append("## 4. Metrics\n")
    m = r.measurements
    out.append("**Deterministic** (pure arithmetic, no LLM)\n")
    out.append("| metric | value | = |")
    out.append("|---|---|---|")
    for k, desc in _DETERMINISTIC_DEFS.items():
        out.append(f"| `{k}` | {_fmt(k, m.get(k, 0))} | {desc} |")

    out.append("\n**LLM-assisted**\n")
    out.append("| metric | value | = |")
    out.append("|---|---|---|")
    for k, desc in _LLM_DEFS.items():
        out.append(f"| `{k}` | {_fmt(k, m.get(k, 0))} | {desc} |")

    out.append("\n**Equilibrium** -- close_rate/attempt_rate->0 is A (\"no more deals\"), "
              "top_seller_share->1 is B (\"one seller fixed\")  \n"
              "close_rate = fraction of turns (buyers) that closed with anyone; "
              "attempt_rate = fraction of individual conversations that closed\n")
    out.append("| cycle | close_rate | attempt_rate | top_seller_share |")
    out.append("|---|---|---|---|")
    for row in r.equilibrium_series:
        out.append(f"| {row['cycle']:.0f} | {row['close_rate']:.2f} | "
                  f"{row['attempt_close_rate']:.2f} | {row['top_seller_share']:.2f} |")
    if len(r.equilibrium_series) < 8:
        out.append(f"\n*{len(r.equilibrium_series)} cycles -- too few to conclude either one.*")

    return "\n".join(out)


async def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m experiments.spot_market.report <run.json>")
    src = Path(sys.argv[1])
    r = RunResult.model_validate(json.loads(src.read_text()))
    seller_header, buyer_header, prompts = await capture_example_prompts(r)
    text = render_report(r, seller_header, buyer_header, prompts)
    out_path = src.with_name(src.stem + "_report.md")
    out_path.write_text(text)
    print(f"Report written: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
