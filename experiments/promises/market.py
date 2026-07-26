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
from dataclasses import dataclass, field

from .agents import (
    BuyerAgent,
    SellerAgent,
    extract_promise,
    market_rules,
    public_board,
    render_plain,
)
from .scoring import score_deals
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
    return lo, hi


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------


def seller_rows(sellers: list[SellerState]) -> list[str]:
    return [f"  {s.id} {s.name:22s} {s.units_sold} handed over (total)" for s in sellers]


def buyer_rows(buyers: dict[str, BuyerState]) -> list[str]:
    ranked = sorted(buyers.values(), key=lambda b: (-b.owned, b.id))
    return [f"  {b.id} {b.agent.name:22s} owns {b.owned}" for b in ranked]


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
    board = public_board(seller_rows(sellers), buyer_rows(buyers))
    conv = Negotiation(round=round_no, attempt=attempt, buyer=bst.id, seller=sst.id,
                       approach_reasoning=why)

    async def seller_msg(opening):
        return await sst.agent.turn(
            rules=seller_rules, board=board, owed=owed_view(deals, sst.id, buyers),
            history=seller_history(sst.id, rounds, names),
            buyer_name=bst.agent.name, buyer_id=bst.id, conv=conv, opening=opening,
            max_messages=scenario.max_messages)

    async def buyer_msg():
        return await bst.agent.turn(
            rules=buyer_rules, board=board,
            progress=progress_view(bst, deals, round_no, scenario),
            history=buyer_history(bst, sellers_by_id),
            seller_name=sst.agent.name, conv=conv, max_messages=scenario.max_messages)

    def register(msg):
        conv.messages.append(msg)
        if msg.declare_deal and msg.speaker == sst.id:
            conv.seller_declared = True
        if msg.declare_deal and msg.speaker == bst.id:
            conv.buyer_declared = True
            conv.buyer_deal_rounds = max(1, int(msg.deal_rounds))
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
    if not conv.closed and (conv.seller_declared != conv.buyer_declared):
        register(await (seller_msg(False) if conv.buyer_declared else buyer_msg()))
    return conv


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


async def run_market(scenario: Scenario, seed: int, *, verbose: bool = True) -> RunResult:
    # Two independent random processes, each seeded the same, so supply is NOT
    # perturbed by how the negotiation consumes randomness — baseline and every
    # other arm face the SAME per-round supply at a given seed.
    rng = random.Random(seed)
    rng_supply = random.Random(seed)
    sellers = [SellerState(SellerAgent(sid, nm, bl, p))
               for (sid, nm, bl), p in zip(SELLERS[:scenario.n_sellers],
                                           scenario.arrival_probs, strict=True)]
    sellers_by_id = {s.id: s for s in sellers}
    buyers = {bid: BuyerState(BuyerAgent(bid, nm, scenario))
              for bid, nm in BUYERS[:scenario.n_buyers]}
    names = {b.id: b.agent.name for b in buyers.values()}

    deals: list[Deal] = []
    handoffs: list[Handoff] = []
    rounds: list[RoundRecord] = []

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
            options = [f"  {s.id} {s.name} — {s.agent.blurb}" for s in sellers]
            fallback = {b.id: rng.choice(alive_ids) for b in free}

            async def approach(b: BuyerState):
                if round_no == 1 and attempt == 1:
                    return fallback[b.id], "(round 1 — nothing known yet, chosen at random)"
                ch: ApproachChoice = await b.agent.choose(
                    rules=market_rules(scenario, round_no, len(alive_ids), side="buyer"),
                    board=public_board(seller_rows(sellers), buyer_rows(buyers)),
                    progress=progress_view(b, deals, round_no, scenario),
                    history=buyer_history(b, sellers_by_id), options=options)
                pick = ch.seller.strip().upper()
                if pick not in alive_ids:
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
                        deals.append(Deal(
                            id=len(deals), buyer=b.id, seller=sid, closed_round=round_no,
                            lock_rounds=conv.buyer_deal_rounds,
                            seller_expected_supply=round(exp, 3),
                            open_deals_at_close=open_now))
                        b.locked_until = round_no + conv.buyer_deal_rounds
                        b.rounds_locked += conv.buyer_deal_rounds
                        b.note(sid, f"round {round_no}: you both declared DEAL; you sit out "
                                    f"{conv.buyer_deal_rounds} round(s).")
                        if verbose:
                            print(f"    DEAL {b.id}~{sid} lock={conv.buyer_deal_rounds} "
                                  f"exp_supply={exp:.2f} open={open_now}")
                    else:
                        b.note(sid, f"round {round_no}: talked, no deal.")
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
            mine = [d for d in deals if d.seller == s.id and d.deliverable(round_no)]
            need = {d.buyer: d.quantity - d.delivered_qty for d in mine}
            total_need = sum(need.values())
            grants: list[str] = []
            if mine and s.stock > 0:
                if s.stock >= total_need:
                    for d in mine:
                        grants += [d.buyer] * need[d.buyer]
                else:
                    ch: HonorChoice = await s.agent.fulfil(
                        rules=market_rules(scenario, round_no, len(sellers), side="seller"),
                        board=public_board(seller_rows(sellers), buyer_rows(buyers)),
                        goods=s.stock,
                        history=seller_history(s.id, rounds + [rec], names),
                        options=owed_view(deals, s.id, buyers), n_deals=len(mine))
                    left = dict(need)
                    for bid in ch.honor:
                        bid = bid.strip().upper()
                        if left.get(bid, 0) > 0 and len(grants) < s.stock:
                            grants.append(bid)
                            left[bid] -= 1
            by_id = {d.buyer: d for d in mine}
            for bid in grants:
                d = by_id[bid]
                b = buyers[bid]
                b.owned += 1
                s.units_sold += 1
                s.stock -= 1
                d.delivered_qty += 1
                if d.delivered_qty >= d.quantity:
                    d.delivered_round = round_no
                h = Handoff(round=round_no, seller=s.id, buyer=bid, deal_id=d.id,
                            waited=round_no - d.closed_round)
                handoffs.append(h)
                rec.handoffs.append(h)
                b.note(s.id, f"round {round_no}: they handed you a unit "
                             f"({d.delivered_qty}/{d.quantity} on your deal).")
            rec.stock_carried[s.id] = s.stock
        rec.sold_this_round = {s.id: sum(1 for h in rec.handoffs if h.seller == s.id)
                               for s in sellers}

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

    # Measurement (Step 2): extract each promise (LLM, extraction only), then score
    # the verdict by arithmetic over the delivery log (no LLM). The contract arm
    # (Step 5) reads its verdict straight from the struct and skips extraction.
    await measure_promises(deals, rounds, sellers_by_id, names,
                           n_rounds=scenario.n_rounds, verbose=verbose)
    return summarise(scenario, seed, sellers, buyers, deals, handoffs, rounds)


