"""Runner for promises.

    python -m experiments.promises.run --check-supply                    # free, no LLM
    python -m experiments.promises.run --scenario baseline --seed 0
    python -m experiments.promises.run --sellers 3 --buyers 4 --rounds 3 --max-messages 6
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv()

from experiments.promises.market import draw_goods, estimate_llm_calls, run_market
from experiments.promises.models import RunResult
from experiments.promises.scenarios import SCENARIOS, SELLERS, get_scenario
from experiments.promises.scoring import audit_table

RESULTS_DIR = Path(__file__).parent / "results"


def save(r: RunResult, tag: str = "") -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # tag the supply parameter when it is not the 0.6 default, so studies at a
    # different p never collide with (or contaminate) the standard-supply runs.
    ptag = "" if abs(r.heads_prob - 0.6) < 1e-9 else f"_p{round(r.heads_prob * 100):02d}"
    mtag = f"_{tag}" if tag else ""     # optional label (e.g. a model name for probes)
    p = RESULTS_DIR / f"{r.scenario}_s{r.seed}{mtag}{ptag}_{ts}.json"
    p.write_text(json.dumps(r.model_dump(mode="json"), indent=2))
    return p


def check_supply(s, trials: int = 20000) -> None:
    print(f"\n{'=' * 72}\n{s.name} — supply check\n{'=' * 72}")
    rng = random.Random(0)
    for (sid, nm, _), p in zip(SELLERS[:s.n_sellers], s.arrival_probs, strict=True):
        draws = [draw_goods(rng, p) for _ in range(trials)]
        print(f"  {sid} {nm:22s} p={p:.2f}  mean {statistics.mean(draws):.2f}  "
              f"P(0)={draws.count(0)/trials:.0%}  max {max(draws)}")
    print(f"\n  {s.n_rounds} rounds, {s.n_sellers} sellers, {s.n_buyers} buyers. "
          f"No elimination; unsold goods accumulate.")


def report(r: RunResult) -> None:
    print(f"\n{'*' * 78}")
    scored = "net deals" if r.apply_attributor else "deals closed"
    print(f"SELLER WINNER ({scored}): {r.seller_winner_name} ({r.seller_winner})")
    print(f"BUYER CHAMPION (goods owned):  {r.buyer_champion_name} ({r.buyer_champion})")
    print("*" * 78)

    print(f"\n{'seller':24s} {'p':>5s} {'drew':>5s} {'sold':>5s} {'left':>5s} "
          f"{'deals':>6s} {'deliv':>6s} {'VOID':>5s} {'NET':>4s}")
    for s in sorted(r.sellers, key=lambda x: -x.net_score):
        print(f"{s.name[:22]:24s} {s.arrival_prob:5.2f} {s.goods_drawn:5d} {s.units_sold:5d} "
              f"{s.stock_leftover:5d} {s.deals_closed:6d} {s.deals_delivered:6d} "
              f"{s.deals_voided:5d} {s.net_score:4d}")

    print(f"\n{'buyer':24s} {'owns':>5s} {'deals':>6s} {'deliv':>6s} {'locked':>7s}")
    for b in r.buyers:
        print(f"{b.name[:22]:24s} {b.owned:5d} {b.deals_closed:6d} "
              f"{b.deals_delivered:6d} {b.rounds_locked:7d}")

    print("\nMeasurements:")
    for k, v in r.measurements.items():
        print(f"  {k:28s} {v}")


def print_audit(r: RunResult) -> None:
    print(f"\n{'=' * 78}\nAUDIT — quote → parsed promise → delivery → verdict (per deal)\n{'=' * 78}")
    print(audit_table(r.deals))
    print("\nEvery row is re-derivable by hand; `python -m experiments.promises.rescore "
          "<file>` proves it with no LLM.")


async def main() -> None:
    ap = argparse.ArgumentParser(description="promises — declare-DEAL market, sound verdict")
    ap.add_argument("--scenario", default="baseline", choices=list(SCENARIOS))
    ap.add_argument("--sellers", type=int, default=None)
    ap.add_argument("--buyers", type=int, default=None)
    ap.add_argument("--rounds", type=int, default=None)
    ap.add_argument("--max-messages", type=int, default=None)
    ap.add_argument("--attempts", type=int, default=None)
    ap.add_argument("--p", type=float, default=None,
                    help="arrival probability p for the geometric supply (overrides the "
                    "scenario default of 0.6); lower p = scarcer goods")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--buyer-model", default=None,
                    help="override the model for BUYER agents only (probe, e.g. a stronger model)")
    ap.add_argument("--seller-model", default=None,
                    help="override the model for SELLER agents only (probe)")
    ap.add_argument("--strong-seller", default=None,
                    help="id of the ONE seller to single out with --strong-seller-model "
                    "(default: the first seller in the run) — everyone else stays on the "
                    "default model, or --seller-model if that is also given")
    ap.add_argument("--strong-seller-model", default=None,
                    help="model for the single seller named by --strong-seller (e.g. "
                    "openai/gpt-4o), to compare one stronger agent against otherwise-"
                    "identical competitors")
    ap.add_argument("--tag", default="",
                    help="label inserted into the saved filename (e.g. a model name)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--check-supply", action="store_true")
    ap.add_argument("--audit", action="store_true",
                    help="after the run, print the per-deal quote→promise→delivery→verdict table")
    args = ap.parse_args()

    s = get_scenario(args.scenario)
    over = {}
    if args.sellers is not None:
        over["n_sellers"] = args.sellers
        over["arrival_probs"] = s.arrival_probs[:args.sellers]
    if args.buyers is not None:
        over["n_buyers"] = args.buyers
    if args.rounds is not None:
        over["n_rounds"] = args.rounds
    if args.max_messages is not None:
        over["max_messages"] = args.max_messages
    if args.attempts is not None:
        over["max_attempts_per_round"] = args.attempts
    if args.p is not None:
        n = over.get("n_sellers", s.n_sellers)
        over["arrival_probs"] = (args.p,) * n
    if over:
        s = replace(s, **over)

    if args.check_supply:
        check_supply(s)
        return

    lo, hi = estimate_llm_calls(s)
    print(f"Scale: {s.n_sellers} sellers, {s.n_buyers} buyers, {s.n_rounds} rounds. "
          f"{lo}-{hi} LLM calls.")
    print(f"{s.name} — {s.description} (seed={args.seed})")

    if args.buyer_model or args.seller_model:
        print(f"MODEL OVERRIDE — buyer: {args.buyer_model or '(default)'}, "
              f"seller: {args.seller_model or '(default)'}")
    if args.strong_seller_model:
        print(f"STRONG SELLER — {args.strong_seller or '(first seller)'} runs "
              f"{args.strong_seller_model}, everyone else on the default")
    result = await run_market(s, seed=args.seed, verbose=not args.quiet,
                              buyer_model=args.buyer_model, seller_model=args.seller_model,
                              strong_seller=args.strong_seller,
                              strong_seller_model=args.strong_seller_model)
    path = save(result, tag=args.tag)
    report(result)
    if args.audit:
        print_audit(result)
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    asyncio.run(main())
