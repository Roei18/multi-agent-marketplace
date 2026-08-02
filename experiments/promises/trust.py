"""Offline buyer-trust scorer (LLM-assisted, post-hoc — no market re-run).

For each CLOSED conversation we rebuild the buyer's end-of-conversation view (the
market rules it sees + the transcript from its side) and ask the buyer-agent, in the
run's own model, how much it trusts the seller to deliver — on 0-100. The scorer is
BLIND to whether the goods actually arrived (like the vagueness judge), so it captures
the buyer's in-context trust at the moment of the deal.

Scores are cached to results/_trust/<run>.json so we never pay for them twice, and
studies.py folds mean-trust + trust-vs-delivery calibration into the LLM-assisted tier.

    python -m experiments.promises.trust <run.json> [<run.json> ...]
    python -m experiments.promises.trust --study p04-scarce      # all 4 arms of a study
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()  # resolve LLM_PROVIDER/MODEL from .env, as run.py does

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.promises.agents import market_rules, render
from experiments.promises.instrument import call_llm
from experiments.promises.models import RunResult
from experiments.promises.scenarios import SELLERS, get_scenario

RESULTS_DIR = Path(__file__).parent / "results"
TRUST_DIR = RESULTS_DIR / "_trust"
SELLER_NAME = {sid: nm for sid, nm, _ in SELLERS}
CONCURRENCY = 4  # gentle on the shared rate limit; the client also caps per-account


class TrustScore(BaseModel):
    reason: str = Field(description="One short sentence: why you do or don't trust them.")
    trust: int = Field(description="0-100. 0 = they will not deliver as discussed; "
                       "100 = complete confidence they deliver the good(s) by when they said.")


def _prompt(run: RunResult, scen, conv, buyer_name: str, seller_name: str) -> str:
    rules = market_rules(scen, conv.round, run.n_sellers, side="buyer")
    return f"""\
You are {buyer_name}, a buyer in this marketplace. You have just finished a private
conversation with the seller {seller_name}. These are the rules you operate under:

{rules}

# Your conversation with {seller_name}
{render(conv, conv.buyer, seller_name)}

# Question
Based ONLY on this conversation — you do NOT yet know whether the goods actually
arrived — how much do you trust {seller_name} to deliver the good(s) you discussed,
by the time they indicated?

Return `trust` as an integer 0-100 (0 = they will not deliver as discussed, 100 =
complete confidence) and one short sentence of `reason`."""


async def score_run(path: Path, *, refresh: bool = False) -> dict:
    run = RunResult.model_validate(json.loads(path.read_text()))
    scen = replace(get_scenario(run.scenario), n_sellers=run.n_sellers,
                   n_buyers=run.n_buyers, n_rounds=run.n_rounds)
    names = {b.id: b.name for b in run.buyers}
    conv_by_key = {(n.round, n.buyer, n.seller): n
                   for rec in run.rounds for n in rec.negotiations if n.closed}

    TRUST_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = TRUST_DIR / f"{path.stem}.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() and not refresh else {}

    todo = [d for d in run.deals
            if str(d.id) not in cache and (d.closed_round, d.buyer, d.seller) in conv_by_key]
    print(f"{path.name}: {len(run.deals)} deals, {len(todo)} to score "
          f"({len(cache)} cached)", flush=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    done = [0]
    start = time.time()

    async def one(d):
        conv = conv_by_key[(d.closed_round, d.buyer, d.seller)]
        prompt = _prompt(run, scen, conv, names.get(d.buyer, d.buyer),
                         SELLER_NAME.get(d.seller, d.seller))
        async with sem:
            r: TrustScore = await call_llm(prompt, TrustScore)
        cache[str(d.id)] = {"trust": max(0, min(100, r.trust)), "reason": r.reason}
        done[0] += 1
        if done[0] % 10 == 0 or done[0] == len(todo):
            print(f"  {path.stem}: {done[0]}/{len(todo)}  "
                  f"({round(time.time()-start)}s)", flush=True)
            cache_path.write_text(json.dumps(cache, indent=2))  # checkpoint

    if todo:
        await asyncio.gather(*(one(d) for d in todo))
    cache_path.write_text(json.dumps(cache, indent=2))
    return cache


def aggregate(path: Path) -> dict | None:
    """Mean trust + calibration (trust for deals that DID vs did NOT deliver)."""
    cache_path = TRUST_DIR / f"{path.stem}.json"
    if not cache_path.exists():
        return None
    cache = json.loads(cache_path.read_text())
    run = RunResult.model_validate(json.loads(path.read_text()))
    scored = [(d, cache[str(d.id)]["trust"]) for d in run.deals if str(d.id) in cache]
    if not scored:
        return None
    delivered = [t for d, t in scored if d.delivered_round >= 0]
    missed = [t for d, t in scored if d.delivered_round < 0]
    mean = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    return {"n": len(scored), "mean_trust": mean([t for _, t in scored]),
            "trust_if_delivered": mean(delivered), "n_delivered": len(delivered),
            "trust_if_missed": mean(missed), "n_missed": len(missed)}


async def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit("usage: trust.py <run.json> ...  |  --study <slug>")
    if args[0] == "--study":
        from experiments.promises.studies import STUDIES, _select, ARMS
        s = STUDIES[args[1]]
        paths = [_select(a, s["seeds"][0], s["p"]) for a in ARMS]
        if any(p is None for p in paths):
            raise SystemExit(f"missing runs for study {args[1]}")
    else:
        paths = [Path(a) for a in args]
    for p in paths:
        await score_run(p)
        print(f"  -> {aggregate(p)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
