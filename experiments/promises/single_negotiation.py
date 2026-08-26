"""Cheap single-negotiation sandbox for iterating on prompt design.

Testing a prompt change (agents.py wording, market_rules(), etc.) shouldn't require
paying for a full N-round market. This reconstructs realistic mid-game surrounding
state -- backlog, board, both sides' own history -- from an ALREADY-SAVED run, then
runs ONE live negotiation between a chosen seller and buyer at a chosen round, using
the real `negotiate()` code path from market.py. A handful of LLM calls instead of
hundreds, so you can tweak a prompt and immediately see how the behavior changes.

    python -m experiments.promises.single_negotiation \\
        --source experiments/promises/results/baseline_s0_mirroredhist_p40_20260826_215956.json \\
        --seller S7 --buyer B01 --round 11

Swap in a different arm's toggles (contract mode, reviews, etc.) while keeping this
run's scale/history to source from:

    ... --scenario contract_attributor

Point one side at a different model to probe it in this exact spot:

    ... --seller-model openai/gpt-4o
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.promises.agents import BuyerAgent, SellerAgent
from experiments.promises.market import BuyerState, SellerState, negotiate
from experiments.promises.models import Deal, RunResult
from experiments.promises.scenarios import BUYERS, SELLERS, get_scenario


def real_scenario(r: RunResult, override_name: str | None = None):
    """The CLI (--sellers/--buyers/--rounds/--p) overrides scenario defaults before
    run_market() ever sees it -- get_scenario(name) alone gives the UN-overridden
    defaults, not what the source run actually used. `override_name` swaps in a
    different arm's toggles (contract_mode, single_good, reviews, ...) while keeping
    this run's actual scale, so you can test a prompt under a different arm without
    a fresh source run."""
    base = get_scenario(override_name or r.scenario)
    return replace(base, n_sellers=r.n_sellers, n_buyers=r.n_buyers, n_rounds=r.n_rounds,
                   arrival_probs=(r.heads_prob,) * r.n_sellers)


def deals_as_of(r: RunResult, round_no: int) -> list[Deal]:
    """Deals closed before `round_no`, with delivery masked back to 'not yet
    happened' if the real delivered_round hasn't occurred as of this snapshot."""
    out = []
    for d in r.deals:
        if d.closed_round >= round_no:
            continue
        if d.delivered_round >= round_no:
            out.append(d.model_copy(update={"delivered_round": -1, "delivered_qty": 0}))
        else:
            out.append(d)
    return out


def build_seller_states(r: RunResult, as_of_round: int) -> dict[str, SellerState]:
    out = {}
    for sid, name, blurb in SELLERS[:r.n_sellers]:
        out[sid] = SellerState(SellerAgent(sid, name, blurb, 0.0))
    p_by_id = {s.id: s.arrival_prob for s in r.sellers}
    for sid, sst in out.items():
        sst.agent.p = p_by_id[sid]
    for rec in r.rounds:
        if rec.round >= as_of_round:
            break
        for sid, drawn in rec.goods_drawn.items():
            out[sid].goods_drawn += drawn
        for n in rec.negotiations:
            out[n.seller].conversations += 1
            if n.closed:
                out[n.seller].deals_closed += 1
    for d in r.deals:
        if d.seller in out and 0 <= d.delivered_round < as_of_round:
            out[d.seller].deals_delivered += 1
            out[d.seller].units_sold += d.delivered_qty
    for sst in out.values():
        sst.stock = sst.goods_drawn - sst.units_sold
    return out


def build_buyer_states(r: RunResult, as_of_round: int, scenario) -> dict[str, BuyerState]:
    out = {}
    for bid, name in BUYERS[:r.n_buyers]:
        out[bid] = BuyerState(BuyerAgent(bid, name, scenario))
    for d in r.deals:
        if d.buyer not in out:
            continue
        if d.closed_round < as_of_round:
            out[d.buyer].deals_closed += 1
        if 0 <= d.delivered_round < as_of_round:
            out[d.buyer].deals_delivered += 1
            out[d.buyer].owned += d.delivered_qty
    return out


def print_transcript(conv, seller_name: str, buyer_name: str) -> None:
    for m in conv.messages:
        who = seller_name if m.speaker == conv.seller else buyer_name
        tag = ""
        if m.declare_deal:
            tag = "  [DECLARED DEAL]"
        if getattr(m, "accepted_contract", False):
            tag = "  [ACCEPTED CONTRACT]"
        if getattr(m, "proposed_contract", ""):
            tag = f"  [{m.proposed_contract}]"
        print(f"{who}: {m.message}{tag}")
        print(f"  (private reasoning: {m.private_reasoning})")
        print()


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True,
                    help="a saved run.json to source realistic status/backlog/history/"
                    "board state from")
    ap.add_argument("--seller", required=True, help="seller id, e.g. S7")
    ap.add_argument("--buyer", required=True, help="buyer id, e.g. B01")
    ap.add_argument("--round", type=int, required=True,
                    help="reconstruct state as of this round, and run the negotiation here")
    ap.add_argument("--scenario", default=None,
                    help="swap in a different arm's toggles while keeping the source run's "
                    "scale/history (default: whatever the source run used)")
    ap.add_argument("--seller-model", default=None, help="probe this seller with a different model")
    ap.add_argument("--buyer-model", default=None, help="probe this buyer with a different model")
    ap.add_argument("--seller-reasoning-effort", default=None,
                    choices=["minimal", "low", "medium", "high"],
                    help="override this seller's reasoning effort (default: whatever LLM_REASONING_EFFORT is)")
    ap.add_argument("--buyer-reasoning-effort", default=None,
                    choices=["minimal", "low", "medium", "high"],
                    help="override this buyer's reasoning effort (default: whatever LLM_REASONING_EFFORT is)")
    args = ap.parse_args()

    r = RunResult.model_validate(json.loads(Path(args.source).read_text()))
    scenario = real_scenario(r, args.scenario)
    sellers = build_seller_states(r, args.round)
    buyers = build_buyer_states(r, args.round, scenario)
    deals = deals_as_of(r, args.round)
    rounds_so_far = [rec for rec in r.rounds if rec.round < args.round]
    names = {bid: nm for bid, nm in BUYERS[:r.n_buyers]}

    if args.seller not in sellers:
        raise SystemExit(f"--seller {args.seller!r} not among this source's "
                         f"{r.n_sellers} sellers ({', '.join(sellers)})")
    if args.buyer not in buyers:
        raise SystemExit(f"--buyer {args.buyer!r} not among this source's "
                         f"{r.n_buyers} buyers ({', '.join(buyers)})")

    if args.seller_model:
        sellers[args.seller].agent.model = args.seller_model
    if args.buyer_model:
        buyers[args.buyer].agent.model = args.buyer_model
    if args.seller_reasoning_effort:
        sellers[args.seller].agent.reasoning_effort = args.seller_reasoning_effort
    if args.buyer_reasoning_effort:
        buyers[args.buyer].agent.reasoning_effort = args.buyer_reasoning_effort

    sst, bst = sellers[args.seller], buyers[args.buyer]
    print(f"scenario={scenario.name}  round={args.round}/{scenario.n_rounds}  "
         f"{'(scenario overridden, scale/history from source)' if args.scenario else ''}")
    print(f"{args.seller} {sst.name}: deals_closed={sst.deals_closed} "
         f"delivered={sst.deals_delivered} goods_drawn={sst.goods_drawn} stock~{sst.stock} "
         f"p={sst.agent.p} model={sst.agent.model or '(default)'} "
         f"reasoning_effort={sst.agent.reasoning_effort or '(default)'}")
    print(f"{args.buyer} {bst.agent.name}: owned={bst.owned} deals_closed={bst.deals_closed} "
         f"delivered={bst.deals_delivered} model={bst.agent.model or '(default)'} "
         f"reasoning_effort={bst.agent.reasoning_effort or '(default)'}")
    print("=" * 88)

    conv = await negotiate(
        sst, bst, scenario=scenario, rounds=rounds_so_far, deals=deals,
        sellers=list(sellers.values()), sellers_by_id=sellers, buyers=buyers,
        round_no=args.round, attempt=1, why="(single-negotiation sandbox)", names=names)

    print_transcript(conv, sst.name, bst.agent.name)
    print("=" * 88)
    print(f"CLOSED: {conv.closed}")
    if conv.closed:
        print(f"lock_rounds understood by buyer: {conv.buyer_deal_rounds}")
        if not scenario.single_good:
            print(f"seller_deal_quantity: {conv.seller_deal_quantity}")
        if scenario.contract_mode:
            print(f"draft: {conv.draft_quantity} unit(s) by round {conv.draft_by_round}")


if __name__ == "__main__":
    asyncio.run(main())
