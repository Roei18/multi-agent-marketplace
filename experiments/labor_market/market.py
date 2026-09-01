"""The labor market: pure allocation/payment arithmetic, plus the round loop
that drives the LLM calls (agent turns, principal estimate).

The allocation and payment functions below take only plain numbers/dicts and
touch no LLM client — they are the auditable core the plan calls for: given
whatever p_i(t) estimates the principal produced, WHO wins and WHAT they are
paid is re-derivable by hand from the saved run, never an LLM opinion.
"""

from __future__ import annotations

import asyncio
import random

from experiments.labor_market.agents import LaborAgent, Principal
from experiments.labor_market.models import (
    AgentSummary,
    BidRecord,
    RoundRecord,
    RunResult,
    StrategyEvent,
)
from experiments.labor_market.scenarios import AGENTS, Scenario

# --------------------------------------------------------------------------
# Pure functions — no LLM, fully unit-testable
# --------------------------------------------------------------------------


def dirichlet_draw(rng: random.Random, k: int) -> list[float]:
    """Dirichlet(1,...,1): k iid Gamma(1,1) (= Exponential(1)) draws, normalised
    to sum to 1. Uniform over the simplex — no task type is favoured a priori."""
    draws = [rng.gammavariate(1.0, 1.0) for _ in range(k)]
    total = sum(draws)
    return [d / total for d in draws]


def draw_success(rng: random.Random, p: float) -> bool:
    """A single Bernoulli trial against the WINNER's true hidden probability."""
    return rng.random() < p


def allocate(scores: dict[str, float]) -> tuple[str, float, float]:
    """argmax over S_i(t) = p_i(t) - alpha*b_i(t). Returns (winner_id, winner's
    own score, second-highest score) — ties broken by agent id for determinism."""
    if len(scores) < 2:
        raise ValueError("allocate() needs at least 2 candidates to define a VCG price")
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    winner_id, s1 = ranked[0]
    _, s2 = ranked[1]
    return winner_id, s1, s2


def vcg_payment(p_winner: float, second_score: float, alpha: float) -> float:
    """The highest price the winner could have asked while still beating the
    runner-up: b* = (p_winner - S_2) / alpha. Depends only on the winner's own
    (principal-estimated) probability and the second-highest score — never on
    the winner's own bid — which is exactly what makes truthful bidding a
    dominant strategy under this scoring rule."""
    if alpha <= 0:
        raise ValueError("alpha must be positive")
    return (p_winner - second_score) / alpha


# --------------------------------------------------------------------------
# The round loop — wires the pure functions above to the LLM calls in agents.py
# --------------------------------------------------------------------------


def estimate_llm_calls(s: Scenario) -> tuple[int, int]:
    per_round = s.n_agents + 1   # every agent bids, plus one principal call
    return per_round * s.n_rounds, per_round * s.n_rounds


