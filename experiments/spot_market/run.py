"""Runner for spot_market.

    python -m experiments.spot_market.run --check-supply                # free, no LLM
    python -m experiments.spot_market.run --scenario baseline --seed 0
    python -m experiments.spot_market.run --sellers 3 --buyers 4 --cycles 3
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

from experiments.spot_market.market import draw_stock, estimate_llm_calls, run_market
from experiments.spot_market.models import RunResult
from experiments.spot_market.scenarios import SCENARIOS, SELLERS, get_scenario

RESULTS_DIR = Path(__file__).parent / "results"


def save(r: RunResult, tag: str = "") -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    mtag = f"_{tag}" if tag else ""
    p = RESULTS_DIR / f"{r.scenario}_s{r.seed}{mtag}_{ts}.json"
    p.write_text(json.dumps(r.model_dump(mode="json"), indent=2))
    return p


def check_supply(s, trials: int = 20000) -> None:
    print(f"\n{'=' * 72}\n{s.name} -- supply check (per CYCLE, not per round)\n{'=' * 72}")
    rng = random.Random(0)
    for (sid, nm, _), p in zip(SELLERS[:s.n_sellers], s.arrival_probs, strict=True):
        draws = [draw_stock(rng, p) for _ in range(trials)]
        rate = sum(draws) / trials
        print(f"  {sid} {nm:22s} p={p:.2f}  empirical hit rate={rate:.3f}")
    print(f"\n  {s.k_cycles} cycles x {s.n_buyers} buyers/cycle = {s.n_rounds} total rounds, "
          f"{s.n_sellers} sellers. No accumulation; each seller redraws every cycle.")


def report(r: RunResult) -> None:
    print(f"\n{'*' * 78}")
    print(f"SELLER WINNER (deals closed): {r.seller_winner_name} ({r.seller_winner})")
    print(f"BUYER CHAMPION (goods owned): {r.buyer_champion_name} ({r.buyer_champion})")
    print("*" * 78)

    print(f"\n{'seller':24s} {'p':>5s} {'appr':>5s} {'closed':>6s} {'deliv':>6s} "
          f"{'failed':>6s} {'vague':>6s}")
    for s in sorted(r.sellers, key=lambda x: -x.deals_closed):
        print(f"{s.name[:22]:24s} {s.arrival_prob:5.2f} {s.times_approached:5d} "
              f"{s.deals_closed:6d} {s.deals_delivered:6d} {s.deals_failed:6d} "
              f"{s.vague_attempts:6d}")

    print(f"\n{'buyer':24s} {'owns':>5s} {'turns':>6s} {'closed':>6s} {'deliv':>6s} "
          f"{'failed':>6s} {'vague':>6s}")
    for b in sorted(r.buyers, key=lambda x: -x.owned):
        print(f"{b.name[:22]:24s} {b.owned:5d} {b.turns_taken:6d} {b.deals_closed:6d} "
              f"{b.deals_delivered:6d} {b.deals_failed:6d} {b.vague_attempts:6d}")

    print("\nMeasurements:")
    for k, v in r.measurements.items():
        print(f"  {k:20s} {v}")


async def main() -> None:
    ap = argparse.ArgumentParser(description="spot_market -- instant-delivery, no forward promises")
    ap.add_argument("--scenario", default="baseline", choices=list(SCENARIOS))
    ap.add_argument("--sellers", type=int, default=None)
    ap.add_argument("--buyers", type=int, default=None)
    ap.add_argument("--cycles", type=int, default=None, help="K: number of full buyer cycles")
    ap.add_argument("--attempts", type=int, default=None,
                    help="max different sellers a buyer may try in ONE turn")
    ap.add_argument("--max-messages", type=int, default=None)
    ap.add_argument("--p", type=float, default=None,
                    help="arrival probability p for ALL sellers (overrides scenario default)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--seller-model", default=None)
    ap.add_argument("--buyer-model", default=None)
    ap.add_argument("--seller-reasoning-effort", default=None,
                    choices=["minimal", "low", "medium", "high"])
    ap.add_argument("--buyer-reasoning-effort", default=None,
                    choices=["minimal", "low", "medium", "high"])
    ap.add_argument("--tag", default="")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--check-supply", action="store_true")
    args = ap.parse_args()

    s = get_scenario(args.scenario)
    over = {}
    if args.sellers is not None:
        over["n_sellers"] = args.sellers
        over["arrival_probs"] = s.arrival_probs[:args.sellers]
    if args.buyers is not None:
        over["n_buyers"] = args.buyers
    if args.cycles is not None:
        over["k_cycles"] = args.cycles
    if args.attempts is not None:
        over["max_attempts_per_turn"] = args.attempts
    if args.max_messages is not None:
        over["max_messages"] = args.max_messages
    if args.p is not None:
        n = over.get("n_sellers", s.n_sellers)
        over["arrival_probs"] = (args.p,) * n
    if over:
        s = replace(s, **over)

    if args.check_supply:
        check_supply(s)
        return

    lo, hi = estimate_llm_calls(s)
    print(f"Scale: {s.n_sellers} sellers, {s.n_buyers} buyers, {s.k_cycles} cycles "
          f"({s.n_rounds} rounds total). {lo}-{hi} LLM calls.")
    print(f"{s.name} -- {s.description} (seed={args.seed})")
    if args.seller_model or args.buyer_model:
        print(f"MODEL OVERRIDE -- seller: {args.seller_model or '(default)'}, "
              f"buyer: {args.buyer_model or '(default)'}")

    result = await run_market(s, seed=args.seed, verbose=not args.quiet,
                              seller_model=args.seller_model, buyer_model=args.buyer_model,
                              seller_reasoning_effort=args.seller_reasoning_effort,
                              buyer_reasoning_effort=args.buyer_reasoning_effort)
    path = save(result, tag=args.tag)
    report(result)
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
