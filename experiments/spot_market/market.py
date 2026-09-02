"""The spot market: one Bernoulli draw per seller per cycle, resolved with pure
arithmetic -- no LLM judge or promise-extraction step anywhere in this file.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass

from experiments.spot_market.agents import BuyerAgent, SellerAgent
from experiments.spot_market.models import (
    Attempt,
    BuyerSummary,
    Cycle,
    RunResult,
    SellerSummary,
    Turn,
)
from experiments.spot_market.scenarios import BUYERS, SELLERS, Scenario

# --------------------------------------------------------------------------
# Pure functions
# --------------------------------------------------------------------------


def draw_stock(rng: random.Random, p: float) -> bool:
    """A single Bernoulli trial -- has a good this cycle, or doesn't. No accumulation:
    called once per seller per cycle, never per-round."""
    return rng.random() < p


def build_measurements(turns: list[Turn]) -> dict:
    all_attempts = [a for t in turns for a in t.attempts]
    v = Counter(a.verdict for a in all_attempts)
    n = len(all_attempts) or 1
    closed = sum(1 for a in all_attempts if a.closed) or 1
    return {
        "attempts_total": len(all_attempts),
        "closed_total": closed if any(a.closed for a in all_attempts) else 0,
        "true": v["true"], "false": v["false"], "vague": v["vague"],
        "true_rate": round(v["true"] / n, 3),
        "false_rate": round(v["false"] / n, 3),
        "vague_rate": round(v["vague"] / n, 3),
        "delivered_of_closed": round(v["true"] / closed, 3),
    }


def estimate_llm_calls(s: Scenario) -> tuple[int, int]:
    lo = s.n_rounds * 2                                              # best case: 1 exchange, instant declare
    hi = s.n_rounds * s.max_attempts_per_turn * (s.max_messages + 1)  # +1 per attempt for choose()
    return lo, hi


# --------------------------------------------------------------------------
# Live state
# --------------------------------------------------------------------------


@dataclass
class SellerState:
    agent: SellerAgent
    times_approached: int = 0
    deals_closed: int = 0
    deals_delivered: int = 0
    deals_failed: int = 0
    vague_attempts: int = 0

    @property
    def id(self) -> str:
        return self.agent.id

    @property
    def name(self) -> str:
        return self.agent.name


@dataclass
class BuyerState:
    agent: BuyerAgent
    owned: int = 0
    turns_taken: int = 0
    deals_closed: int = 0
    deals_delivered: int = 0
    deals_failed: int = 0
    vague_attempts: int = 0

    @property
    def id(self) -> str:
        return self.agent.id


def seller_rows(sellers: list[SellerState]) -> list[str]:
    return [f"  {s.id} {s.name:22s} {s.deals_closed} deal(s) closed" for s in sellers]


def buyer_rows(buyers: list[BuyerState]) -> list[str]:
    ranked = sorted(buyers, key=lambda b: (-b.owned, b.id))
    return [f"  {b.id} {b.agent.name:22s} owns {b.owned}" for b in ranked]


def public_board(seller_lines: list[str], buyer_lines: list[str] | None = None) -> str:
    out = ["# Public board -- sellers' contest (deals closed)"] + seller_lines
    if buyer_lines is not None:
        out += ["", "# Public board -- buyers' contest (goods owned)"] + buyer_lines
    return "\n".join(out)


def seller_status_view(s: SellerState) -> str:
    return (f"Deals closed so far: {s.deals_closed}. Delivered: {s.deals_delivered}. "
           f"Closed but NOT delivered: {s.deals_failed}. Approached {s.times_approached} "
           f"time(s) so far.")


def buyer_status_view(b: BuyerState) -> str:
    return (f"You own {b.owned} good(s) so far. Turns taken: {b.turns_taken}. Deals closed: "
           f"{b.deals_closed}, delivered: {b.deals_delivered}, closed but NOT delivered: "
           f"{b.deals_failed}.")


def resolve_seller_id(raw: str, sellers: dict[str, SellerState]) -> str | None:
    """Match a buyer's free-text seller answer back to an id, same forgiving matching
    as promises' resolve_seller -- models often answer 'S7 Redmond Wholesale' or just
    the name instead of the bare id asked for."""
    upper = raw.strip().upper()
    if upper in sellers:
        return upper
    m = re.match(r"([A-Z]+\d+)\b", upper)
    if m and m.group(1) in sellers:
        return m.group(1)
    lower = raw.strip().lower()
    matches = {sid for sid, s in sellers.items()
              if s.name.lower() in lower or lower in s.name.lower()}
    return next(iter(matches)) if len(matches) == 1 else None


# --------------------------------------------------------------------------
# One negotiation
# --------------------------------------------------------------------------


async def negotiate_attempt(seller: SellerState, buyer: BuyerState, *, seller_board: str,
                            buyer_board: str, seller_status: str, buyer_status: str,
                            max_messages: int, approach_reasoning: str) -> Attempt:
    att = Attempt(seller=seller.id, approach_reasoning=approach_reasoning)
    seller_declared = buyer_declared = False
    opening = True
    while len(att.messages) < max_messages:
        s_msg = await seller.agent.turn(
            board=seller_board, status=seller_status, buyer_name=buyer.agent.name,
            buyer_id=buyer.id, messages=att.messages, opening=opening,
            max_messages=max_messages)
        att.messages.append(s_msg)
        seller_declared = seller_declared or s_msg.declare_deal
        if seller_declared and buyer_declared:
            att.closed = True
            break
        if not s_msg.continue_conversation or len(att.messages) >= max_messages:
            break

        b_msg = await buyer.agent.turn(
            board=buyer_board, status=buyer_status, seller_name=seller.agent.name,
            seller_id=seller.id, messages=att.messages, opening=opening,
            max_messages=max_messages)
        att.messages.append(b_msg)
        buyer_declared = buyer_declared or b_msg.declare_deal
        opening = False
        if seller_declared and buyer_declared:
            att.closed = True
            break
        if not b_msg.continue_conversation:
            break
    return att


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


async def run_market(scenario: Scenario, seed: int, *, verbose: bool = True,
                     seller_model: str | None = None, buyer_model: str | None = None,
                     seller_reasoning_effort: str | None = None,
                     buyer_reasoning_effort: str | None = None) -> RunResult:
    rng = random.Random(seed)

    sellers: dict[str, SellerState] = {}
    for (sid, name, blurb), p in zip(SELLERS[:scenario.n_sellers], scenario.arrival_probs,
                                     strict=True):
        a = SellerAgent(sid, name, blurb, p)
        if seller_model:
            a.model = seller_model
        if seller_reasoning_effort:
            a.reasoning_effort = seller_reasoning_effort
        sellers[sid] = SellerState(a)

    buyers: dict[str, BuyerState] = {}
    for bid, name in BUYERS[:scenario.n_buyers]:
        a = BuyerAgent(bid, name)
        if buyer_model:
            a.model = buyer_model
        if buyer_reasoning_effort:
            a.reasoning_effort = buyer_reasoning_effort
        buyers[bid] = BuyerState(a)

    seller_order = list(sellers)
    buyer_order = list(buyers)

    cycles: list[Cycle] = []
    turns: list[Turn] = []
    round_no = 0

    for cyc_no in range(1, scenario.k_cycles + 1):
        drawn = {sid: draw_stock(rng, sellers[sid].agent.p) for sid in seller_order}
        cycle_first_closer: dict[str, str] = {}    # seller_id -> buyer_id
        cycle_turns: list[Turn] = []

        if verbose:
            print(f"\n{'=' * 78}\nCYCLE {cyc_no}\n{'=' * 78}")

        for bid in buyer_order:
            round_no += 1
            b = buyers[bid]
            b.turns_taken += 1
            turn = Turn(round=round_no, cycle=cyc_no, buyer=bid)
            tried: list[str] = []

            for _ in range(scenario.max_attempts_per_turn):
                seller_board = public_board(seller_rows(list(sellers.values())))
                buyer_board = public_board(seller_rows(list(sellers.values())),
                                           buyer_rows(list(buyers.values())))
                buyer_status = buyer_status_view(b)
                available = [s for s in seller_order if s not in tried]
                if not available:
                    break
                ch = await b.agent.choose(board=buyer_board, status=buyer_status,
                                          tried=tried, sellers=seller_order)
                sid = resolve_seller_id(ch.seller, sellers) or available[0]
                tried.append(sid)
                s = sellers[sid]
                s.times_approached += 1
                seller_status = seller_status_view(s)

                att = await negotiate_attempt(
                    s, b, seller_board=seller_board, buyer_board=buyer_board,
                    seller_status=seller_status, buyer_status=buyer_status,
                    max_messages=scenario.max_messages, approach_reasoning=ch.private_reasoning)
                turn.attempts.append(att)

                if att.closed:
                    s.deals_closed += 1
                    b.deals_closed += 1
                    turn.closed_with = sid
                    cycle_first_closer.setdefault(sid, bid)
                    break
                else:
                    att.verdict = "vague"
                    s.vague_attempts += 1
                    b.vague_attempts += 1

            cycle_turns.append(turn)
            turns.append(turn)
            if verbose:
                print(f"  round {round_no} buyer={bid} "
                      f"{'-> closed with ' + turn.closed_with if turn.closed_with else '-> no deal'}")

        # resolve the cycle: reveal draws, first closer of each seller wins delivery
        for turn in cycle_turns:
            if not turn.closed_with:
                continue
            sid = turn.closed_with
            s = sellers[sid]
            b = buyers[turn.buyer]
            att = next(a for a in turn.attempts if a.seller == sid and a.closed)
            won = drawn[sid] and cycle_first_closer.get(sid) == turn.buyer
            if won:
                att.verdict = "true"
                turn.delivered = True
                b.owned += 1
                b.deals_delivered += 1
                s.deals_delivered += 1
            else:
                att.verdict = "false"
                b.deals_failed += 1
                s.deals_failed += 1

        cycles.append(Cycle(cycle=cyc_no, drawn=drawn, rounds=[t.round for t in cycle_turns]))
        if verbose:
            got = [sid for sid, d in drawn.items() if d]
            print(f"  cycle {cyc_no} draws: {got or '(none)'}")

    seller_summaries = [
        SellerSummary(id=s.id, name=s.name, arrival_prob=s.agent.p,
                      times_approached=s.times_approached, deals_closed=s.deals_closed,
                      deals_delivered=s.deals_delivered, deals_failed=s.deals_failed,
                      vague_attempts=s.vague_attempts, final_note=s.agent.note)
        for s in sellers.values()
    ]
    buyer_summaries = [
        BuyerSummary(id=b.id, name=b.agent.name, owned=b.owned, turns_taken=b.turns_taken,
                     deals_closed=b.deals_closed, deals_delivered=b.deals_delivered,
                     deals_failed=b.deals_failed, vague_attempts=b.vague_attempts,
                     final_note=b.agent.note)
        for b in buyers.values()
    ]
    seller_winner = max(seller_summaries, key=lambda s: s.deals_closed)
    buyer_champion = max(buyer_summaries, key=lambda b: b.owned)

    return RunResult(
        scenario=scenario.name, description=scenario.description, seed=seed,
        n_sellers=scenario.n_sellers, n_buyers=scenario.n_buyers, k_cycles=scenario.k_cycles,
        n_rounds=scenario.n_rounds,
        load_bearing_assumptions=list(scenario.load_bearing_assumptions),
        cycles=cycles, turns=turns, sellers=seller_summaries, buyers=buyer_summaries,
        seller_winner=seller_winner.id, seller_winner_name=seller_winner.name,
        buyer_champion=buyer_champion.id, buyer_champion_name=buyer_champion.name,
        measurements=build_measurements(turns),
    )
