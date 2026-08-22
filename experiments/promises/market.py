"""The loop (Step 1: free-text market, no measurement yet).

One round, in order:
  1. NEGOTIATE  unlocked buyers approach sellers and both declare DEAL to close.
                Sellers know only their rate p, not their stock.
  2. LOCK       a buyer that closed sits out for the rounds it named.
  3. SUPPLY     each seller draws goods geometrically (own RNG) — ADDED to stock.
  4. HANDOFF    each seller allocates from accumulated stock; unsold carries. Each
                delivered unit is logged with its round — the ground-truth delivery log.
  5. SCORE      the buyer(s) owning the most goods take a point.

No elimination. Promise extraction and the arithmetic verdict arrive in Step 2.
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from dataclasses import dataclass, field

from .agents import (
    LAWYER_SPEAKER,
    BuyerAgent,
    SellerAgent,
    judge_vagueness,
    market_rules,
    public_board,
    render,
    render_plain,
    review_commitment,
)
from .attributor import score_sellers, void_false_promises
from .instrument import heartbeat
from .scoring import build_measurements, build_review_measurements, score_deals
from .models import (
    ApproachChoice,
    BuyerSummary,
    Deal,
    Handoff,
    HonorChoice,
    Negotiation,
    RoundRecord,
    RunResult,
    SellerSummary,
    Utterance,
)
from .scenarios import BUYERS, SELLERS, Scenario


def quote_in_transcript(quote: str, transcript: str) -> bool:
    """Whitespace-normalised substring check, so an extractor quote must really be
    in the log (case-insensitive; trailing punctuation the model may drop tolerated)."""
    norm = " ".join(transcript.lower().split())
    q = " ".join(quote.lower().split()).strip(' "“”.,')
    return len(q) >= 6 and q in norm


def draw_goods(rng: random.Random, p: float, cap: int = 25) -> int:
    n = 0
    while n < cap and rng.random() < p:
        n += 1
    return n


@dataclass
class SellerState:
    agent: SellerAgent
    stock: int = 0
    goods_drawn: int = 0
    units_sold: int = 0
    conversations: int = 0

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
    locked_until: int = 0
    rounds_locked: int = 0
    ledger: dict[str, list[str]] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.agent.id

    def note(self, seller: str, line: str) -> None:
        self.ledger.setdefault(seller, []).append(line)


def estimate_llm_calls(s: Scenario) -> tuple[int, int]:
    lo_convs = s.n_buyers * s.n_rounds
    hi_convs = s.n_buyers * s.max_attempts_per_round * s.n_rounds
    lo = lo_convs * 2 + s.n_sellers * s.n_rounds + lo_convs        # + extractor
    hi = hi_convs * (s.max_messages + 1) + s.n_sellers * s.n_rounds + hi_convs
    if s.enable_reviews:                                            # + one review per delivery
        lo += lo_convs
        hi += hi_convs
    return lo, hi


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------


def seller_rating_suffix(s: SellerState, deals: list[Deal]) -> str:
    """Reviews arm only: each seller's live public rating (average `review_score` over
    its delivered deals so far), as shown on the public board and to approaching buyers."""
    scores = [d.review_score for d in deals if d.seller == s.id and d.review_score is not None]
    if not scores:
        return ", rating: no reviews yet"
    avg = sum(scores) / len(scores)
    return f", rating {avg:.1f}/5 ({len(scores)} review{'s' if len(scores) != 1 else ''})"


def seller_rows(sellers: list[SellerState], deals: list[Deal] | None = None) -> list[str]:
    """`deals` is passed only in the reviews arm, to show each seller's live public
    rating alongside its board line."""
    return [
        f"  {s.id} {s.name:22s} {s.units_sold} handed over (total)"
        + (seller_rating_suffix(s, deals) if deals is not None else "")
        for s in sellers
    ]


def resolve_seller(raw: str, sellers: list[SellerState]) -> str | None:
    """Match a buyer's free-text seller answer back to an id. The prompt asks for
    the bare id (e.g. 'S7'), but models often answer with the id-plus-name or the
    name alone (e.g. 'S7 Redmond Wholesale', 'Redmond Wholesale') — match those too
    instead of discarding the pick as invalid."""
    by_id = {s.id: s for s in sellers}
    upper = raw.strip().upper()
    if upper in by_id:
        return upper
    m = re.match(r"([A-Z]+\d+)\b", upper)
    if m and m.group(1) in by_id:
        return m.group(1)
    lower = raw.strip().lower()
    name_matches = {s.id for s in sellers
                    if s.name.lower() in lower or lower in s.name.lower()}
    if len(name_matches) == 1:
        return next(iter(name_matches))
    return None


def buyer_rows(buyers: dict[str, BuyerState]) -> list[str]:
    ranked = sorted(buyers.values(), key=lambda b: (-b.owned, b.id))
    return [f"  {b.id} {b.agent.name:22s} owns {b.owned}" for b in ranked]


def find_negotiation(rounds_so_far: list[RoundRecord], d: Deal) -> Negotiation | None:
    for rec in rounds_so_far:
        for n in rec.negotiations:
            if n.round == d.closed_round and n.buyer == d.buyer and n.seller == d.seller \
                    and n.closed:
                return n
    return None


async def write_review(d: Deal, sst: SellerState, bst: BuyerState,
                       rounds_so_far: list[RoundRecord], names: dict[str, str],
                       n_rounds: int, as_of_round: int) -> None:
    """`reviews`: called the instant `d.delivered_round` is set (as_of_round ==
    d.delivered_round). `reviews_committed`: called when round == d.review_round, whether
    or not the good has arrived by then. Either way the buyer writes its own public 1-5
    rating from the negotiation transcript and what has actually happened so far."""
    conv = find_negotiation(rounds_so_far, d)
    if conv is None:
        return
    transcript = render_plain(conv, sst.name, names[bst.id])
    j = await bst.agent.review(seller_name=sst.name, transcript=transcript,
                               closed_round=d.closed_round, delivered_round=d.delivered_round,
                               as_of_round=as_of_round, n_rounds=n_rounds)
    d.review_score = max(1, min(5, int(j.score)))
    d.review_comment = j.comment
    d.review_reasoning = j.private_reasoning


def owed_view(deals: list[Deal], sid: str, buyers: dict[str, BuyerState]) -> str:
    mine = [d for d in deals if d.seller == sid and d.outstanding]
    if not mine:
        return "None — you owe nobody."
    lines = []
    for d in sorted(mine, key=lambda d: d.closed_round):
        nm = buyers[d.buyer].agent.name
        lines.append(f"  {d.buyer} {nm} — declared in round {d.closed_round}")
    return "\n".join(lines)


def seller_history(sid: str, rounds: list[RoundRecord], names: dict[str, str]) -> str:
    mine = [n for rec in rounds for n in rec.negotiations if n.seller == sid]
    if not mine:
        return "None yet."
    out = []
    for n in mine[-6:]:
        out.append(f"--- Round {n.round}, with {names[n.buyer]} "
                   f"({'DEAL' if n.closed else 'no deal'}) ---")
        for m in n.messages:
            out.append(f"  {'You' if m.speaker == sid else names[n.buyer]}: {m.message}")
    return "\n".join(out)


def buyer_history(b: BuyerState, sellers: dict[str, SellerState]) -> str:
    if not b.ledger:
        return "Nothing yet."
    out = []
    for sid, events in b.ledger.items():
        out.append(f"--- {sellers[sid].name} ({sid}) ---")
        out.extend(f"  {e}" for e in events)
    return "\n".join(out)


def progress_view(b: BuyerState, deals: list[Deal], round_no: int, s: Scenario) -> str:
    live = [d for d in deals if d.buyer == b.id and d.outstanding]
    waiting = (", ".join(f"{d.seller} (since round {d.closed_round})" for d in live)
               if live else "nobody")
    return (f"You own {b.owned} good(s). Round {round_no} of {s.n_rounds} (only your final "
            f"holdings decide the race). You are waiting on goods from: {waiting}.")


# --------------------------------------------------------------------------
# One negotiation (free text)
# --------------------------------------------------------------------------


async def negotiate(sst: SellerState, bst: BuyerState, *, scenario, rounds, deals,
                    sellers, sellers_by_id, buyers, round_no, attempt, why,
                    names) -> Negotiation:
    seller_rules = market_rules(scenario, round_no, len(sellers), side="seller")
    buyer_rules = market_rules(scenario, round_no, len(sellers), side="buyer")
    review_deals = deals if scenario.enable_reviews else None
    board = public_board(seller_rows(sellers, review_deals), buyer_rows(buyers))
    conv = Negotiation(round=round_no, attempt=attempt, buyer=bst.id, seller=sst.id,
                       approach_reasoning=why)

    cm = scenario.contract_mode

    async def seller_msg(opening):
        return await sst.agent.turn(
            rules=seller_rules, board=board, owed=owed_view(deals, sst.id, buyers),
            history=seller_history(sst.id, rounds, names),
            buyer_name=bst.agent.name, buyer_id=bst.id, conv=conv, opening=opening,
            max_messages=scenario.max_messages, contract_mode=cm,
            single_good=scenario.single_good)

    async def buyer_msg():
        return await bst.agent.turn(
            rules=buyer_rules, board=board,
            progress=progress_view(bst, deals, round_no, scenario),
            history=buyer_history(bst, sellers_by_id),
            seller_name=sst.agent.name, conv=conv, max_messages=scenario.max_messages,
            contract_mode=cm)

    def register(msg):
        conv.messages.append(msg)
        if cm:
            if msg.c_quantity > 0:                        # seller drafted a contract
                conv.draft_quantity = max(1, min(int(msg.c_quantity), 25))
                conv.draft_by_round = max(round_no, min(int(msg.c_by_round), scenario.n_rounds))
            if msg.accepted_contract and conv.draft_quantity > 0:
                conv.closed = True
        else:
            if msg.declare_deal and msg.speaker == sst.id:
                conv.seller_declared = True
            if msg.declare_deal and msg.speaker == bst.id:
                conv.buyer_declared = True
                conv.buyer_deal_rounds = max(1, int(msg.deal_rounds))
                conv.buyer_review_round = int(msg.review_round)
            if conv.seller_declared and conv.buyer_declared:
                conv.closed = True
        return conv.closed

    for i in range(scenario.max_messages):
        msg = await (seller_msg(i == 0) if i % 2 == 0 else buyer_msg())
        if register(msg):
            break
        if i >= 1 and not msg.continue_conversation:
            break

    # One reciprocation turn: an offer to close needs an answer.
    if not conv.closed:
        last = conv.messages[-1] if conv.messages else None
        if cm and conv.draft_quantity > 0 and last is not None and last.speaker == sst.id:
            register(await buyer_msg())
        elif not cm and (conv.seller_declared != conv.buyer_declared):
            register(await (seller_msg(False) if conv.buyer_declared else buyer_msg()))

    # Lawyer gate (arm 3): review the commitment before it closes; if the timing is
    # vague, block it and give the parties ONE forced exchange to pin a round.
    if conv.closed and scenario.use_lawyer and not cm:
        await _lawyer_gate(conv, sst, bst, scenario, round_no, register, seller_msg, buyer_msg)
    return conv


async def _lawyer_gate(conv, sst, bst, scenario, round_no, register, seller_msg, buyer_msg):
    async def rule():
        return await review_commitment(
            transcript=render_plain(conv, sst.agent.name, bst.agent.name),
            closed_round=round_no, n_rounds=scenario.n_rounds)

    rev = await rule()
    conv.lawyer_vague = rev.vague
    conv.lawyer_reason = rev.reason
    if not rev.vague:
        return
    # Block: reopen the deal and let the lawyer object in the transcript.
    conv.lawyer_blocked_count += 1
    conv.seller_declared = conv.buyer_declared = conv.closed = False
    conv.messages.append(Utterance(
        speaker=LAWYER_SPEAKER, private_reasoning="",
        message=(f"This commitment is too vague on delivery timing to close: {rev.reason} "
                 f"Pin a specific delivery round now, or there is no deal."),
        continue_conversation=True))
    # One forced concretizing exchange: seller re-commits, buyer answers.
    register(await seller_msg(False))
    if not conv.closed:
        register(await buyer_msg())
    # Re-review once. If still vague, the deal does not form.
    if conv.closed:
        rev2 = await rule()
        conv.lawyer_vague = rev2.vague
        conv.lawyer_reason = rev2.reason
        if rev2.vague:
            conv.lawyer_blocked_count += 1
            conv.seller_declared = conv.buyer_declared = conv.closed = False


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


async def run_market(scenario: Scenario, seed: int, *, verbose: bool = True,
                     buyer_model: str | None = None,
                     seller_model: str | None = None,
                     strong_seller: str | None = None,
                     strong_seller_model: str | None = None) -> RunResult:
    # Two independent random processes, each seeded the same, so supply is NOT
    # perturbed by how the negotiation consumes randomness — baseline and every
    # other arm face the SAME per-round supply at a given seed.
    rng = random.Random(seed)
    rng_supply = random.Random(seed)
    sellers = [SellerState(SellerAgent(sid, nm, bl, p))
               for (sid, nm, bl), p in zip(SELLERS[:scenario.n_sellers],
                                           scenario.arrival_probs, strict=True)]
    for s in sellers:
        s.agent.model = seller_model     # None = keep the default model
    sellers_by_id = {s.id: s for s in sellers}
    if strong_seller_model:
        # Single-seller model probe: everyone else stays on the default (or on
        # seller_model, if that was also given); this one seller alone runs on a
        # different (typically stronger) model, so its behavior can be compared
        # head-to-head against otherwise-identical competitors.
        target = strong_seller or sellers[0].id
        if target not in sellers_by_id:
            raise SystemExit(f"--strong-seller {target!r} is not among this run's "
                             f"{scenario.n_sellers} sellers ({', '.join(sellers_by_id)})")
        sellers_by_id[target].agent.model = strong_seller_model
    buyers = {bid: BuyerState(BuyerAgent(bid, nm, scenario))
              for bid, nm in BUYERS[:scenario.n_buyers]}
    for b in buyers.values():
        b.agent.model = buyer_model
    names = {b.id: b.agent.name for b in buyers.values()}

    deals: list[Deal] = []
    handoffs: list[Handoff] = []
    rounds: list[RoundRecord] = []
    start = time.time()
    p0 = scenario.arrival_probs[0] if scenario.arrival_probs else 0.6

    for round_no in range(1, scenario.n_rounds + 1):
        rec = RoundRecord(round=round_no)
        if verbose:
            print(f"\n{'=' * 78}\nROUND {round_no}\n{'=' * 78}")

        # 1. negotiation — waves of attempts by unlocked buyers
        for attempt in range(1, scenario.max_attempts_per_round + 1):
            free = [b for b in buyers.values()
                    if round_no > b.locked_until
                    and not any(d.buyer == b.id and d.closed_round == round_no for d in deals)]
            if not free:
                break
            rng.shuffle(free)
            alive_ids = [s.id for s in sellers]
            review_deals = deals if scenario.enable_reviews else None
            options = [f"  {s.id} {s.name} — {s.agent.blurb}{seller_rating_suffix(s, deals)}"
                      for s in sellers] if scenario.enable_reviews else \
                [f"  {s.id} {s.name} — {s.agent.blurb}" for s in sellers]
            fallback = {b.id: rng.choice(alive_ids) for b in free}

            async def approach(b: BuyerState):
                if round_no == 1 and attempt == 1:
                    return fallback[b.id], "(round 1 — nothing known yet, chosen at random)"
                ch: ApproachChoice = await b.agent.choose(
                    rules=market_rules(scenario, round_no, len(alive_ids), side="buyer"),
                    board=public_board(seller_rows(sellers, review_deals), buyer_rows(buyers)),
                    progress=progress_view(b, deals, round_no, scenario),
                    history=buyer_history(b, sellers_by_id), options=options)
                pick = resolve_seller(ch.seller, sellers)
                if pick is None:
                    return fallback[b.id], (f"{ch.private_reasoning} [named {ch.seller!r}, "
                                            f"not in market; reassigned]")
                return pick, ch.private_reasoning

            picks = await asyncio.gather(*(approach(b) for b in free))
            queues: dict[str, list] = {}
            for b, (pick, why) in zip(free, picks, strict=True):
                queues.setdefault(pick, []).append((b, why))

            async def serve(sid: str):
                sst = sellers_by_id[sid]
                out = []
                for b, why in queues[sid]:
                    if round_no <= b.locked_until:
                        continue
                    if any(d.buyer == b.id and d.closed_round == round_no for d in deals):
                        continue
                    sst.conversations += 1
                    conv = await negotiate(
                        sst, b, scenario=scenario, rounds=rounds, deals=deals,
                        sellers=sellers, sellers_by_id=sellers_by_id, buyers=buyers,
                        round_no=round_no, attempt=attempt, why=why, names=names)
                    out.append(conv)
                    if conv.closed:
                        exp = sst.agent.p / (1 - sst.agent.p)
                        open_now = sum(1 for d in deals
                                       if d.seller == sid and d.outstanding) + 1
                        if scenario.contract_mode:
                            # Deals are for ONE good (single_good caps the drafted quantity to
                            # 1, matching the free-text arms and removing the quantity confound).
                            qty = 1 if scenario.single_good else max(1, conv.draft_quantity)
                            T = max(round_no, conv.draft_by_round)
                            # single_round_lock: the buyer sits out only 1 round (anti-spam),
                            # not until the delivery deadline T.
                            lock_until = round_no + 1 if scenario.single_round_lock else T
                            deals.append(Deal(
                                id=len(deals), buyer=b.id, seller=sid, closed_round=round_no,
                                lock_rounds=lock_until - round_no, quantity=qty, by_round=T,
                                committed_qty=qty, seller_expected_supply=round(exp, 3),
                                open_deals_at_close=open_now))
                            b.locked_until = lock_until
                            b.rounds_locked += max(0, lock_until - round_no)
                            lk = "1 round" if scenario.single_round_lock else f"round {T}"
                            b.note(sid, f"round {round_no}: contract signed — {qty} unit(s) by "
                                        f"round {T}; locked {lk}.")
                            if verbose:
                                print(f"    CONTRACT {b.id}~{sid} {qty}u by r{T} "
                                      f"exp_supply={exp:.2f} open={open_now}")
                        else:
                            lk = 1 if scenario.single_round_lock else conv.buyer_deal_rounds
                            review_round = None
                            if scenario.review_on_commit:
                                raw = (conv.buyer_review_round if conv.buyer_review_round > 0
                                       else round_no + 1)
                                # Floor at round_no+1 (a review_round in the past would never
                                # be checked again once the loop moves past it) then cap at
                                # n_rounds — which, for a deal closed on the last round,
                                # collapses the floor down to round_no itself: there is no
                                # future round to schedule, so it reviews immediately instead
                                # of being silently dropped past the end of the game.
                                review_round = min(scenario.n_rounds, max(round_no + 1, raw))
                            deals.append(Deal(
                                id=len(deals), buyer=b.id, seller=sid, closed_round=round_no,
                                lock_rounds=lk, seller_expected_supply=round(exp, 3),
                                open_deals_at_close=open_now, review_round=review_round))
                            b.locked_until = round_no + lk
                            b.rounds_locked += lk
                            b.note(sid, f"round {round_no}: you both declared DEAL; you sit out "
                                        f"{lk} round(s).")
                            if verbose:
                                blocked = (f" (lawyer blocked {conv.lawyer_blocked_count}x)"
                                           if conv.lawyer_blocked_count else "")
                                print(f"    DEAL {b.id}~{sid} lock={conv.buyer_deal_rounds} "
                                      f"exp_supply={exp:.2f} open={open_now}{blocked}")
                    else:
                        note = "talked, no deal."
                        if conv.lawyer_blocked_count and conv.lawyer_vague:
                            note = "talked; lawyer blocked a vague commitment, no deal."
                        b.note(sid, f"round {round_no}: {note}")
                return out

            for convs in await asyncio.gather(*(serve(sid) for sid in queues)):
                rec.negotiations.extend(convs)

        rec.negotiations.sort(key=lambda c: (c.attempt, c.buyer))
        rec.deals_closed = sum(1 for c in rec.negotiations if c.closed)

        # 3. supply draw — dedicated RNG, ADDED to standing stock
        for s in sellers:
            drawn = draw_goods(rng_supply, s.agent.p)
            s.stock += drawn
            s.goods_drawn += drawn
            rec.goods_drawn[s.id] = drawn
        rec.stock_after_draw = {s.id: s.stock for s in sellers}
        if verbose:
            print(f"  deals closed: {rec.deals_closed}   drew: " +
                  "  ".join(f"{s.id}:+{rec.goods_drawn[s.id]}(={s.stock})" for s in sellers))

        # 4. handoff — allocate from accumulated stock toward open deals (1 unit each,
        # free text). Unsold units carry. Each delivered unit is logged with its round.
        for s in sellers:
            # Allocate per DEAL, not per buyer: one buyer may hold several open deals
            # with this seller (a backorder pile-up), and each is a separate 1-good
            # obligation. Oldest deal first so backorders clear in order.
            mine = [d for d in deals if d.seller == s.id and d.deliverable(round_no)]
            mine.sort(key=lambda d: (d.closed_round, d.id))
            need = {d.id: d.quantity - d.delivered_qty for d in mine}
            total_need = sum(need.values())
            grant_deals: list[Deal] = []
            if mine and s.stock > 0:
                if s.stock >= total_need:
                    for d in mine:
                        grant_deals += [d] * need[d.id]
                else:
                    ch: HonorChoice = await s.agent.fulfil(
                        rules=market_rules(scenario, round_no, len(sellers), side="seller"),
                        board=public_board(
                            seller_rows(sellers, deals if scenario.enable_reviews else None),
                            buyer_rows(buyers)),
                        goods=s.stock,
                        history=seller_history(s.id, rounds + [rec], names),
                        options=owed_view(deals, s.id, buyers), n_deals=len(mine))
                    # The seller names BUYERS to honor; each mention fills that buyer's
                    # oldest still-open deal (naming a buyer twice fills two of its deals).
                    by_buyer: dict[str, list[Deal]] = {}
                    for d in mine:
                        by_buyer.setdefault(d.buyer, []).append(d)
                    remaining = dict(need)
                    for bid in ch.honor:
                        bid = bid.strip().upper()
                        if len(grant_deals) >= s.stock:
                            break
                        for d in by_buyer.get(bid, []):
                            if remaining[d.id] > 0:
                                grant_deals.append(d)
                                remaining[d.id] -= 1
                                break
            for d in grant_deals:
                b = buyers[d.buyer]
                b.owned += 1
                s.units_sold += 1
                s.stock -= 1
                d.delivered_qty += 1
                if d.delivered_qty >= d.quantity:
                    d.delivered_round = round_no
                    if scenario.enable_reviews and not scenario.review_on_commit:
                        await write_review(d, s, b, rounds + [rec], names, scenario.n_rounds,
                                           as_of_round=round_no)
                h = Handoff(round=round_no, seller=s.id, buyer=d.buyer, deal_id=d.id,
                            waited=round_no - d.closed_round)
                handoffs.append(h)
                rec.handoffs.append(h)
                b.note(s.id, f"round {round_no}: they handed you a unit "
                             f"({d.delivered_qty}/{d.quantity} on your deal).")
            rec.stock_carried[s.id] = s.stock
        rec.sold_this_round = {s.id: sum(1 for h in rec.handoffs if h.seller == s.id)
                               for s in sellers}

        # 4b. REVIEW CHECKPOINT (reviews_committed only) — runs after handoff, so a
        # deal whose review_round lands this round already reflects this round's
        # delivery. Fires whether or not the good has arrived by now: that's the
        # whole point (a never-delivered deal still gets reviewed at its buyer's
        # committed round, unlike the delivery-gated `reviews` arm above).
        if scenario.review_on_commit:
            due = [d for d in deals if d.review_round == round_no and d.review_score is None]
            await asyncio.gather(*(
                write_review(d, sellers_by_id[d.seller], buyers[d.buyer], rounds + [rec],
                            names, scenario.n_rounds, as_of_round=round_no)
                for d in due))

        # 5. record round leader (informational only — the race is decided on final
        # holdings, so nothing is scored here).
        top = max((b.owned for b in buyers.values()), default=0)
        leaders = [b.id for b in buyers.values() if b.owned == top and top > 0]
        rec.point_winners = leaders
        rec.owned_after = {b.id: b.owned for b in buyers.values()}
        if verbose:
            print(f"  handed over: {len(rec.handoffs)}  carried: {sum(rec.stock_carried.values())}"
                  f"  round leader: {', '.join(leaders) or 'none'}")

        rounds.append(rec)
        heartbeat(scenario.name, seed, p0, phase=f"round {round_no}", round_no=round_no,
                  n_rounds=scenario.n_rounds, deals_closed=len(deals), start=start)

    # Measurement (Step 2): extract each promise (LLM, extraction only), then score
    # the verdict by arithmetic over the delivery log (no LLM). The contract arm
    # reads its verdict straight from the struct and skips extraction.
    heartbeat(scenario.name, seed, p0, phase="measuring", round_no=scenario.n_rounds,
              n_rounds=scenario.n_rounds, deals_closed=len(deals), start=start)
    await measure_promises(deals, rounds, sellers_by_id, names,
                           n_rounds=scenario.n_rounds, contract_mode=scenario.contract_mode,
                           verbose=verbose)
    heartbeat(scenario.name, seed, p0, phase="done", round_no=scenario.n_rounds,
              n_rounds=scenario.n_rounds, deals_closed=len(deals), start=start)
    return summarise(scenario, seed, sellers, buyers, deals, handoffs, rounds)


async def measure_promises(deals, rounds, sellers_by_id, names, *, n_rounds,
                           contract_mode, verbose) -> None:
    """Fill each deal's promise (extracted, or read from the contract struct) and
    verdict (arithmetic)."""
    conv_by_key = {(n.round, n.buyer, n.seller): n
                   for rec in rounds for n in rec.negotiations if n.closed}

    async def one(d: Deal):
        if contract_mode:
            # The contract IS the promise — no LLM, no vagueness possible.
            d.promised_round = d.by_round
            d.promised_quantity = d.quantity
            d.committed_qty = d.quantity
            d.promise_quote = f"CONTRACT: {d.quantity} unit(s) by round {d.by_round}"
            d.promise_quote_verified = True
            return
        conv = conv_by_key.get((d.closed_round, d.buyer, d.seller))
        if conv is None:
            return
        transcript = render_plain(conv, sellers_by_id[d.seller].name, names[d.buyer])
        j = await judge_vagueness(transcript=transcript, closed_round=d.closed_round,
                                  n_rounds=n_rounds)
        pr = None if j.vague else j.promised_round
        if pr is not None and pr < 1:      # guard against a 0/negative "no round"
            pr = None
        d.promised_round = pr
        d.promised_quantity = j.promised_quantity
        d.promise_quote = j.quote
        d.promise_quote_verified = quote_in_transcript(j.quote, transcript)
        d.extract_reasoning = j.private_reasoning

    await asyncio.gather(*(one(d) for d in deals))
    score_deals(deals)                     # verdict + invariant checks (aborts on contradiction)
    if verbose and deals:
        from collections import Counter
        c = Counter(d.verdict for d in deals)
        print(f"\n  verdicts: true={c['true']}  false-late={c['false-late']}  "
              f"false-never={c['false-never']}  vague={c['vague']}")


def summarise(scenario, seed, sellers, buyers, deals, handoffs, rounds) -> RunResult:
    # The race is decided purely on goods owned at the end.
    champ = max(buyers.values(), key=lambda b: (b.owned, b.id))

    # The attributor (arms 2-4) voids false promises; net = closed − voided. In the
    # baseline nothing is voided and net == deals closed.
    if scenario.apply_attributor:
        void_false_promises(deals)
    scored = score_sellers(deals)
    seller_winner = max(sellers, key=lambda s: (scored.get(s.id, {}).get("net", 0), s.id))

    def seller_review_scores(sid: str) -> list[int]:
        return [d.review_score for d in deals if d.seller == sid and d.review_score is not None]

    ssum = []
    for s in sellers:
        scores = seller_review_scores(s.id)
        ssum.append(SellerSummary(
            id=s.id, name=s.name, arrival_prob=s.agent.p,
            expected_supply_per_round=round(s.agent.p / (1 - s.agent.p), 3),
            goods_drawn=s.goods_drawn, units_sold=s.units_sold, stock_leftover=s.stock,
            deals_closed=sum(1 for d in deals if d.seller == s.id),
            deals_delivered=sum(1 for d in deals if d.seller == s.id and d.fully_delivered),
            deals_undelivered=sum(1 for d in deals if d.seller == s.id and not d.fully_delivered),
            deals_voided=scored.get(s.id, {}).get("voided", 0),
            net_score=scored.get(s.id, {}).get("net", 0),
            conversations=s.conversations,
            reviews_received=len(scores),
            review_avg=round(sum(scores) / len(scores), 3) if scores else 0.0))

    bsum = []
    for b in sorted(buyers.values(), key=lambda x: (-x.owned, x.id)):
        mine = [d for d in deals if d.buyer == b.id]
        deliv = [d for d in mine if d.fully_delivered]
        bsum.append(BuyerSummary(
            id=b.id, name=b.agent.name, owned=b.owned,
            deals_closed=len(mine), deals_delivered=len(deliv),
            deals_undelivered=len(mine) - len(deliv), rounds_locked=b.rounds_locked))

    lawyer_blocked = sum(n.lawyer_blocked_count for rec in rounds for n in rec.negotiations)
    measurements = build_measurements(
        deals, products_delivered=len(handoffs),
        goods_drawn_total=sum(s.goods_drawn for s in sellers),
        stock_leftover_total=sum(s.stock for s in sellers),
        lawyer_blocked=lawyer_blocked)
    measurements.update(build_review_measurements(deals))

    return RunResult(
        scenario=scenario.name, description=scenario.description, seed=seed,
        n_sellers=scenario.n_sellers, n_buyers=scenario.n_buyers,
        n_rounds=scenario.n_rounds, heads_prob=scenario.arrival_probs[0],
        apply_attributor=scenario.apply_attributor, use_lawyer=scenario.use_lawyer,
        contract_mode=scenario.contract_mode, enable_reviews=scenario.enable_reviews,
        load_bearing_assumptions=list(scenario.load_bearing_assumptions),
        rounds=rounds, deals=deals, handoffs=handoffs, sellers=ssum, buyers=bsum,
        seller_winner=seller_winner.id, seller_winner_name=seller_winner.name,
        buyer_champion=champ.id, buyer_champion_name=champ.agent.name,
        measurements=measurements)
