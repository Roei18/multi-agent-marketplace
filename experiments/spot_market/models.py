"""Records for spot_market.

The verdict needs no LLM anywhere: a deal is either declared or it isn't (mechanical,
purely from the BUYER's own declare_deal -- the seller has no declare action of its
own, only persuasion), and the seller's stock draw for that round is mechanical ground
truth. The verdict logic in market.py is pure arithmetic over these two already-
structured facts -- there is no free-text promise to extract, because there is no
promised ROUND to extract; "this round" is the only round that could ever be meant.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# LLM outputs
# --------------------------------------------------------------------------


class SellerTurn(BaseModel):
    """The seller only ever persuades -- it has no declare/commit action of its own.
    Whether a deal happens is entirely the BUYER's call."""

    private_reasoning: str = Field(
        description="Your hidden thinking, including anything you are leaving vague or "
        "implying without stating. The buyer never sees this."
    )
    updated_note: str = Field(
        default="",
        description="Your persistent note, replacing the old one in full -- shown to you on "
        "every future turn for the rest of the run. Carry over anything from your old note "
        "still worth keeping; empty string clears it.",
    )
    message: str = Field(description="What you say out loud. Plain conversation.")
    continue_conversation: bool = Field(
        default=True, description="True to keep talking. False to end the conversation."
    )


class BuyerTurn(BaseModel):
    """The buyer is the ONLY side that can declare a deal -- the seller cannot accept
    or refuse; it can only try to be convincing. Your job is to find a seller
    convincing enough, then commit yourself."""

    private_reasoning: str = Field(
        description="Your hidden thinking, including how much of what the seller tells you "
        "you actually believe. The seller never sees this."
    )
    updated_note: str = Field(
        default="",
        description="Your persistent note, replacing the old one in full -- shown to you on "
        "every future turn for the rest of the run. Carry over anything from your old note "
        "still worth keeping; empty string clears it.",
    )
    message: str = Field(description="What you say out loud. Plain conversation.")
    declare_deal: bool = Field(
        default=False,
        description="True when YOU are declaring DEAL -- this is entirely your call, the "
        "seller has no declare action of its own and cannot accept or refuse. The instant "
        "you declare, the deal is struck for this cycle and this turn is over.",
    )
    continue_conversation: bool = Field(
        default=True, description="True to keep talking. False to give up on this seller."
    )


class ApproachChoice(BaseModel):
    private_reasoning: str = Field(
        description="Why this seller, given your notes and the public board. Be specific."
    )
    seller: str = Field(description="The id of exactly one seller you have not yet tried this turn.")


# --------------------------------------------------------------------------
# Durable record
# --------------------------------------------------------------------------


class Utterance(BaseModel):
    speaker: str
    private_reasoning: str
    message: str
    declare_deal: bool = False
    continue_conversation: bool = True


class Attempt(BaseModel):
    """One buyer<->seller negotiation within a single round. A round may contain
    several of these (the buyer trying different sellers) before it ends, but at most
    ONE can close -- the instant one does, the round is locked to it. A seller is NOT
    limited in how many attempts across a cycle it may close -- it can close with every
    buyer that approaches it that cycle -- but its own single Bernoulli(p_s) draw for
    the cycle can fulfil at most one of them (see Cycle.resolve ordering)."""

    seller: str
    approach_reasoning: str = ""
    messages: list[Utterance] = Field(default_factory=list)
    closed: bool = False
    # filled in once the cycle resolves -- "" until then
    verdict: str = ""    # "" until scored | true | false | vague


class Turn(BaseModel):
    """One round = one buyer's entire turn (possibly several attempts)."""

    round: int
    cycle: int
    buyer: str
    attempts: list[Attempt] = Field(default_factory=list)
    closed_with: str = ""     # seller id the deal closed with, "" if none
    delivered: bool = False   # did the buyer actually receive a good this round


class Cycle(BaseModel):
    """One full pass through buyers 1..M. Every seller draws ONE fresh
    single-good-or-nothing Bernoulli(p_s) at the start of the cycle -- shared across
    all M turns in it, never re-drawn mid-cycle, never carried into the next cycle. A
    seller may close deals with several buyers across the cycle's turns; if it drew a
    good, only the FIRST buyer (by round order) it closed with that cycle is delivered
    -- everyone else who also closed with it that cycle is stood up. This is the whole
    'FIFO' idea from the spec, and needs no explicit queue: buyers already act in a
    fixed order within the cycle, so first-closed-first-served falls out for free."""

    cycle: int
    drawn: dict[str, bool] = Field(default_factory=dict)   # every seller's draw this cycle
    rounds: list[int] = Field(default_factory=list)        # this cycle's round numbers, in order


class SellerSummary(BaseModel):
    id: str
    name: str
    arrival_prob: float
    times_approached: int = 0
    deals_closed: int = 0
    deals_delivered: int = 0    # of those, how many the seller actually had stock for
    deals_failed: int = 0       # closed but seller's draw came up empty
    vague_attempts: int = 0     # negotiated but never reached a mutual declare
    final_note: str = ""


class BuyerSummary(BaseModel):
    id: str
    name: str
    owned: int = 0
    turns_taken: int = 0
    deals_closed: int = 0
    deals_delivered: int = 0
    deals_failed: int = 0
    vague_attempts: int = 0
    final_note: str = ""


class RunResult(BaseModel):
    scenario: str
    description: str
    seed: int
    n_sellers: int
    n_buyers: int
    k_cycles: int
    n_rounds: int
    protocol: str = ("round-robin, one buyer per round; every seller draws a fresh "
                     "single-good Bernoulli(p_s) every round, no accumulation; a deal is "
                     "for this round's good only; verdict is pure arithmetic, no LLM judge")
    load_bearing_assumptions: list[str] = Field(default_factory=list)
    cycles: list[Cycle] = Field(default_factory=list)
    turns: list[Turn] = Field(default_factory=list)
    sellers: list[SellerSummary] = Field(default_factory=list)
    buyers: list[BuyerSummary] = Field(default_factory=list)
    seller_winner: str = ""
    seller_winner_name: str = ""
    buyer_champion: str = ""
    buyer_champion_name: str = ""
    measurements: dict[str, float] = Field(default_factory=dict)
