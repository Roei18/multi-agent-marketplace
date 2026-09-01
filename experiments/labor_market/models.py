"""Records for labor_market.

The only LLM opinion in the whole loop is the principal's probability ESTIMATE
per agent. Everything downstream of that estimate — who wins, what they're
paid, whether a fine applies — is pure arithmetic over ground-truth numbers
(the winner's hidden true p, the round's coin flip), exactly like promises'
verdict is arithmetic over the delivery log.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# LLM outputs
# --------------------------------------------------------------------------


class AgentTurn(BaseModel):
    private_reasoning: str = Field(
        description="Your hidden thinking about this round's task, your track record, and "
        "last round's outcome (if any). Nobody else ever sees this."
    )
    updated_strategy: str = Field(
        default="",
        description="Your new strategy note, replacing the old one in full — this is what you "
        "will see on every future round. Keep it concrete and actionable. Carry over anything "
        "from your old note still worth keeping; empty string clears it.",
    )
    bid: float = Field(
        description="The price you are asking to be paid if you win this task. Lower asking "
        "prices score better, all else equal — but you are only paid if you win AND succeed."
    )
    claimed_probability: float = Field(
        ge=0.0, le=1.0,
        description="Your own self-reported estimate of your chance of succeeding at THIS "
        "task type, from 0 to 1. This is a claim, not a verified number — the principal may "
        "weigh your track record over it.",
    )


class AgentEstimate(BaseModel):
    agent_id: str = Field(description="The id of the agent this estimate is for, e.g. A3.")
    p_estimate: float = Field(
        ge=0.0, le=1.0,
        description="Your estimate of this agent's true probability of succeeding at this "
        "round's task type, from 0 (certain failure) to 1 (certain success).",
    )


class PrincipalEstimate(BaseModel):
    private_reasoning: str = Field(
        description="How you weighed each agent's track record against its bid and claim. "
        "Note any agent whose claim looks inflated or overly conservative relative to its "
        "track record."
    )
    estimates: list[AgentEstimate] = Field(
        description="Exactly one estimate per candidate agent, covering every agent id you "
        "were given."
    )


# --------------------------------------------------------------------------
# Durable record
# --------------------------------------------------------------------------


class BidRecord(BaseModel):
    """One agent's full participation in one round: what it did, what the
    principal thought of it, and what it scored — regardless of whether it won."""

    agent: str
    private_reasoning: str
    bid: float
    claimed_probability: float
    p_estimate: float = 0.0
    score: float = 0.0
    won: bool = False


class RoundRecord(BaseModel):
    round: int
    task_type: int
    principal_reasoning: str = ""
    bids: list[BidRecord] = Field(default_factory=list)
    winner: str = ""
    winner_score: float = 0.0
    second_score: float = 0.0
    payment: float = 0.0
    success: bool | None = None       # None only if there was no valid winner (shouldn't happen)
    fine: float = 0.0                 # error_attribution only, else 0.0
    track_updated: bool = False       # False for positive_market on a failed win


class AgentSummary(BaseModel):
    id: str
    name: str
    final_capital: float
    wins: int = 0
    successes: int = 0
    failures: int = 0                 # only counted when the scenario actually records losses
    bids_submitted: int = 0
    true_p: list[float] = Field(default_factory=list)   # ground truth, revealed post-hoc
    final_strategy: str = ""


class StrategyEvent(BaseModel):
    """One entry in an agent's strategy history — the full trace of every
    revision, not just the final note, so the evolution is inspectable."""

    round: int
    agent: str
    prior_strategy: str
    private_reasoning: str
    updated_strategy: str


class RunResult(BaseModel):
    scenario: str
    description: str
    seed: int
    n_agents: int
    n_task_types: int
    n_rounds: int
    alpha: float
    beta: float
    error_attribution: bool = False
    positive_market: bool = False
    protocol: str = ("one task type drawn per round; every agent bids; LLM principal "
                     "estimates p_i(t) per agent from track record+bid+claim; deterministic "
                     "argmax allocation and VCG critical-bid payment on top")
    load_bearing_assumptions: list[str] = Field(default_factory=list)
    rounds: list[RoundRecord] = Field(default_factory=list)
    agents: list[AgentSummary] = Field(default_factory=list)
    strategy_log: list[StrategyEvent] = Field(default_factory=list)
    winner: str = ""
    winner_name: str = ""
    measurements: dict[str, float] = Field(default_factory=dict)