async def run_market(scenario: Scenario, seed: int, *, verbose: bool = True,
                     agent_model: str | None = None,
                     agent_reasoning_effort: str | None = None,
                     principal_model: str | None = None) -> RunResult:
    rng = random.Random(seed)
    roster = AGENTS[: scenario.n_agents]

    agents: dict[str, LaborAgent] = {}
    for aid, name, blurb in roster:
        true_p = dirichlet_draw(rng, scenario.n_task_types)
        a = LaborAgent(aid, name, blurb, true_p)
        if agent_model:
            a.model = agent_model
        if agent_reasoning_effort:
            a.reasoning_effort = agent_reasoning_effort
        agents[aid] = a

    principal = Principal(model=principal_model)

    # per-agent last-round outcome, shown at the top of the NEXT round's prompt
    last_outcome: dict[str, str] = {aid: "" for aid in agents}

    rounds: list[RoundRecord] = []
    strategy_log: list[StrategyEvent] = []

    for round_no in range(1, scenario.n_rounds + 1):
        task_type = rng.randrange(scenario.n_task_types)
        if verbose:
            print(f"\n{'=' * 78}\nROUND {round_no}  task_type={task_type}\n{'=' * 78}")

        turns = await asyncio.gather(*(
            a.turn(task_type=task_type, round_no=round_no,
                  outcome_disclosure=last_outcome[aid], n_task_types=scenario.n_task_types)
            for aid, a in agents.items()
        ))

        for (aid, a), t in zip(agents.items(), turns, strict=True):
            if t.updated_strategy.strip() != a.strategy.strip():
                strategy_log.append(StrategyEvent(
                    round=round_no, agent=aid, prior_strategy=a.strategy,
                    private_reasoning=t.private_reasoning, updated_strategy=t.updated_strategy))
            a.strategy = t.updated_strategy

        bids = {aid: t.bid for aid, t in zip(agents.keys(), turns)}
        claims = {aid: t.claimed_probability for aid, t in zip(agents.keys(), turns)}
        for a in agents.values():
            a.bids_submitted += 1

        pe = await principal.estimate(task_type=task_type, agents=list(agents.values()),
                                      bids=bids, claims=claims)
        estimates = {e.agent_id: e.p_estimate for e in pe.estimates}
        missing = set(agents) - set(estimates)
        if missing:
            raise RuntimeError(f"principal omitted estimates for {missing}")

        scores = {aid: estimates[aid] - scenario.alpha * bids[aid] for aid in agents}
        winner_id, s1, s2 = allocate(scores)
        payment = max(0.0, vcg_payment(estimates[winner_id], s2, scenario.alpha))

        success = draw_success(rng, agents[winner_id].true_p[task_type])
        fine = 0.0
        track_updated = True
        winner = agents[winner_id]
        if success:
            winner.capital += payment
            winner.wins += 1
            winner.successes += 1
            winner.record(task_type, success=True)
        else:
            if scenario.positive_market:
                track_updated = False   # loss never touches the public track record
            else:
                winner.failures += 1
                winner.record(task_type, success=False)
            if scenario.error_attribution:
                fine = scenario.beta * bids[winner_id]
                winner.capital -= fine

        rec = RoundRecord(
            round=round_no, task_type=task_type, principal_reasoning=pe.private_reasoning,
            bids=[BidRecord(agent=aid, private_reasoning=t.private_reasoning, bid=bids[aid],
                            claimed_probability=claims[aid], p_estimate=estimates[aid],
                            score=scores[aid], won=(aid == winner_id))
                  for aid, t in zip(agents.keys(), turns)],
            winner=winner_id, winner_score=s1, second_score=s2, payment=payment if success else 0.0,
            success=success, fine=fine, track_updated=track_updated,
        )
        rounds.append(rec)

        # outcome disclosure for every agent's NEXT round
        for aid, t in zip(agents.keys(), turns):
            won = aid == winner_id
            line = (f"Last round (type {task_type}): you bid {bids[aid]:.2f}, claimed "
                    f"{claims[aid]:.0%}, the principal estimated you at {estimates[aid]:.0%}, "
                    f"your score was {scores[aid]:.2f}. ")
            if won:
                outcome = "You WON." + (f" You succeeded and were paid {payment:.2f}."
                                        if success else " You FAILED the task and were not paid.")
                if fine:
                    outcome += f" You were also fined {fine:.2f}."
                if scenario.positive_market and not success:
                    outcome += " This failure was NOT recorded in your public track record."
            else:
                outcome = f"You LOST. The winning score was {s1:.2f}."
            last_outcome[aid] = line + outcome

        if verbose:
            print(f"  winner={winner_id} score={s1:.2f} (2nd={s2:.2f}) "
                  f"success={success} payment={payment if success else 0.0:.2f} fine={fine:.2f}")

    agents_summary = [
        AgentSummary(id=aid, name=a.name, final_capital=a.capital, wins=a.wins,
                    successes=a.successes, failures=a.failures, bids_submitted=a.bids_submitted,
                    true_p=a.true_p, final_strategy=a.strategy)
        for aid, a in agents.items()
    ]
    winner_summary = max(agents_summary, key=lambda x: x.final_capital)

    return RunResult(
        scenario=scenario.name, description=scenario.description, seed=seed,
        n_agents=scenario.n_agents, n_task_types=scenario.n_task_types,
        n_rounds=scenario.n_rounds, alpha=scenario.alpha, beta=scenario.beta,
        error_attribution=scenario.error_attribution, positive_market=scenario.positive_market,
        load_bearing_assumptions=list(scenario.load_bearing_assumptions),
        rounds=rounds, agents=agents_summary, strategy_log=strategy_log,
        winner=winner_summary.id, winner_name=winner_summary.name,
    )
