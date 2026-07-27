"""Re-measure a saved run with the LLM vagueness judge — no market re-run.

The market outcomes (who dealt with whom, what was said, what was delivered) are
fixed in the saved file; only the PROMISE LABELS depend on the judge. So we replay
the judge over the saved transcripts, recompute the mechanical verdict and all
ratio metrics, and write a new results file. Cheap: one judge call per deal.

    python -m experiments.promises.remeasure experiments/promises/results/baseline_s0_*.json
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv()

from experiments.promises.agents import judge_vagueness, render_plain
from experiments.promises.attributor import score_sellers, void_false_promises
from experiments.promises.market import quote_in_transcript
from experiments.promises.models import RunResult
from experiments.promises.scoring import build_measurements, score_deals

RESULTS_DIR = Path(__file__).parent / "results"


async def remeasure(r: RunResult) -> RunResult:
    snames = {s.id: s.name for s in r.sellers}
    bnames = {b.id: b.name for b in r.buyers}
    conv_by_key = {(n.round, n.buyer, n.seller): n
                   for rec in r.rounds for n in rec.negotiations if n.closed}

    async def one(d):
        if r.contract_mode:                      # contract arm: promise is the struct
            d.promised_round = d.by_round
            d.promised_quantity = d.quantity
            d.promise_quote = f"CONTRACT: {d.quantity} unit(s) by round {d.by_round}"
            d.promise_quote_verified = True
            return
        conv = conv_by_key.get((d.closed_round, d.buyer, d.seller))
        if conv is None:
            return
        transcript = render_plain(conv, snames[d.seller], bnames[d.buyer])
        j = await judge_vagueness(transcript=transcript, closed_round=d.closed_round,
                                  n_rounds=r.n_rounds)
        pr = None if j.vague else j.promised_round
        if pr is not None and pr < 1:
            pr = None
        d.promised_round = pr
        d.promised_quantity = j.promised_quantity
        d.promise_quote = j.quote
        d.promise_quote_verified = quote_in_transcript(j.quote, transcript)
        d.extract_reasoning = j.private_reasoning

    await asyncio.gather(*(one(d) for d in r.deals))
    score_deals(r.deals)

    if r.apply_attributor:
        void_false_promises(r.deals)
    scored = score_sellers(r.deals)
    for s in r.sellers:
        s.deals_voided = scored.get(s.id, {}).get("voided", 0)
        s.net_score = scored.get(s.id, {}).get("net", 0)

    lawyer_blocked = sum(n.lawyer_blocked_count for rec in r.rounds for n in rec.negotiations)
    r.measurements = build_measurements(
        r.deals, products_delivered=len(r.handoffs),
        goods_drawn_total=sum(s.goods_drawn for s in r.sellers),
        stock_leftover_total=sum(s.stock_leftover for s in r.sellers),
        lawyer_blocked=lawyer_blocked)
    return r


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m experiments.promises.remeasure <run.json>")
    src = Path(sys.argv[1])
    r = RunResult.model_validate(json.loads(src.read_text()))
    r = asyncio.run(remeasure(r))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RESULTS_DIR / f"{r.scenario}_s{r.seed}_{ts}_judged.json"
    out.write_text(json.dumps(r.model_dump(mode="json"), indent=2))
    m = r.measurements
    print(f"{r.scenario}: vague_rate={m['vague_rate']}  true_rate={m['true_rate']}  "
          f"false_rate={m['false_rate']}  (deals {m['deals_made']})")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