async def measure_promises(deals, rounds, sellers_by_id, names, *, n_rounds, verbose) -> None:
    """Fill each deal's promise (extracted) and verdict (arithmetic)."""
    conv_by_key = {(n.round, n.buyer, n.seller): n
                   for rec in rounds for n in rec.negotiations if n.closed}

    async def one(d: Deal):
        conv = conv_by_key.get((d.closed_round, d.buyer, d.seller))
        if conv is None:
            return
        transcript = render_plain(conv, sellers_by_id[d.seller].name, names[d.buyer])
        ex = await extract_promise(transcript=transcript, closed_round=d.closed_round,
                                   n_rounds=n_rounds)
        pr = ex.promised_round
        if pr is not None and pr < 1:      # guard against a 0/negative "no round"
            pr = None
        d.promised_round = pr
        d.promised_quantity = ex.promised_quantity
        d.promise_quote = ex.quote
        d.promise_quote_verified = quote_in_transcript(ex.quote, transcript)
        d.extract_reasoning = ex.private_reasoning

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
    # Step 1: no attributor yet — net score is just deals closed.
    seller_winner = max(
        sellers, key=lambda s: (sum(1 for d in deals if d.seller == s.id), s.id))

    ssum = [SellerSummary(
        id=s.id, name=s.name, arrival_prob=s.agent.p,
        expected_supply_per_round=round(s.agent.p / (1 - s.agent.p), 3),
        goods_drawn=s.goods_drawn, units_sold=s.units_sold, stock_leftover=s.stock,
        deals_closed=sum(1 for d in deals if d.seller == s.id),
        deals_delivered=sum(1 for d in deals if d.seller == s.id and d.fully_delivered),
        deals_undelivered=sum(1 for d in deals if d.seller == s.id and not d.fully_delivered),
        net_score=sum(1 for d in deals if d.seller == s.id),
        conversations=s.conversations) for s in sellers]

    bsum = []
    for b in sorted(buyers.values(), key=lambda x: (-x.owned, x.id)):
        mine = [d for d in deals if d.buyer == b.id]
        deliv = [d for d in mine if d.fully_delivered]
        bsum.append(BuyerSummary(
            id=b.id, name=b.agent.name, owned=b.owned,
            deals_closed=len(mine), deals_delivered=len(deliv),
            deals_undelivered=len(mine) - len(deliv), rounds_locked=b.rounds_locked))

    deals_made = len(deals)
    products_delivered = len(handoffs)
    from collections import Counter
    v = Counter(d.verdict for d in deals)
    false_total = v["false-late"] + v["false-never"]
    measurements = {
        "deals_made": deals_made,
        "products_delivered": products_delivered,
        "delivered_per_deal": round(products_delivered / (deals_made or 1), 3),
        # promise distribution — all mechanical, re-derivable via rescore.py
        "true": v["true"],
        "false": false_total,
        "false_late": v["false-late"],
        "false_never": v["false-never"],
        "vague": v["vague"],
        "quotes_verified": sum(1 for d in deals if d.promise_quote_verified),
        "goods_drawn_total": sum(s.goods_drawn for s in sellers),
        "stock_leftover_total": sum(s.stock for s in sellers),
    }

    return RunResult(
        scenario=scenario.name, description=scenario.description, seed=seed,
        n_sellers=scenario.n_sellers, n_buyers=scenario.n_buyers,
        n_rounds=scenario.n_rounds, heads_prob=scenario.arrival_probs[0],
        apply_attributor=scenario.apply_attributor, use_lawyer=scenario.use_lawyer,
        contract_mode=scenario.contract_mode,
        load_bearing_assumptions=list(scenario.load_bearing_assumptions),
        rounds=rounds, deals=deals, handoffs=handoffs, sellers=ssum, buyers=bsum,
        seller_winner=seller_winner.id, seller_winner_name=seller_winner.name,
        buyer_champion=champ.id, buyer_champion_name=champ.agent.name,
        measurements=measurements)
