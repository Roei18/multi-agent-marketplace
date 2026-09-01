"""LaborAgent (bidder) and Principal (LLM-scored allocator) for labor_market.

Both are thin: one combined LLM call each. LaborAgent.turn() reflects on last
round's outcome, revises its persistent strategy note, and bids in one call —
same "reflect-then-act" shape as promises' SellerAgent.update_strategy(),
except here it happens every round rather than at review checkpoints, since
every agent participates every round. Principal.estimate() is the ONE LLM
opinion in the whole loop; everything downstream (allocate, pay) is pure
arithmetic in market.py.
"""

from __future__ import annotations

from experiments.dealrace.llm import call_llm
from experiments.labor_market.models import AgentTurn, PrincipalEstimate

MARKET_RULES = """\
# How this market works
Each round the principal announces ONE task type (an index, nothing else — the task has no \
content to reason about beyond its type). Every labor agent submits, in the same round:
  - a BID: the price you are asking to be paid if you win and succeed.
  - a CLAIMED PROBABILITY: your own honest estimate of your chance of succeeding at THIS \
task type.
The principal (not you) estimates each agent's true success probability for this task type, \
weighing your track record against your bid and claim, and scores every agent as
    score = (principal's probability estimate for you) - alpha * (your bid).
The single highest-scoring agent wins. Critically, the WINNER IS NOT PAID ITS OWN BID: it is \
paid the highest price it could have asked while still beating the runner-up's score — a VCG \
critical-bid price, computed from the runner-up's score, not from what you actually asked. \
This means your bid affects ONLY whether you win, never what you are paid if you do. Payment \
happens only if you win AND then actually succeed at the task.
"""


class LaborAgent:
    def __init__(self, aid: str, name: str, blurb: str, true_p: list[float]):
        self.id, self.name, self.blurb = aid, name, blurb
        self.true_p = true_p             # hidden; never shown in any prompt
        self.model: str | None = None
        self.reasoning_effort: str | int | None = None
        self.strategy: str = ""
        self.capital: float = 0.0
        self.wins: int = 0
        self.successes: int = 0
        self.failures: int = 0
        self.bids_submitted: int = 0
        self.track: dict[int, dict[str, int]] = {}   # task_type -> {"attempts", "successes"}

    def record(self, task_type: int, *, success: bool) -> None:
        row = self.track.setdefault(task_type, {"attempts": 0, "successes": 0})
        row["attempts"] += 1
        if success:
            row["successes"] += 1

    def track_line(self, task_type: int) -> str:
        row = self.track.get(task_type)
        if not row or row["attempts"] == 0:
            return "no completed wins/losses on record yet"
        return f"{row['successes']}/{row['attempts']} succeeded (of recorded outcomes)"

    def track_text(self, n_task_types: int) -> str:
        return "\n".join(f"  type {t}: {self.track_line(t)}" for t in range(n_task_types))

    async def turn(self, *, task_type: int, round_no: int, outcome_disclosure: str,
                   n_task_types: int) -> AgentTurn:
        prompt = f"""\
{MARKET_RULES}

# Who you are
You are {self.name} ({self.id}), one of several labor agents in this market. Your only goal \
is to maximise your accumulated capital (starts at 0) over the whole run.

# Your strategy note (written by you; carries forward until you revise it)
{self.strategy.strip() or "(none yet — this is your first round)"}

# Your public track record (what the principal can see about you)
{self.track_text(n_task_types)}

# Last round
{outcome_disclosure or "(this is round 1 — no prior round to reflect on)"}

# This round
The task type on offer is type {task_type} (of {n_task_types} possible types, indexed 0 to \
{n_task_types - 1}). Decide your bid and claimed probability for THIS type.

Return private_reasoning (never seen by anyone), updated_strategy (your full new note, \
replacing the old one — may be unchanged), bid, and claimed_probability."""
        return await call_llm(prompt, AgentTurn, model=self.model,
                              reasoning_effort=self.reasoning_effort)


class Principal:
    def __init__(self, model: str | None = None):
        self.model = model

    async def estimate(self, *, task_type: int, agents: list[LaborAgent],
                       bids: dict[str, float], claims: dict[str, float]) -> PrincipalEstimate:
        rows = []
        for a in agents:
            rows.append(
                f"- {a.id} ({a.name}): track record for type {task_type} — "
                f"{a.track_line(task_type)}; bid={bids[a.id]:.2f}; "
                f"claimed_probability={claims[a.id]:.0%}"
            )
        prompt = f"""\
# Who you are
You are the principal running this labor market. Each round you pick ONE labor agent to do \
a task, based on their public track record, their bid, and their self-reported claim. You do \
not know any agent's TRUE hidden success probability — only what their history, bid, and \
claim suggest.

# This round's task type
type {task_type}

# Candidates
{chr(10).join(rows)}

For EACH candidate listed above, estimate their true probability of succeeding at THIS task \
type if chosen — weigh their track record on this type most heavily; treat their claim as \
informative but self-interested (an agent that claims high but has a poor record on this type \
should not automatically be believed).

Return private_reasoning and estimates — one entry per candidate, covering every id above."""
        return await call_llm(prompt, PrincipalEstimate, model=self.model)
