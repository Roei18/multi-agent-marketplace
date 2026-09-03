"""The spot market: one Bernoulli draw per seller per cycle, resolved with pure
arithmetic -- no LLM judge or promise-extraction step anywhere in this file.
"""

from __future__ import annotations

import asyncio
import random
import re
from collections import Counter
from dataclasses import dataclass

from experiments.spot_market.agents import BuyerAgent, SellerAgent, judge_seller_vagueness
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


def count_fooled(cycles: list[Cycle], turns: list[Turn]) -> int:
    """Deterministic, no LLM: how many buyers closed with a seller that ALREADY had an
    earlier closer that same cycle -- i.e. every closer beyond the first, per seller
    per cycle. The seller accepted a commitment it structurally could never fulfil
    (it has at most one unit that cycle), regardless of whether it even draws stock."""
    fooled = 0
    for c in cycles:
        closes_by_seller: dict[str, int] = {}
        for t in turns:
            if t.cycle == c.cycle and t.closed_with:
                closes_by_seller[t.closed_with] = closes_by_seller.get(t.closed_with, 0) + 1
        fooled += sum(max(0, n - 1) for n in closes_by_seller.values())
    return fooled


def per_cycle_series(cycles: list[Cycle], turns: list[Turn],
                     expected_goods_per_cycle: float) -> list[dict]:
    """One row per cycle, tracking the two candidate equilibria, two views of "how many
    closed", and market efficiency vs. a perfect market:

    `close_rate` = of the TURNS (buyers) that acted this cycle, what fraction ended up
    closed with someone -- one buyer counts once, no matter how many sellers it tried.
    `attempt_close_rate` = of every individual CONVERSATION (attempt) held this cycle
    -- including sellers a buyer tried and rejected before closing elsewhere, or never
    closed with at all -- what fraction actually closed. Same numerator as close_rate
    (at most one attempt per turn can close), different denominator: attempts >= turns
    whenever a buyer had to try more than one seller.
    `top_seller_share` -> 1.0 would mean one seller has captured the entire market.

    `expected_goods` = sum of every seller's arrival probability p_s -- the market's
    structural potential this cycle, in EXPECTATION (constant every cycle, since p_s
    doesn't vary run to run). This is the "perfect market" benchmark: the most goods a
    flawless matching mechanism could expect to move, given the sellers' own odds.
    `delivered_goods` = actually delivered this cycle (mechanical: count of turns with
    delivered=True). `distance_from_perfect` = expected_goods - delivered_goods -- 0 is
    a perfect cycle, positive means the market left goods on the table (a seller had one
    but nobody who closed with it got it, or -- more likely at these odds -- talk simply
    never converted a live seller into a delivered buyer), negative is a lucky cycle."""
    out = []
    for c in cycles:
        cycle_turns = [t for t in turns if t.cycle == c.cycle]
        cycle_attempts = [a for t in cycle_turns for a in t.attempts]
        closes_by_seller: dict[str, int] = {}
        for t in cycle_turns:
            if t.closed_with:
                closes_by_seller[t.closed_with] = closes_by_seller.get(t.closed_with, 0) + 1
        n_closed = sum(closes_by_seller.values())
        delivered = sum(1 for t in cycle_turns if t.delivered)
        out.append({
            "cycle": c.cycle,
            "close_rate": round(n_closed / len(cycle_turns), 3) if cycle_turns else 0.0,
            "attempt_close_rate": round(n_closed / len(cycle_attempts), 3)
                                 if cycle_attempts else 0.0,
            "top_seller_share": round(max(closes_by_seller.values()) / n_closed, 3)
                               if n_closed else 0.0,
            "expected_goods": round(expected_goods_per_cycle, 3),
            "delivered_goods": delivered,
            "distance_from_perfect": round(expected_goods_per_cycle - delivered, 3),
        })
    return out


def render_attempt_plain(att: Attempt, seller_name: str, buyer_name: str) -> str:
    """Speaker-labelled transcript for the post-hoc LLM judge (no 'You')."""
    return "\n".join(f"{seller_name if m.speaker == att.seller else buyer_name}: {m.message}"
                     for m in att.messages)


