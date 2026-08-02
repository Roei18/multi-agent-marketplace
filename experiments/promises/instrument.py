"""Run instrumentation so we can SEE where a run stands (the debuggability layer).

Two pieces:
  1. `call_llm` — a thin wrapper around the real one that counts calls, total wait
     time, and "slow" calls (>10s ≈ a 429 backoff, i.e. throttling), with no change
     to the shared llm client. agents.py imports call_llm from here.
  2. `heartbeat()` — run_market writes a tiny JSON to results/_progress/<run>.json
     after every round and phase, so `status.py` can show live progress even under
     --quiet (which otherwise prints nothing until the run ends).

This is what was missing: a --quiet run used to be a black box until it saved.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from experiments.dealrace.llm import call_llm as _call_llm

PROGRESS_DIR = Path(__file__).parent / "results" / "_progress"
SLOW_CALL_S = 10.0  # a single call taking longer than this ≈ hit a rate-limit backoff

_stats = {"calls": 0, "slow": 0, "wait_s": 0.0}


async def call_llm(prompt, response_format, **kw):
    t0 = time.time()
    try:
        return await _call_llm(prompt, response_format, **kw)
    finally:
        dt = time.time() - t0
        _stats["calls"] += 1
        _stats["wait_s"] += dt
        if dt > SLOW_CALL_S:
            _stats["slow"] += 1


def _path(scenario: str, seed: int, p: float) -> Path:
    tag = "" if abs(p - 0.6) < 1e-9 else f"_p{round(p * 100):02d}"
    return PROGRESS_DIR / f"{scenario}_s{seed}{tag}.json"


def heartbeat(scenario: str, seed: int, p: float, *, phase: str, round_no: int,
              n_rounds: int, deals_closed: int, start: float) -> None:
    """Write a progress snapshot. Never raises — instrumentation must not break a run."""
    try:
        PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
        calls = _stats["calls"]
        _path(scenario, seed, p).write_text(json.dumps({
            "scenario": scenario, "seed": seed, "p": p,
            "phase": phase, "round": round_no, "n_rounds": n_rounds,
            "deals_closed": deals_closed,
            "llm_calls": calls, "slow_calls": _stats["slow"],
            "avg_call_s": round(_stats["wait_s"] / calls, 2) if calls else 0.0,
            "elapsed_s": round(time.time() - start), "pid": os.getpid(),
            "updated": round(time.time(), 1),
        }, indent=2))
    except Exception:
        pass
