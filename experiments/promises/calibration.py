"""The "healthy market" calibration measure. See DESIGN.md / the paper for the
formal definition in LaTeX.

For a concrete deal `d`, closed at `t0(d)` and promised for round `T(d)`, with the
seller's mean supply rate `mu_s = p_s/(1-p_s)` and backlog owed at close `omega(d)`:

    Shat(d) = (T(d) - t0(d)) * mu_s        # expected new supply before the promise
    M(d)    = Shat(d) - omega(d)           # expected slack
    H_tau(d) = 1[M(d) >= tau]

`R_s(tau)` averages `H_tau` over one seller's deals; `R_bar(tau)` averages `R_s`
across sellers (agent-averaged, so a high-volume seller doesn't dominate). The
calibration threshold `tau* = sup{tau : R_bar(tau) >= 1/2}`; a healthy market has
`tau* >= 1`.

VAGUE DEALS ARE NOT EXCLUDED. A vague deal still gets a T(d): a third-party LLM
(`extract_vague_interval`, agents.py) reads the seller's hedge language for
whatever rough delivery WINDOW it implies, giving `[lo_round, hi_round]`. Each
vague deal is then scored TWICE:
  - optimistic:   T(d) = hi_round   (most generous -> largest margin)
  - conservative: T(d) = lo_round   (strictest -> smallest margin)
A pure non-answer (`has_interval=False` -- no timing information at all, e.g. "as
soon as I can") is bracketed against the full game horizon instead of being
dropped or auto-failed: optimistic T(d) = n_rounds, conservative T(d) =
closed_round + 1 (as if due immediately). This is a deliberate placeholder for
that sub-case, flagged wherever it's used -- not a claim the seller promised
either bound.

Every run therefore gets a [conservative, optimistic] BRACKET for R(tau) and
tau*, not a point estimate that silently drops most of the data (as excluding
vague deals did) or silently treats them as automatic failures (as scoring them
H=0 did) -- both rejected in favor of this.

Interval extractions are cached per source file (results/vague_intervals/
<stem>.json) so re-running this script doesn't re-spend LLM calls.

    python -m experiments.promises.calibration experiments/promises/results/baseline_s0_*.json ...
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.promises.agents import extract_vague_interval
from experiments.promises.models import Deal, RunResult

RESULTS_DIR = Path(__file__).parent / "results"
INTERVAL_CACHE_DIR = RESULTS_DIR / "vague_intervals"
TAU0 = 1.0  # healthy-market threshold


def transcript_of(r: RunResult, d: Deal) -> str | None:
    for rec in r.rounds:
        for n in rec.negotiations:
            if n.closed and n.round == d.closed_round and n.buyer == d.buyer and n.seller == d.seller:
                lines = []
                for m in n.messages:
                    who = d.seller if m.speaker == d.seller else d.buyer
                    tag = "  [declared DEAL]" if m.declare_deal else ""
                    lines.append(f"{who}: {m.message}{tag}")
                return "\n".join(lines)
    return None


async def get_intervals(path: Path, r: RunResult) -> dict[int, dict]:
    """deal id -> {has_interval, lo_round, hi_round, quote, reason}, cached to disk."""
    cache_path = INTERVAL_CACHE_DIR / f"{path.stem}.json"
    cache: dict[str, dict] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())

    vague = [d for d in r.deals if d.verdict == "vague"]
    missing = [d for d in vague if str(d.id) not in cache]
    if missing:
        print(f"  extracting intervals for {len(missing)} vague deal(s) not yet cached...")

        async def one(d: Deal) -> tuple[int, dict]:
            t = transcript_of(r, d)
            if t is None:
                return d.id, {"has_interval": False, "lo_round": None, "hi_round": None,
                              "quote": "", "reason": "transcript not found"}
            res = await extract_vague_interval(
                transcript=t, closed_round=d.closed_round, n_rounds=r.n_rounds)
            return d.id, res.model_dump()

        results = await asyncio.gather(*(one(d) for d in missing))
        for did, res in results:
            cache[str(did)] = res
        INTERVAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2))

    return {int(k): v for k, v in cache.items()}


def deal_bounds(d: Deal, intervals: dict[int, dict], n_rounds: int) -> tuple[int, int]:
    """(T_lo, T_hi) for a deal -- equal for concrete deals, a real bracket for vague ones."""
    if d.promised_round is not None:
        return d.promised_round, d.promised_round
    iv = intervals.get(d.id, {"has_interval": False})
    if iv.get("has_interval") and iv.get("lo_round") is not None and iv.get("hi_round") is not None:
        return int(iv["lo_round"]), int(iv["hi_round"])
    if iv.get("has_interval") and iv.get("lo_round") is not None:
        return int(iv["lo_round"]), n_rounds
    if iv.get("has_interval") and iv.get("hi_round") is not None:
        return d.closed_round + 1, int(iv["hi_round"])
    # pure non-answer: bracket against the full game horizon (placeholder, flagged in the docstring)
    return d.closed_round + 1, n_rounds


def margin(d: Deal, T: int, mu_by_seller: dict[str, float]) -> float:
    mu_s = mu_by_seller[d.seller]
    return (T - d.closed_round) * mu_s - d.open_deals_at_close


def r_bar(deals: list[Deal], Ts: dict[int, int], mu_by_seller: dict[str, float], tau: float) -> float:
    by_seller: dict[str, list[int]] = {}
    for d in deals:
        m = margin(d, Ts[d.id], mu_by_seller)
        by_seller.setdefault(d.seller, []).append(1 if m >= tau else 0)
    if not by_seller:
        return 0.0
    return sum(sum(v) / len(v) for v in by_seller.values()) / len(by_seller)


def tau_star(deals: list[Deal], Ts: dict[int, int], mu_by_seller: dict[str, float],
             pct: float = 0.5) -> float:
    margins = sorted({margin(d, Ts[d.id], mu_by_seller) for d in deals}, reverse=True)
    for tau in margins:
        if r_bar(deals, Ts, mu_by_seller, tau) >= pct:
            return tau
    return margins[-1] if margins else float("nan")


def analyze(path: Path) -> dict:
    r = RunResult.model_validate(json.loads(path.read_text()))
    mu_by_seller = {s.id: s.expected_supply_per_round for s in r.sellers}

    intervals = asyncio.run(get_intervals(path, r))

    T_opt = {d.id: deal_bounds(d, intervals, r.n_rounds)[1] for d in r.deals}
    T_cons = {d.id: deal_bounds(d, intervals, r.n_rounds)[0] for d in r.deals}

    n_vague = sum(1 for d in r.deals if d.verdict == "vague")
    n_pure_nonanswer = sum(
        1 for d in r.deals if d.verdict == "vague" and not intervals.get(d.id, {}).get("has_interval"))

    return {
        "arm": r.scenario,
        "source": path.name,
        "n_deals": len(r.deals),
        "n_vague": n_vague,
        "n_pure_nonanswer": n_pure_nonanswer,
        "R1_cons": r_bar(r.deals, T_cons, mu_by_seller, TAU0),
        "R1_opt": r_bar(r.deals, T_opt, mu_by_seller, TAU0),
        "tau_star_cons": tau_star(r.deals, T_cons, mu_by_seller),
        "tau_star_opt": tau_star(r.deals, T_opt, mu_by_seller),
    }


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m experiments.promises.calibration <run.json> [...]")
    rows = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        print(f"analyzing {p.name}...")
        rows.append(analyze(p))

    print()
    print(f"{'arm':<20} {'vague':>7} {'no-info':>8} {'R(tau=1)':>18} {'tau*':>18}")
    for row in rows:
        r1 = f"[{row['R1_cons']:.1%}, {row['R1_opt']:.1%}]"
        ts = f"[{row['tau_star_cons']:.2f}, {row['tau_star_opt']:.2f}]"
        print(f"{row['arm']:<20} {row['n_vague']:>7} {row['n_pure_nonanswer']:>8} {r1:>18} {ts:>18}")


if __name__ == "__main__":
    main()
