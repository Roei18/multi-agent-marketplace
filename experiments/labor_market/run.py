"""Runner for labor_market.

    python -m experiments.labor_market.run --check-supply                 # free, no LLM
    python -m experiments.labor_market.run --scenario baseline --seed 0
    python -m experiments.labor_market.run --scenario error_attribution --agents 3 --task-types 2 --rounds 6
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv()

from experiments.labor_market.market import allocate, dirichlet_draw, estimate_llm_calls, run_market, vcg_payment
from experiments.labor_market.models import RunResult
from experiments.labor_market.scenarios import AGENTS, SCENARIOS, get_scenario

RESULTS_DIR = Path(__file__).parent / "results"


def save(r: RunResult, tag: str = "") -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    mtag = f"_{tag}" if tag else ""
    p = RESULTS_DIR / f"{r.scenario}_s{r.seed}{mtag}_{ts}.json"
    p.write_text(json.dumps(r.model_dump(mode="json"), indent=2))
    return p


def check_supply(s, trials: int = 1) -> None:
    """No LLM: show the hidden Dirichlet draw each agent would get, and hand-check
    allocate()/vcg_payment() on a synthetic 3-agent example."""
    print(f"\n{'=' * 72}\n{s.name} — dry run (no LLM)\n{'=' * 72}")
    rng = random.Random(0)
    for aid, name, _ in AGENTS[:s.n_agents]:
        p = dirichlet_draw(rng, s.n_task_types)
        p_str = ", ".join(f"{x:.2f}" for x in p)
        print(f"  {aid} {name:14s} true p by type: [{p_str}]  (sums to {sum(p):.3f})")

    print("\n  Hand-check: 3 agents, alpha=1.0, scores {A1: 0.8, A2: 0.5, A3: 0.9}")
    scores = {"A1": 0.8, "A2": 0.5, "A3": 0.9}
    winner, s1, s2 = allocate(scores)
    pay = vcg_payment(p_winner=0.95, second_score=s2, alpha=1.0)
    print(f"    winner={winner} (score {s1}), runner-up score={s2}, "
          f"principal estimate for winner=0.95 -> VCG payment={pay:.3f}")
    assert winner == "A3" and abs(pay - 0.15) < 1e-9

    print(f"\n  {s.n_rounds} rounds, {s.n_agents} agents, {s.n_task_types} task types, "
          f"alpha={s.alpha}, beta={s.beta}. error_attribution={s.error_attribution} "
          f"positive_market={s.positive_market}")


def report(r: RunResult) -> None:
    print(f"\n{'*' * 78}")
    print(f"WINNER (final capital): {r.winner_name} ({r.winner})")
    print("*" * 78)

    print(f"\n{'agent':16s} {'capital':>9s} {'wins':>5s} {'succ':>5s} {'fail':>5s} "
          f"{'bids':>5s}  true_p")
    for a in sorted(r.agents, key=lambda x: -x.final_capital):
        p_str = ", ".join(f"{x:.2f}" for x in a.true_p)
        print(f"{a.name[:14]:16s} {a.final_capital:9.2f} {a.wins:5d} {a.successes:5d} "
              f"{a.failures:5d} {a.bids_submitted:5d}  [{p_str}]")

    n_success = sum(1 for rd in r.rounds if rd.success)
    n_fail = sum(1 for rd in r.rounds if rd.success is False)
    total_paid = sum(rd.payment for rd in r.rounds)
    total_fines = sum(rd.fine for rd in r.rounds)
    print(f"\nRounds: {len(r.rounds)}  successes={n_success}  failures={n_fail}  "
          f"total_paid={total_paid:.2f}  total_fines={total_fines:.2f}")
    if r.strategy_log:
        print(f"strategy revisions: {len(r.strategy_log)}")


async def main() -> None:
    ap = argparse.ArgumentParser(description="labor_market — LLM-scored VCG task auction")
    ap.add_argument("--scenario", default="baseline", choices=list(SCENARIOS))
    ap.add_argument("--agents", type=int, default=None)
    ap.add_argument("--task-types", type=int, default=None)
    ap.add_argument("--rounds", type=int, default=None)
    ap.add_argument("--alpha", type=float, default=None)
    ap.add_argument("--beta", type=float, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--agent-model", default=None,
                    help="override the model for all labor agents (probe)")
    ap.add_argument("--agent-reasoning-effort", default=None,
                    choices=["minimal", "low", "medium", "high"])
    ap.add_argument("--principal-model", default=None,
                    help="override the model for the principal (probe)")
    ap.add_argument("--tag", default="", help="label inserted into the saved filename")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--check-supply", action="store_true")
    args = ap.parse_args()

    s = get_scenario(args.scenario)
    over = {}
    if args.agents is not None:
        over["n_agents"] = args.agents
    if args.task_types is not None:
        over["n_task_types"] = args.task_types
    if args.rounds is not None:
        over["n_rounds"] = args.rounds
    if args.alpha is not None:
        over["alpha"] = args.alpha
    if args.beta is not None:
        over["beta"] = args.beta
    if over:
        s = replace(s, **over)

    if args.check_supply:
        check_supply(s)
        return

    lo, hi = estimate_llm_calls(s)
    print(f"Scale: {s.n_agents} agents, {s.n_task_types} task types, {s.n_rounds} rounds. "
          f"~{lo}-{hi} LLM calls.")
    print(f"{s.name} — {s.description} (seed={args.seed})")
    if args.agent_model:
        print(f"AGENT MODEL OVERRIDE — {args.agent_model}")
    if args.principal_model:
        print(f"PRINCIPAL MODEL OVERRIDE — {args.principal_model}")

    result = await run_market(s, seed=args.seed, verbose=not args.quiet,
                              agent_model=args.agent_model,
                              agent_reasoning_effort=args.agent_reasoning_effort,
                              principal_model=args.principal_model)
    path = save(result, tag=args.tag)
    report(result)
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
