"""The trust anchor: recompute every verdict from a saved run with ZERO model calls
and assert it matches what was stored. If this passes, the reported verdicts are
exactly a deterministic function of (extracted promise, delivery log) — nothing an
LLM decided at report time.

    python -m experiments.promises.rescore experiments/promises/results/baseline_s0_*.json

Exits non-zero on any mismatch. Also prints the per-deal audit table so a human can
hand-check any row.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.promises.models import Deal
from experiments.promises.scoring import audit_table, score_promise


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m experiments.promises.rescore <run.json>")
    data = json.loads(Path(sys.argv[1]).read_text())
    deals = [Deal.model_validate(d) for d in data["deals"]]

    mismatches = []
    for d in deals:
        recomputed = score_promise(d.promised_round, d.delivered_round)
        if recomputed != d.verdict:
            mismatches.append((d.id, d.verdict, recomputed))

    print(audit_table(deals))
    print(f"\n{len(deals)} deals re-scored with no LLM.")
    if mismatches:
        print(f"MISMATCH on {len(mismatches)} deal(s): "
              + ", ".join(f"#{i} stored={s!r} recomputed={r!r}" for i, s, r in mismatches))
        raise SystemExit(1)
    print("DETERMINISM OK — every stored verdict reproduced exactly from the delivery log.")


if __name__ == "__main__":
    main()