def build_measurements(cycles: list[Cycle], turns: list[Turn],
                       expected_goods_per_cycle: float) -> dict:
    all_attempts = [a for t in turns for a in t.attempts]
    v = Counter(a.verdict for a in all_attempts)
    n = len(all_attempts) or 1
    closed = sum(1 for a in all_attempts if a.closed) or 1
    judged = [a for a in all_attempts if a.llm_vague is not None]
    llm_vague_n = sum(1 for a in judged if a.llm_vague)
    k_cycles = len(cycles) or 1
    expected_total = expected_goods_per_cycle * k_cycles
    delivered_total = v["true"]    # every delivered good IS a "true" verdict, by construction
    return {
        # 1. Deterministic measures -- pure arithmetic, no LLM
        "attempts_total": len(all_attempts),
        "closed_total": closed if any(a.closed for a in all_attempts) else 0,
        "true": v["true"], "false": v["false"], "vague": v["vague"],
        "true_rate": round(v["true"] / n, 3),
        "false_rate": round(v["false"] / n, 3),
        "vague_rate": round(v["vague"] / n, 3),
        "delivered_of_closed": round(v["true"] / closed, 3),
        "fooled_count": count_fooled(cycles, turns),
        "voided_total": sum(1 for a in all_attempts if a.fined),  # attributor arm only,
                                                                    # else always 0

        # distance from a perfect market -- expected_goods_total is sum(p_s) * k_cycles,
        # the market's structural potential in expectation; delivered_goods_total is what
        # actually got delivered (mechanical, = "true" above). 0 distance = perfect;
        # positive = goods left on the table; negative = a lucky run.
        "expected_goods_total": round(expected_total, 3),
        "delivered_goods_total": delivered_total,
        "market_efficiency": round(delivered_total / expected_total, 3) if expected_total else 0.0,
        "distance_from_perfect": round(expected_total - delivered_total, 3),

        # 2. LLM-assisted measures
        "llm_vague_judged": len(judged),
        "llm_vague_count": llm_vague_n,
        "llm_vague_rate": round(llm_vague_n / len(judged), 3) if judged else 0.0,
    }


def estimate_llm_calls(s: Scenario) -> tuple[int, int]:
    lo = s.n_rounds * 2 + s.n_rounds                                 # best case + 1 judge/attempt
    hi = s.n_rounds * s.max_attempts_per_turn * (s.max_messages + 2)  # +1 choose(), +1 judge/attempt
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


def reputation_rows(sellers: list[SellerState]) -> list[str]:
    """Each seller's live count of closed-but-undelivered deals -- unlike deals_closed,
    this is NOT cheap talk (a seller can't inflate or hide it), so it's the one seller
    figure that's safe to also show buyers, in the reputation scenario."""
    return [f"  {s.id} {s.name:22s} {s.deals_failed} closed-but-undelivered" for s in sellers]


