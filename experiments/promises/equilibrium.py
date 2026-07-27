"""Equilibrium / convergence analysis over saved promises runs. Pure — no LLM.

Answers three questions the market only reveals over a longer game:
  1. CONVERGENCE — what state did it settle into? Deals rising or falling; do sellers
     get more vague or more truthful as rounds pass (first-third vs last-third).
  2. BUYER TRUST — return-to-deliverer rate per round: share of approaches that go to
     a seller who ALREADY delivered to that buyer. Rising = buyers learn to return to
     proven sellers instead of exploring.
  3. SOCIAL WELFARE — number of TRUE deals (honest, on-time transactions) plus the
     winners' profit (seller winner's net deals, buyer champion's goods).

    python -m experiments.promises.equilibrium                 # newest of each arm -> 4-arm table
    python -m experiments.promises.equilibrium a.json b.json …  # explicit files
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.promises.models import RunResult

RESULTS_DIR = Path(__file__).parent / "results"
ARMS = ["baseline", "attributor", "lawyer_attributor", "contract_attributor"]
LABEL = {"baseline": "baseline", "attributor": "attributor",
         "lawyer_attributor": "lawyer+attr", "contract_attributor": "contract+attr"}


def newest(arm: str) -> Path | None:
    # Newest by time overall — fresh runs carry verdicts inline (the vagueness judge
    # runs during the run), so a re-judged file is only newer when we re-measured.
    hits = sorted(RESULTS_DIR.glob(f"{arm}_s*.json"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def _rate(x, d):
    return round(x / d, 3) if d else 0.0


def analyze(r: RunResult) -> dict:
    n = r.n_rounds

    # deals bucketed by the round they closed in
    by_round: dict[int, list] = {t: [] for t in range(1, n + 1)}
    for d in r.deals:
        by_round.setdefault(d.closed_round, []).append(d)

    def counts(ds):
        nd = len(ds)
        return {
            "deals": nd,
            "vague_rate": _rate(sum(d.verdict == "vague" for d in ds), nd),
            "true_rate": _rate(sum(d.verdict == "true" for d in ds), nd),
            "false_rate": _rate(sum(d.verdict in ("false-late", "false-never") for d in ds), nd),
        }

    series = [{"round": t, **counts(by_round.get(t, []))} for t in range(1, n + 1)]

    # return-to-deliverer: earliest round each (seller,buyer) pair saw a delivery
    first_delivery: dict[tuple, int] = {}
    for h in r.handoffs:
        key = (h.seller, h.buyer)
        first_delivery[key] = min(first_delivery.get(key, h.round), h.round)

    approaches: dict[int, list] = {t: [] for t in range(1, n + 1)}
    for rec in r.rounds:
        for ng in rec.negotiations:
            approaches.setdefault(ng.round, []).append((ng.buyer, ng.seller))

    r2d = []
    for t in range(1, n + 1):
        appr = approaches.get(t, [])
        ret = sum(1 for (b, s) in appr
                  if (s, b) in first_delivery and first_delivery[(s, b)] < t)
        r2d.append({"round": t, "approaches": len(appr), "returns": ret,
                    "return_rate": _rate(ret, len(appr))})

    # first-third vs last-third
    k = max(1, n // 3)
    early, late = set(range(1, k + 1)), set(range(n - k + 1, n + 1))

    def deals_in(rs):
        return [d for d in r.deals if d.closed_round in rs]

    def r2d_rate(rs):
        num = sum(e["returns"] for e in r2d if e["round"] in rs)
        den = sum(e["approaches"] for e in r2d if e["round"] in rs)
        return _rate(num, den)

    conv = {
        "early_rounds": sorted(early), "late_rounds": sorted(late),
        "early_deals": len(deals_in(early)), "late_deals": len(deals_in(late)),
        "early_vague": counts(deals_in(early))["vague_rate"],
        "late_vague": counts(deals_in(late))["vague_rate"],
        "early_true": counts(deals_in(early))["true_rate"],
        "late_true": counts(deals_in(late))["true_rate"],
        "early_return": r2d_rate(early), "late_return": r2d_rate(late),
    }

    sw = next((s for s in r.sellers if s.id == r.seller_winner), None)
    bw = next((b for b in r.buyers if b.id == r.buyer_champion), None)
    true_deals = sum(d.verdict == "true" for d in r.deals)
    welfare = {
        "true_deals": true_deals,
        "true_rate": _rate(true_deals, len(r.deals)),
        "seller_winner": r.seller_winner_name, "seller_winner_profit": sw.net_score if sw else 0,
        "buyer_winner": r.buyer_champion_name, "buyer_winner_profit": bw.owned if bw else 0,
    }

    return {"scenario": r.scenario, "seed": r.seed, "n_rounds": n,
            "series": series, "r2d": r2d, "convergence": conv, "welfare": welfare}


def _arrow(a, b):
    return "→" if a == b else ("↑" if b > a else "↓")


def render_arm(a: dict) -> str:
    c, w = a["convergence"], a["welfare"]
    L = [f"### {a['scenario']} (seed {a['seed']}, {a['n_rounds']} rounds)", "",
         "| round | deals | vague | true | false | return-to-deliverer |",
         "|---|---|---|---|---|---|"]
    for s, rr in zip(a["series"], a["r2d"]):
        L.append(f"| {s['round']} | {s['deals']} | {s['vague_rate']} | {s['true_rate']} | "
                 f"{s['false_rate']} | {rr['return_rate']} |")
    L += ["",
          f"- **converged toward** {'more' if c['late_deals'] >= c['early_deals'] else 'fewer'} "
          f"deals/round-window ({c['early_deals']}→{c['late_deals']}); "
          f"vagueness {_arrow(c['early_vague'], c['late_vague'])} "
          f"({c['early_vague']}→{c['late_vague']}); "
          f"truthfulness {_arrow(c['early_true'], c['late_true'])} "
          f"({c['early_true']}→{c['late_true']})",
          f"- **return-to-deliverer** {_arrow(c['early_return'], c['late_return'])} "
          f"({c['early_return']}→{c['late_return']}) early→late",
          f"- **welfare:** {w['true_deals']} true deals ({w['true_rate']}); "
          f"seller winner {w['seller_winner']} profit {w['seller_winner_profit']} net deals; "
          f"buyer champion {w['buyer_winner']} profit {w['buyer_winner_profit']} goods", ""]
    return "\n".join(L)


def render_compare(arms: list[dict]) -> str:
    cols = " | ".join(LABEL.get(a["scenario"], a["scenario"]) for a in arms)
    sep = "|".join(["---"] * (len(arms) + 1))

    def row(label, fn):
        return f"| {label} | " + " | ".join(fn(a) for a in arms) + " |"

    L = [
        "# promises — equilibrium (4-arm)",
        "",
        f"{arms[0]['n_rounds']} rounds each, seed {arms[0]['seed']}. Pure post-hoc analysis "
        "(no LLM); re-run with `python -m experiments.promises.equilibrium`.",
        "",
        "## Convergence (first-third → last-third)",
        "",
        f"| | {cols} |", f"|{sep}|",
        row("deals (early→late window)",
            lambda a: f"{a['convergence']['early_deals']}→{a['convergence']['late_deals']}"),
        row("vague rate (early→late)",
            lambda a: f"{a['convergence']['early_vague']}→{a['convergence']['late_vague']}"),
        row("true rate (early→late)",
            lambda a: f"{a['convergence']['early_true']}→{a['convergence']['late_true']}"),
        "",
        "## Buyer trust — return-to-deliverer rate",
        "",
        f"| | {cols} |", f"|{sep}|",
        row("**early → late**",
            lambda a: f"**{a['convergence']['early_return']}→{a['convergence']['late_return']}**"),
        "",
        "## Social welfare",
        "",
        f"| | {cols} |", f"|{sep}|",
        row("true deals (count)", lambda a: str(a["welfare"]["true_deals"])),
        row("true rate", lambda a: str(a["welfare"]["true_rate"])),
        row("seller-winner profit (net deals)",
            lambda a: str(a["welfare"]["seller_winner_profit"])),
        row("buyer-champion profit (goods)",
            lambda a: str(a["welfare"]["buyer_winner_profit"])),
        "",
        "## Per-arm round-by-round",
        "",
    ]
    L += [render_arm(a) for a in arms]
    return "\n".join(L) + "\n"


def main() -> None:
    if len(sys.argv) >= 2:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        paths = [p for p in (newest(n) for n in ARMS) if p]
        if not paths:
            raise SystemExit("no results found in results/, or pass files explicitly")
    arms = [analyze(RunResult.model_validate(json.loads(p.read_text()))) for p in paths]
    arms.sort(key=lambda a: ARMS.index(a["scenario"]) if a["scenario"] in ARMS else 99)
    md = render_compare(arms)
    out = RESULTS_DIR / "equilibrium.md"
    out.write_text(md)
    print(md)
    print("(" + "  ·  ".join(p.name for p in paths) + f")\nSaved: {out}")


if __name__ == "__main__":
    main()
