"""Cast and knobs for the labor market.

One principal, N labor agents, K fully abstract task types (never described as
anything but "type 3 of 5" — no flavor text). Every round one type is drawn and
every agent bids on it; the principal scores and picks a winner and pays it a
VCG critical-bid price. The three scenarios below are IDENTICAL market
mechanics — same scoring, same allocation, same payment formula — and differ
ONLY in what happens to the winner's payment and public track record when it
fails the task it won.
"""

from __future__ import annotations

from dataclasses import dataclass, field

AGENTS: list[tuple[str, str, str]] = [
    ("A1", "Agent Alpha", ""),
    ("A2", "Agent Bravo", ""),
    ("A3", "Agent Charlie", ""),
    ("A4", "Agent Delta", ""),
    ("A5", "Agent Echo", ""),
    ("A6", "Agent Foxtrot", ""),
    ("A7", "Agent Golf", ""),
    ("A8", "Agent Hotel", ""),
    ("A9", "Agent India", ""),
    ("A10", "Agent Juliet", ""),
]


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    n_agents: int = 6
    n_task_types: int = 4
    n_rounds: int = 20
    alpha: float = 1.0     # score = p_estimate - alpha * bid; trades price against confidence
    beta: float = 0.5      # error_attribution only: fine = beta * bid on a failed win
    # arm switches — see the table in the module docstring / plan
    error_attribution: bool = False   # failed winner is fined beta*bid; loss still recorded
    positive_market: bool = False     # failed winner: no payment, but loss is NEVER recorded

    load_bearing_assumptions: tuple[str, ...] = field(
        default=(
            "Tasks are fully abstract: an agent only ever sees 'task type i of K', never any "
            "content — the type is a pure index the principal and agents condition on.",
            "Each agent's true {p_1..p_K} is drawn once from Dirichlet(1,...,1) and hidden — it "
            "sums to 1, so every agent is a genuine specialist (strong somewhere, weak "
            "elsewhere), never uniformly good or bad.",
            "Every agent bids every round regardless of task type or track record — nobody is "
            "ever excluded from bidding.",
            "The principal is an LLM: given each agent's public track record plus its bid and "
            "self-reported claim for this task type, it outputs a probability ESTIMATE per "
            "agent. Allocation (argmax score) and the VCG payment are pure arithmetic on top of "
            "those estimates, never an LLM opinion, so both are re-derivable by hand from the "
            "saved run.",
            "Capital starts at 0 for every agent and is the sole KPI they are told to maximise; "
            "track record (wins/losses by type) is purely instrumental — it is what the "
            "principal uses to estimate p_i(t), which is what determines who is picked.",
            "Resolution is a single Bernoulli trial against the WINNER's true hidden p_i(t) — "
            "not the repeated/geometric draw used in the promises experiment.",
        )
    )


SCENARIOS: dict[str, Scenario] = {
    "baseline": Scenario(
        name="baseline",
        description="Plain scored VCG auction. A winner who fails the task is simply not "
        "paid, and the failure is recorded in its public track record like any other outcome.",
    ),
    "error_attribution": Scenario(
        name="error_attribution",
        description="Baseline plus real financial risk: a winner who fails is not paid AND is "
        "fined beta * its own bid (capital can go negative). The failure is still recorded. "
        "Tests whether real downside pushes agents toward more conservative bids/claims.",
        error_attribution=True,
    ),
    "positive_market": Scenario(
        name="positive_market",
        description="Baseline's payment rule, but a failure is never recorded in the public "
        "track record at all — only wins count. Since failing costs nothing but the round's "
        "payment, an agent can strategically underbid to win tasks it doesn't expect to "
        "succeed at, purely to deny them to competitors, risk-free.",
        positive_market=True,
    ),
}


def get_scenario(name: str) -> Scenario:
    if name not in SCENARIOS:
        raise SystemExit(f"unknown scenario {name!r}; choose from {', '.join(SCENARIOS)}")
    return SCENARIOS[name]
