"""Show where every promises run stands — live progress under --quiet.

Reads the heartbeats written by instrument.heartbeat (results/_progress/*.json) and
prints one line per run: which phase/round, deals so far, LLM calls, average call
latency, how many calls were slow (>10s ≈ throttled), elapsed, and how stale the
heartbeat is (a run whose heartbeat stopped updating is stuck or finished).

    python -m experiments.promises.status          # once
    watch -n5 python -m experiments.promises.status  # live
"""

from __future__ import annotations

import json
import time
from pathlib import Path

PROGRESS_DIR = Path(__file__).parent / "results" / "_progress"


def _fmt_age(sec: float) -> str:
    return f"{int(sec)}s" if sec < 90 else f"{int(sec // 60)}m{int(sec % 60)}s"


def main() -> None:
    files = sorted(PROGRESS_DIR.glob("*.json")) if PROGRESS_DIR.exists() else []
    if not files:
        print("no runs found (results/_progress/ is empty). Progress appears once a "
              "run finishes its first round.")
        return
    now = time.time()
    rows = []
    for f in files:
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        age = now - d.get("updated", now)
        phase = d.get("phase", "?")
        pos = phase if phase in ("measuring", "done") else f"{d.get('round','?')}/{d.get('n_rounds','?')}"
        state = "DONE" if phase == "done" else ("STALE" if age > 180 else "live")
        rows.append((d.get("scenario", f.stem), d.get("p", ""), pos,
                     d.get("deals_closed", 0), d.get("llm_calls", 0),
                     d.get("avg_call_s", 0), d.get("slow_calls", 0),
                     _fmt_age(d.get("elapsed_s", 0)), _fmt_age(age), state))

    hdr = ("run", "p", "round", "deals", "calls", "avg_s", "slow", "elapsed", "hb-age", "state")
    w = [max(len(str(r[i])) for r in rows + [hdr]) for i in range(len(hdr))]
    line = lambda r: "  ".join(str(c).ljust(w[i]) for i, c in enumerate(r))
    print(line(hdr))
    print("  ".join("-" * x for x in w))
    for r in sorted(rows, key=lambda r: str(r[0])):
        print(line(r))
    print("\nslow = calls >10s (≈ rate-limit backoff).  STALE = heartbeat >3min old "
          "(stuck or finished).  Progress updates once per round.")


if __name__ == "__main__":
    main()
