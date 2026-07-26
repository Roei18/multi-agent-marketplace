"""The loop.

One round, in order (see DESIGN.md):

  1. NEGOTIATE  unlocked buyers approach sellers (<= max_attempts tries) and both
                declare DEAL to close. Sellers know only their rate p, not stock.
  2. LOCK       a buyer that closed sits out for the rounds it named.
  3. SUPPLY     each seller draws goods geometrically (own RNG) -- ADDED to stock.
  4. HANDOFF    each seller allocates from its accumulated stock; unsold carries.
  5. SCORE      the buyer(s) owning the most goods take a point.

No seller elimination — all sellers play every round. After the final round a
third-party judge labels every deal true/false/vague.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field

from .agents import (
    BuyerAgent,
    SellerAgent,
    judge_deal,
    market_rules,
    public_board,
    render_plain,
)
from .attributor import Fine, brute_force_attributor, score_sellers
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
    """Whitespace-normalised substring check, so a judge quote must really be in
    the log (case-insensitive; trailing punctuation the model may drop is tolerated
    by matching on the normalised text)."""
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
    stock: int = 0               # accumulating inventory; unsold goods carry over
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
    points: int = 0
    locked_until: int = 0        # may negotiate when round > locked_until
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
    lo = lo_convs * 2 + s.n_sellers * s.n_rounds + lo_convs        # + judge
    hi = hi_convs * (s.max_messages + 1) + s.n_sellers * s.n_rounds + hi_convs
    return lo, hi


# --------------------------------------------------------------------------
# Views
# --------------------------------------------------------------------------


def seller_rows(sellers: list[SellerState]) -> list[str]:
    return [f"  {s.id} {s.name:22s} {s.units_sold} handed over (total)" for s in sellers]


def buyer_rows(buyers: dict[str, BuyerState]) -> list[str]:
    ranked = sorted(buyers.values(), key=lambda b: (-b.owned, b.id))
    return [f"  {b.id} {b.agent.name:22s} owns {b.owned}  ({b.points} pt)" for b in ranked]


def owed_view(deals: list[Deal], sid: str, buyers: dict[str, BuyerState]) -> str:
    mine = [d for d in deals if d.seller == sid and d.outstanding]
    if not mine:
        return "None — you owe nobody."
    return "\n".join(
        f"  {d.buyer} {buyers[d.buyer].agent.name} — declared in round {d.closed_round}"
        for d in sorted(mine, key=lambda d: d.closed_round)
    )


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
    return (f"You own {b.owned} good(s) and have {b.points} point(s). "
            f"Round {round_no} of {s.n_rounds}. You are waiting on goods from: {waiting}.")


# --------------------------------------------------------------------------
# One negotiation
# --------------------------------------------------------------------------


async def negotiate(sst: SellerState, bst: BuyerState, *, scenario, rounds, deals,
                    sellers, sellers_by_id, buyers, round_no, attempt, why,
                    names) -> Negotiation:
    seller_rules = market_rules(scenario, round_no, len(sellers), side="seller")
    buyer_rules = market_rules(scenario, round_no, len(sellers), side="buyer")
    board = public_board(seller_rows(sellers), buyer_rows(buyers))
    conv = Negotiation(round=round_no, attempt=attempt, buyer=bst.id, seller=sst.id,
                       approach_reasoning=why)

    for i in range(scenario.max_messages):
        if i % 2 == 0:
            msg = await sst.agent.turn(
                rules=seller_rules, board=board, owed=owed_view(deals, sst.id, buyers),
                history=seller_history(sst.id, rounds, names),
                buyer_name=bst.agent.name, buyer_id=bst.id, conv=conv, opening=(i == 0),
                max_messages=scenario.max_messages)
            if msg.declare_deal:
                conv.seller_declared = True
        else:
            msg = await bst.agent.turn(
                rules=buyer_rules, board=board,
                progress=progress_view(bst, deals, round_no, scenario),
                history=buyer_history(bst, sellers_by_id),
                seller_name=sst.agent.name, conv=conv, max_messages=scenario.max_messages)
            if msg.declare_deal:
                conv.buyer_declared = True
                conv.buyer_deal_rounds = max(1, int(msg.deal_rounds))
        conv.messages.append(msg)
        if conv.seller_declared and conv.buyer_declared:
            conv.closed = True
            break
        if i >= 1 and not msg.continue_conversation:
            break

    # A declaration is an offer to close; give the other side one turn to answer.
    if not conv.closed and (conv.seller_declared != conv.buyer_declared):
        if conv.buyer_declared:
            msg = await sst.agent.turn(
                rules=seller_rules, board=board, owed=owed_view(deals, sst.id, buyers),
                history=seller_history(sst.id, rounds, names),
                buyer_name=bst.agent.name, buyer_id=bst.id, conv=conv, opening=False,
                max_messages=scenario.max_messages)
            if msg.declare_deal:
                conv.seller_declared = True
        else:
            msg = await bst.agent.turn(
                rules=buyer_rules, board=board,
                progress=progress_view(bst, deals, round_no, scenario),
                history=buyer_history(bst, sellers_by_id),
                seller_name=sst.agent.name, conv=conv, max_messages=scenario.max_messages)
            if msg.declare_deal:
                conv.buyer_declared = True
                conv.buyer_deal_rounds = max(1, int(msg.deal_rounds))
        conv.messages.append(msg)
        conv.closed = conv.seller_declared and conv.buyer_declared
    return conv


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


async def run_market(scenario: Scenario, seed: int, *, verbose: bool = True) -> RunResult:
    # Two independent random processes, each with its own fixed seed, so supply is
    # NOT perturbed by how the negotiation happens to consume randomness. This is
    # what makes baseline and attributor face the SAME per-round supply at a given
    # seed, so any difference between them is the regulator, not luck.
    rng = random.Random(seed)               # market: shopper order, approach fallback
    rng_supply = random.Random(seed)        # supply draws only, in fixed round×seller order
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

        # 1. negotiation -- waves of attempts by unlocked buyers
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
                            open_deals_at_close=open_now,
                            unbacked_at_close=open_now > exp))
                        b.locked_until = round_no + conv.buyer_deal_rounds
                        b.rounds_locked += conv.buyer_deal_rounds
                        b.note(sid, f"round {round_no}: you both declared DEAL; you sit out "
                                    f"{conv.buyer_deal_rounds} round(s).")
                        if verbose:
                            f = "  << UNBACKED" if deals[-1].unbacked_at_close else ""
                            print(f"    DEAL {b.id}~{sid} lock={conv.buyer_deal_rounds} "
                                  f"exp_supply={exp:.2f} open={open_now}{f}")
                    else:
                        b.note(sid, f"round {round_no}: talked, no deal.")
                return out

            for convs in await asyncio.gather(*(serve(sid) for sid in queues)):
                rec.negotiations.extend(convs)

        rec.negotiations.sort(key=lambda c: (c.attempt, c.buyer))
        rec.deals_closed = sum(1 for c in rec.negotiations if c.closed)

        # 3. supply draw -- from the dedicated supply RNG (independent of the
        # negotiation), ADDED to the seller's standing stock
        for s in sellers:
            drawn = draw_goods(rng_supply, s.agent.p)
            s.stock += drawn
            s.goods_drawn += drawn
            rec.goods_drawn[s.id] = drawn
        rec.stock_after_draw = {s.id: s.stock for s in sellers}
        if verbose:
            print(f"  deals closed: {rec.deals_closed}   drew: " +
                  "  ".join(f"{s.id}:+{rec.goods_drawn[s.id]}(={s.stock})" for s in sellers))

        # 4. handoff -- a seller allocates from its accumulated stock; unsold units
        # stay in stock for later rounds (goods are NOT perishable).
        for s in sellers:
            mine = [d for d in deals if d.seller == s.id and d.outstanding]
            picked: list[str] = []
            if mine and s.stock > 0:
                if len(mine) <= s.stock:
                    picked = [d.buyer for d in mine]
                else:
                    ch: HonorChoice = await s.agent.fulfil(
                        rules=market_rules(scenario, round_no, len(sellers), side="seller"),
                        board=public_board(seller_rows(sellers), buyer_rows(buyers)),
                        goods=s.stock,
                        history=seller_history(s.id, rounds + [rec], names),
                        options=owed_view(deals, s.id, buyers), n_deals=len(mine))
                    valid = {d.buyer for d in mine}
                    seen: set[str] = set()
                    for bid in ch.honor:
                        bid = bid.strip().upper()
                        if bid in valid and bid not in seen:
                            seen.add(bid)
                            picked.append(bid)
                        if len(picked) >= s.stock:
                            break
            for bid in picked:
                d = next(d for d in mine if d.buyer == bid and d.outstanding)
                d.honored_round = round_no
                b = buyers[bid]
                b.owned += 1
                s.units_sold += 1
                s.stock -= 1
                h = Handoff(round=round_no, seller=s.id, buyer=bid, deal_id=d.id,
                            waited=round_no - d.closed_round)
                handoffs.append(h)
                rec.handoffs.append(h)
                b.note(s.id, f"round {round_no}: they handed you a unit.")
            rec.stock_carried[s.id] = s.stock          # unsold, carries to next round
        rec.sold_this_round = {s.id: sum(1 for h in rec.handoffs if h.seller == s.id)
                               for s in sellers}

        # 5. score the buyers' round
        top = max((b.owned for b in buyers.values()), default=0)
        winners = [b for b in buyers.values() if b.owned == top and top > 0]
        for b in winners:
            b.points += 1
        rec.point_winners = [b.id for b in winners]
        rec.owned_after = {b.id: b.owned for b in buyers.values()}
        if verbose:
            print(f"  handed over: {len(rec.handoffs)}  carried: {sum(rec.stock_carried.values())}"
                  f"  round point: {', '.join(rec.point_winners) or 'none'}")

        rounds.append(rec)
        # No seller elimination — all sellers play every round.

    await run_judge(deals, rounds, sellers_by_id, names, verbose=verbose)
    return summarise(scenario, seed, sellers, buyers, deals, handoffs, rounds)


async def run_judge(deals, rounds, sellers_by_id, names, *, verbose) -> None:
    """Third party labels every closed deal, once, at game end."""
    conv_by_key = {(n.round, n.buyer, n.seller): n
                   for rec in rounds for n in rec.negotiations if n.closed}

    async def label(d: Deal):
        conv = conv_by_key.get((d.closed_round, d.buyer, d.seller))
        if conv is None:
            return
        if d.honored_round >= 0:
            outcome = f"The goods were handed over in round {d.honored_round}."
        else:
            outcome = "The goods were never handed over by the end of the game."
        transcript = render_plain(conv, sellers_by_id[d.seller].name, names[d.buyer])
        res = await judge_deal(transcript=transcript, outcome=outcome)
        lab = res.label.strip().lower()
        d.judge_label = lab if lab in ("true", "false", "vague") else "vague"
        d.judge_reasoning = res.private_reasoning
        d.judge_reason = res.reason
        d.judge_quotes = list(res.quotes)
        d.judge_quotes_verified = [quote_in_transcript(q, transcript) for q in res.quotes]

    await asyncio.gather(*(label(d) for d in deals))
    if verbose and deals:
        from collections import Counter
        c = Counter(d.judge_label for d in deals)
        print(f"\n  judge: true={c['true']}  false={c['false']}  vague={c['vague']}")


def summarise(scenario, seed, sellers, buyers, deals, handoffs, rounds) -> RunResult:
    champ = max(buyers.values(), key=lambda b: (b.points, b.owned))

    # The attributor voids false commitments only when this condition applies it.
    # The judge still runs in every condition (promise labels are a measurement),
    # but the baseline leaves every deal standing.
    if scenario.apply_attributor:
        fines = brute_force_attributor(deals)
    else:
        fines = [Fine(deal_id=d.id, seller=d.seller, fined=False, reason="no attributor")
                 for d in deals]
    scored = score_sellers(deals, fines)
    fined_ids = {f.deal_id for f in fines if f.fined}
    for d in deals:
        d.fined = d.id in fined_ids

    # No elimination — the seller with the highest net score wins the contest.
    seller_winner = max(sellers, key=lambda s: (scored.get(s.id, {}).get("net", 0), s.id))

    ssum = [SellerSummary(
        id=s.id, name=s.name, arrival_prob=s.agent.p,
        expected_supply_per_round=round(s.agent.p / (1 - s.agent.p), 3),
        goods_drawn=s.goods_drawn, units_sold=s.units_sold, stock_leftover=s.stock,
        deals_closed=sum(1 for d in deals if d.seller == s.id),
        deals_honored=sum(1 for d in deals if d.seller == s.id and d.honored_round >= 0),
        deals_never_honored=sum(1 for d in deals if d.seller == s.id and d.honored_round < 0),
        unbacked_deals=sum(1 for d in deals if d.seller == s.id and d.unbacked_at_close),
        deals_voided=scored.get(s.id, {}).get("voided", 0),
        net_score=scored.get(s.id, {}).get("net", 0),
        conversations=s.conversations) for s in sellers]

    bsum = []
    for b in sorted(buyers.values(), key=lambda x: (-x.points, -x.owned, x.id)):
        mine = [d for d in deals if d.buyer == b.id]
        hon = [d for d in mine if d.honored_round >= 0]
        bsum.append(BuyerSummary(
            id=b.id, name=b.agent.name, owned=b.owned, points=b.points,
            deals_closed=len(mine), deals_honored=len(hon),
            deals_broken=len(mine) - len(hon), rounds_locked=b.rounds_locked))

    honored = [d for d in deals if d.honored_round >= 0]
    unbacked = [d for d in deals if d.unbacked_at_close]
    n = len(deals) or 1
    labels = [d.judge_label for d in deals]
    attribution = {
        "deals_closed": len(deals),
        "deals_honored": len(honored),
        "deals_never_honored": len(deals) - len(honored),
        "share_honored": round(len(honored) / n, 3),
        "unbacked_at_close": len(unbacked),
        "share_unbacked": round(len(unbacked) / n, 3),
        "unbacked_never_honored": sum(1 for d in unbacked if d.honored_round < 0),
        "backed_never_honored": sum(1 for d in deals
                                    if not d.unbacked_at_close and d.honored_round < 0),
        "judge_true": labels.count("true"),
        "judge_false": labels.count("false"),
        "judge_vague": labels.count("vague"),
        "share_vague": round(labels.count("vague") / n, 3),
        "goods_drawn_total": sum(s.goods_drawn for s in sellers),
        "units_handed_over": len(handoffs),
        "stock_leftover_total": sum(s.stock for s in sellers),
    }

    attribution["deals_voided_by_attributor"] = len(fined_ids)

    return RunResult(
        scenario=scenario.name, description=scenario.description, seed=seed,
        n_sellers=scenario.n_sellers, n_buyers=scenario.n_buyers,
        n_rounds=scenario.n_rounds, heads_prob=scenario.arrival_probs[0],
        apply_attributor=scenario.apply_attributor,
        load_bearing_assumptions=list(scenario.load_bearing_assumptions),
        rounds=rounds, deals=deals, handoffs=handoffs, sellers=ssum, buyers=bsum,
        seller_winner=seller_winner.id, seller_winner_name=seller_winner.name,
        buyer_champion=champ.id, buyer_champion_name=champ.agent.name,
        attribution=attribution)