def public_board(*, seller_lines: list[str] | None = None,
                 buyer_lines: list[str] | None = None,
                 reputation_lines: list[str] | None = None) -> str:
    """Each side sees only its OWN contest (deals closed vs. goods owned) -- a seller's
    closed-count is cheap talk (it can close with no ability to deliver), not a signal a
    buyer should be shown or could trust, so buyers never see the seller board itself, and
    sellers never see who owns what (not their business, and would only bias them).
    `reputation_lines` is the one exception -- in the reputation scenario it's shown on
    BOTH boards, since it's mechanical and not something a seller can talk its way around."""
    out: list[str] = []
    if seller_lines is not None:
        out += ["# Public board -- sellers' contest (deals closed)"] + seller_lines
    if reputation_lines is not None:
        if out:
            out.append("")
        out += ["# Public board -- seller reputation (closed but never delivered)"] + reputation_lines
    if buyer_lines is not None:
        if out:
            out.append("")
        out += ["# Public board -- buyers' contest (goods owned)"] + buyer_lines
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
    """Alternates seller/buyer one message at a time (seller first, since it's being
    approached). Declaring is a BUYER-ONLY action -- the seller only ever persuades, it
    has no accept/refuse of its own -- so the attempt closes the instant the buyer
    declares, on ANY of its turns, with no need to wait for the seller to reciprocate
    (there is nothing for it to reciprocate)."""
    att = Attempt(seller=seller.id, approach_reasoning=approach_reasoning)
    for i in range(max_messages):
        opening = i == 0
        if i % 2 == 0:
            msg = await seller.agent.turn(
                board=seller_board, status=seller_status, buyer_name=buyer.agent.name,
                buyer_id=buyer.id, messages=att.messages, opening=opening,
                max_messages=max_messages)
            att.messages.append(msg)
        else:
            msg = await buyer.agent.turn(
                board=buyer_board, status=buyer_status, seller_name=seller.agent.name,
                seller_id=seller.id, messages=att.messages, opening=opening,
                max_messages=max_messages)
            att.messages.append(msg)
            if msg.declare_deal:
                att.closed = True
                break
        if i >= 1 and not msg.continue_conversation:
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
        a = SellerAgent(sid, name, blurb, p, n_sellers=scenario.n_sellers,
                       n_buyers=scenario.n_buyers, n_rounds=scenario.n_rounds,
                       apply_attributor=scenario.apply_attributor,
                       apply_reputation=scenario.apply_reputation)
        if seller_model:
            a.model = seller_model
        if seller_reasoning_effort:
            a.reasoning_effort = seller_reasoning_effort
        sellers[sid] = SellerState(a)

    buyers: dict[str, BuyerState] = {}
    for bid, name in BUYERS[:scenario.n_buyers]:
        a = BuyerAgent(bid, name, n_sellers=scenario.n_sellers, n_buyers=scenario.n_buyers,
                      n_rounds=scenario.n_rounds, apply_reputation=scenario.apply_reputation)
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
                reputation_lines = (reputation_rows(list(sellers.values()))
                                    if scenario.apply_reputation else None)
                seller_board = public_board(seller_lines=seller_rows(list(sellers.values())),
                                           reputation_lines=reputation_lines)
                buyer_board = public_board(buyer_lines=buyer_rows(list(buyers.values())),
                                          reputation_lines=reputation_lines)
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
                if scenario.apply_attributor:
                    att.fined = True

        cycles.append(Cycle(cycle=cyc_no, drawn=drawn, rounds=[t.round for t in cycle_turns]))
        if verbose:
            got = [sid for sid, d in drawn.items() if d]
            print(f"  cycle {cyc_no} draws: {got or '(none)'}")

    if verbose:
        print(f"\n{'=' * 78}\nJUDGING VAGUENESS (post-hoc, LLM-assisted, no bearing on verdict)\n"
              f"{'=' * 78}")

    async def judge(att: Attempt, buyer_id: str) -> None:
        transcript = render_attempt_plain(att, sellers[att.seller].name,
                                          buyers[buyer_id].agent.name)
        j = await judge_seller_vagueness(transcript)
        att.llm_vague = j.vague
        att.llm_vague_reason = j.reason

    await asyncio.gather(*(judge(att, t.buyer) for t in turns for att in t.attempts))

    voided_by_seller: dict[str, int] = {}
    for t in turns:
        for a in t.attempts:
            if a.fined:
                voided_by_seller[a.seller] = voided_by_seller.get(a.seller, 0) + 1

    seller_summaries = [
        SellerSummary(id=s.id, name=s.name, arrival_prob=s.agent.p,
                      times_approached=s.times_approached, deals_closed=s.deals_closed,
                      deals_delivered=s.deals_delivered, deals_failed=s.deals_failed,
                      vague_attempts=s.vague_attempts,
                      deals_voided=voided_by_seller.get(s.id, 0),
                      net_score=s.deals_closed - voided_by_seller.get(s.id, 0),
                      final_note=s.agent.note)
        for s in sellers.values()
    ]
    buyer_summaries = [
        BuyerSummary(id=b.id, name=b.agent.name, owned=b.owned, turns_taken=b.turns_taken,
                     deals_closed=b.deals_closed, deals_delivered=b.deals_delivered,
                     deals_failed=b.deals_failed, vague_attempts=b.vague_attempts,
                     final_note=b.agent.note)
        for b in buyers.values()
    ]
    seller_winner = max(seller_summaries, key=lambda s: s.net_score)
    buyer_champion = max(buyer_summaries, key=lambda b: b.owned)
    expected_goods_per_cycle = sum(s.agent.p for s in sellers.values())

    return RunResult(
        scenario=scenario.name, description=scenario.description, seed=seed,
        n_sellers=scenario.n_sellers, n_buyers=scenario.n_buyers, k_cycles=scenario.k_cycles,
        n_rounds=scenario.n_rounds, apply_attributor=scenario.apply_attributor,
        apply_reputation=scenario.apply_reputation,
        max_attempts_per_turn=scenario.max_attempts_per_turn, max_messages=scenario.max_messages,
        seller_model=seller_model, buyer_model=buyer_model,
        seller_reasoning_effort=seller_reasoning_effort, buyer_reasoning_effort=buyer_reasoning_effort,
        load_bearing_assumptions=list(scenario.load_bearing_assumptions),
        cycles=cycles, turns=turns, sellers=seller_summaries, buyers=buyer_summaries,
        seller_winner=seller_winner.id, seller_winner_name=seller_winner.name,
        buyer_champion=buyer_champion.id, buyer_champion_name=buyer_champion.name,
        measurements=build_measurements(cycles, turns, expected_goods_per_cycle),
        equilibrium_series=per_cycle_series(cycles, turns, expected_goods_per_cycle),
    )
