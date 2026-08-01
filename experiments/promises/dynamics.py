"""Market-dynamics analysis over saved promises runs. Pure — no LLM.

Measures the CURRENT (lock-fix) version only — 8x16x12, single good, one deal per
round with NO cross-round lock (`lock_rounds == 0`, 192 deals, closes every round).
The earlier 'lock-next-round' runs (`lock_rounds == 1`, 96 deals) are excluded.

Three groups:

1. DEAL DISTRIBUTION — vague / true / false, overall and per round the deal closed in.

2. SOCIAL WELFARE — the spread between the top and the average agent on each side.
   Sellers score net deals (closed − voided); buyers score goods owned. We report
   top, mean, and the gap (top − mean, and top / mean) — how much the winner runs
   away from the pack.

3. NEGOTIATIONS / TRUST —
   - attempts to close (sellers a buyer goes through before it lands a deal);
   - conversation length (turns), closed vs walked;
   - return-to-deliverer: do buyers go BACK to sellers who delivered to them?
   - avoidance: do buyers STOP going back to sellers who let them down (a prior
     deal that never delivered)? Reported as re-approach rates conditional on the
     buyer's own past experience with that seller.

    python -m experiments.promises.dynamics                 # newest fair run per arm, seed 0
    python -m experiments.promises.dynamics --seeds 0 1 2   # average over seeds
    python -m experiments.promises.dynamics a.json b.json …  # explicit files
"""

from __future__ import annotations

import json
import statistics
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


# Which lock generation to select. lock=0 is the "lock-fix" version (one deal per
# round, no cross-round lock, 192 deals, closes every round). lock=1 is the earlier
# "2-round-blocked" version (a closed deal also blocks the NEXT round, 96 deals,
# closes odd rounds only). Both are single-good 8x16x12.
LOCK = 1
PROB = 0.6   # supply parameter of the standard runs; a study at another p is separate


def _is_fair(r: RunResult) -> bool:
    return (r.n_sellers == 8 and r.n_rounds == 12
            and abs(r.heads_prob - PROB) < 1e-9
            and all(d.quantity == 1 for d in r.deals)
            and all(d.lock_rounds == LOCK for d in r.deals))


def newest_fair(arm: str, seed: int | None = None) -> Path | None:
    pat = f"{arm}_s{seed}_*.json" if seed is not None else f"{arm}_s*.json"
    for p in sorted(RESULTS_DIR.glob(pat), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            if _is_fair(RunResult.model_validate(json.loads(p.read_text()))):
                return p
        except Exception:
            continue
    return None


def _rate(x, d):
    return round(x / d, 3) if d else 0.0


def analyze(r: RunResult) -> dict:
    n = r.n_rounds
    negs = [ng for rec in r.rounds for ng in rec.negotiations]

    # ---- Group 1: deal distribution (overall + per round) ----
    def vtf(ds):
        return {
            "deals": len(ds),
            "vague": sum(d.verdict == "vague" for d in ds),
            "true": sum(d.verdict == "true" for d in ds),
            "false": sum(d.verdict in ("false-late", "false-never") for d in ds),
        }

    by_round: dict[int, list] = {t: [] for t in range(1, n + 1)}
    for d in r.deals:
        by_round.setdefault(d.closed_round, []).append(d)
    series = [{"round": t, **vtf(by_round.get(t, []))} for t in range(1, n + 1)]
    overall = vtf(r.deals)
    nd = max(1, len(r.deals))
    overall_rates = {"vague_rate": _rate(overall["vague"], nd),
                     "true_rate": _rate(overall["true"], nd),
                     "false_rate": _rate(overall["false"], nd)}

    # ---- Group 2: social welfare — top vs average spread ----
    seller_scores = sorted((s.net_score for s in r.sellers), reverse=True)
    buyer_scores = sorted((b.owned for b in r.buyers), reverse=True)

    def spread(xs):
        top = xs[0] if xs else 0
        mean = statistics.mean(xs) if xs else 0
        return {"top": top, "mean": round(mean, 2),
                "gap_abs": round(top - mean, 2),
                "gap_ratio": round(top / mean, 2) if mean else 0.0}

    welfare = {"seller": spread(seller_scores), "buyer": spread(buyer_scores),
               "true_deals": overall["true"]}

    # ---- Group 3: negotiations / trust ----
    # attempts to close (sellers gone through before landing the deal)
    close_attempts = [ng.attempt for ng in negs if ng.closed]
    ceiling = max(close_attempts) if close_attempts else 0
    attempt_hist = {k: close_attempts.count(k) for k in range(1, ceiling + 1)}

    # distinct sellers a buyer approaches over the whole game
    seen: dict[str, set] = {}
    for ng in negs:
        seen.setdefault(ng.buyer, set()).add(ng.seller)
    distinct_per_buyer = [len(s) for s in seen.values()]

    # conversation length, closed vs walked
    len_closed = [len(ng.messages) for ng in negs if ng.closed]
    len_walked = [len(ng.messages) for ng in negs if not ng.closed]
    len_all = [len(ng.messages) for ng in negs]

    # --- trust: what the buyer knew about a seller when it approached ---
    # first round a seller delivered a good to a buyer (from ground-truth handoffs)
    first_delivery: dict[tuple, int] = {}
    for h in r.handoffs:
        key = (h.seller, h.buyer)
        first_delivery[key] = min(first_delivery.get(key, h.round), h.round)
    # first round a (seller,buyer) deal closed that NEVER delivered a good — a let-down
    first_letdown: dict[tuple, int] = {}
    for d in r.deals:
        if d.delivered_round < 0:  # buyer got nothing from this deal, ever
            key = (d.seller, d.buyer)
            first_letdown[key] = min(first_letdown.get(key, d.closed_round), d.closed_round)

    # approach-level rates: of all approaches, share to a prior deliverer / prior let-down
    appr_total = ret_deliv = ret_letdown = 0
    for ng in negs:
        t, key = ng.round, (ng.seller, ng.buyer)
        appr_total += 1
        if first_delivery.get(key, 10**9) < t:
            ret_deliv += 1
        if first_letdown.get(key, 10**9) < t:
            ret_letdown += 1

    # pair-level LEARNING: after a seller delivered to a buyer, does the buyer come
    # back? after a seller let the buyer down, does the buyer come back? (avoidance)
    appr_rounds: dict[tuple, list] = {}
    for ng in negs:
        appr_rounds.setdefault((ng.seller, ng.buyer), []).append(ng.round)

    def reapproached_after(event_round: dict) -> tuple[int, int]:
        back = tot = 0
        for key, r0 in event_round.items():
            tot += 1
            if any(rr > r0 for rr in appr_rounds.get(key, [])):
                back += 1
        return back, tot

    back_d, pairs_d = reapproached_after(first_delivery)
    back_l, pairs_l = reapproached_after(first_letdown)

    # attributor activity: how many deals it voided (fined) as broken promises
    fines = sum(1 for d in r.deals if d.fined)

    # lawyer activity: how the DECLINING of vague commitments distributes.
    # Per negotiation the lawyer blocks 0/1/2 times; a block forces one concretizing
    # exchange, then a deal either recovers (closes concrete) or walks (never pinned).
    lw_reviewed = sum(1 for ng in negs if ng.lawyer_vague is not None)
    lw_declines = sum(ng.lawyer_blocked_count for ng in negs)
    lw_clean = sum(1 for ng in negs if ng.lawyer_vague is not None and ng.lawyer_blocked_count == 0)
    lw_once = sum(1 for ng in negs if ng.lawyer_blocked_count == 1)
    lw_twice = sum(1 for ng in negs if ng.lawyer_blocked_count >= 2)
    lw_blocked = sum(1 for ng in negs if ng.lawyer_blocked_count > 0)
    lw_recovered = sum(1 for ng in negs if ng.lawyer_blocked_count > 0 and ng.closed)
    lw_walked = sum(1 for ng in negs if ng.lawyer_blocked_count > 0 and not ng.closed)
    lw_by_round = [sum(ng.lawyer_blocked_count for ng in negs if ng.round == t)
                   for t in range(1, n + 1)]

    return {
        "scenario": r.scenario, "seed": r.seed, "n_rounds": n, "n_sellers": r.n_sellers,
        "n_negs": len(negs), "n_closed": len(close_attempts), "n_deals": len(r.deals),
        # group 1
        "series": series, "overall": overall, **overall_rates,
        # group 2
        "welfare": welfare,
        # group 3
        "attempts_mean": round(statistics.mean(close_attempts), 2) if close_attempts else 0,
        "closed_on_1st_rate": _rate(attempt_hist.get(1, 0), len(close_attempts)),
        "attempts_hist": attempt_hist,
        "distinct_mean": round(statistics.mean(distinct_per_buyer), 2) if distinct_per_buyer else 0,
        "len_all_mean": round(statistics.mean(len_all), 2) if len_all else 0,
        "len_all_median": statistics.median(len_all) if len_all else 0,
        "len_closed_mean": round(statistics.mean(len_closed), 2) if len_closed else 0,
        "len_walked_mean": round(statistics.mean(len_walked), 2) if len_walked else 0,
        "n_walked": len(len_walked),
        "close_rate": _rate(len(len_closed), len(negs)),
        "return_to_deliverer_rate": _rate(ret_deliv, appr_total),
        "return_to_letdown_rate": _rate(ret_letdown, appr_total),
        "reapproach_after_delivery": _rate(back_d, pairs_d),
        "reapproach_after_letdown": _rate(back_l, pairs_l),
        "pairs_delivered": pairs_d, "pairs_letdown": pairs_l,
        "fines": fines,
        # lawyer declining
        "lw_reviewed": lw_reviewed, "lw_declines": lw_declines, "lw_clean": lw_clean,
        "lw_once": lw_once, "lw_twice": lw_twice, "lw_blocked": lw_blocked,
        "lw_recovered": lw_recovered, "lw_walked": lw_walked, "lw_by_round": lw_by_round,
    }


def render(arms: list[dict], seed_label: str) -> str:
    cols = " | ".join(LABEL.get(a["scenario"], a["scenario"]) for a in arms)
    sep = "|".join(["---"] * (len(arms) + 1))

    def row(label, fn):
        return f"| {label} | " + " | ".join(str(fn(a)) for a in arms) + " |"

    ver = ("one deal per round, no cross-round lock → 192 deals, closes every round"
           if LOCK == 0 else
           "2-round-blocked: a closed deal also blocks the next round → 96 deals, "
           "closes odd rounds only")
    L = [
        f"# promises — market dynamics (4-arm, lock={LOCK} version)",
        "",
        f"8×16×12, {seed_label}. **{ver}.** Pure post-hoc, no LLM; "
        "`python -m experiments.promises.dynamics`.",
        "",
        "## 1 — Deal distribution (vague / true / false)",
        "",
        f"| | {cols} |", f"|{sep}|",
        row("total deals", lambda a: a["n_deals"]),
        row("vague %", lambda a: round(a["vague_rate"] * 100)),
        row("true %", lambda a: round(a["true_rate"] * 100)),
        row("false %", lambda a: round(a["false_rate"] * 100)),
        "",
        "## 2 — Social welfare (top vs average agent)",
        "",
        "*Seller score = net deals (closed − voided); buyer score = goods owned. "
        "Gap = how far the winner runs from the average.*",
        "",
        f"| | {cols} |", f"|{sep}|",
        row("seller: top", lambda a: a["welfare"]["seller"]["top"]),
        row("seller: average", lambda a: a["welfare"]["seller"]["mean"]),
        row("seller: gap (top−avg)", lambda a: a["welfare"]["seller"]["gap_abs"]),
        row("seller: top/avg", lambda a: a["welfare"]["seller"]["gap_ratio"]),
        row("buyer: top", lambda a: a["welfare"]["buyer"]["top"]),
        row("buyer: average", lambda a: a["welfare"]["buyer"]["mean"]),
        row("buyer: gap (top−avg)", lambda a: a["welfare"]["buyer"]["gap_abs"]),
        row("buyer: top/avg", lambda a: a["welfare"]["buyer"]["gap_ratio"]),
        row("true deals (welfare good)", lambda a: a["welfare"]["true_deals"]),
        "",
        "## 3 — Negotiations & trust",
        "",
        "*A buyer gets ≤3 approaches/round, one seller each; closing locks it for the "
        "round (so attempts-to-close ≤ 3 by design).*",
        "",
        f"| | {cols} |", f"|{sep}|",
        row("attempts to close (mean)", lambda a: a["attempts_mean"]),
        row("closed on 1st seller %", lambda a: round(a["closed_on_1st_rate"] * 100)),
        row("distinct sellers/buyer over game (of 8)", lambda a: a["distinct_mean"]),
        row("conversation length (mean turns, cap 12)", lambda a: a["len_all_mean"]),
        row("  — closed-with-deal", lambda a: a["len_closed_mean"]),
        row("close rate", lambda a: a["close_rate"]),
        row("walked away (no deal, count)", lambda a: round(a["n_walked"], 1)),
        row("attributor fines given (deals voided)", lambda a: a["fines"]),
        "",
        "### Trust — do buyers reward deliverers and avoid let-downs?",
        "",
        "*return-to-X rate = share of ALL approaches that go to a seller who had "
        "already X'd this buyer in an earlier round. re-approach-after-X = of "
        "(seller,buyer) pairs where X happened, share the buyer approached that "
        "seller again afterward. delivery = got a good; let-down = a prior deal that "
        "never delivered.*",
        "",
        f"| | {cols} |", f"|{sep}|",
        row("return-to-deliverer rate", lambda a: a["return_to_deliverer_rate"]),
        row("return-to-let-down rate", lambda a: a["return_to_letdown_rate"]),
        row("re-approach AFTER a delivery",
            lambda a: f"{a['reapproach_after_delivery']} (n={round(a['pairs_delivered'])})"),
        row("re-approach AFTER a let-down",
            lambda a: f"{a['reapproach_after_letdown']} (n={round(a['pairs_letdown'])})"),
        "",
    ]

    # lawyer-only section: how declining vague commitments distributes
    law = next((a for a in arms if a["scenario"] == "lawyer_attributor"), None)
    if law and law["lw_reviewed"]:
        rev, dec = law["lw_reviewed"], law["lw_declines"]
        L += [
            "### Lawyer — how declining distributes (lawyer+attr arm)",
            "",
            "*On a vague close the lawyer blocks it and forces one concretizing exchange; "
            "the deal then either recovers (closes with a round pinned) or walks (never "
            "pinned → no deal). Per negotiation it blocks 0/1/2 times.*",
            "",
            "| metric | value |", "|---|---|",
            f"| commitments reviewed | {round(rev, 1)} |",
            f"| total declines | {round(dec, 1)} |",
            f"| passed clean (0 blocks) | {round(law['lw_clean'], 1)} "
            f"({round(100 * law['lw_clean'] / rev) if rev else 0}%) |",
            f"| declined once | {round(law['lw_once'], 1)} |",
            f"| declined twice (max) | {round(law['lw_twice'], 1)} |",
            f"| of declined: recovered (closed) | {round(law['lw_recovered'], 1)} "
            f"({round(100 * law['lw_recovered'] / law['lw_blocked']) if law['lw_blocked'] else 0}%) |",
            f"| of declined: walked (no deal) | {round(law['lw_walked'], 1)} "
            f"({round(100 * law['lw_walked'] / law['lw_blocked']) if law['lw_blocked'] else 0}%) |",
            "",
            "Declines per round (front-loaded — sellers learn to commit up front):",
            "",
            "| " + " | ".join(str(t) for t in range(1, law["n_rounds"] + 1)) + " |",
            "|" + "---|" * law["n_rounds"],
            "| " + " | ".join(str(x) for x in law["lw_by_round"]) + " |",
            "",
        ]

    L += [
        "## Per-round deal distribution",
        "",
    ]
    for a in arms:
        L += [f"### {LABEL.get(a['scenario'], a['scenario'])} "
              f"(seed {a['seed']}, {a['n_deals']} deals)", "",
              "| round | deals | vague | true | false |", "|---|---|---|---|---|"]
        for s in a["series"]:
            L.append(f"| {s['round']} | {s['deals']} | {s['vague']} | {s['true']} | {s['false']} |")
        L.append("")
    return "\n".join(L) + "\n"


def _avg_arms(per_seed: list[list[dict]]) -> list[dict]:
    """Average numeric scalars across seeds; sum attempt histograms; mean the series
    and the nested welfare/rate structures. Single-seed input passes through."""
    out = []
    for arm_idx in range(len(per_seed[0])):
        variants = [ps[arm_idx] for ps in per_seed]
        base = dict(variants[0])
        if len(variants) == 1:
            out.append(base)
            continue

        def mean_key(k):
            return round(statistics.mean(v[k] for v in variants), 2)

        for k, v0 in list(base.items()):
            if isinstance(v0, (int, float)) and not isinstance(v0, bool):
                base[k] = mean_key(k)
        # attempt histogram: sum counts
        hist: dict[int, int] = {}
        for v in variants:
            for kk, c in v["attempts_hist"].items():
                hist[kk] = hist.get(kk, 0) + c
        base["attempts_hist"] = hist
        # welfare: average each nested field
        base["welfare"] = {
            "seller": {kk: round(statistics.mean(v["welfare"]["seller"][kk] for v in variants), 2)
                       for kk in variants[0]["welfare"]["seller"]},
            "buyer": {kk: round(statistics.mean(v["welfare"]["buyer"][kk] for v in variants), 2)
                      for kk in variants[0]["welfare"]["buyer"]},
            "true_deals": round(statistics.mean(v["welfare"]["true_deals"] for v in variants), 1),
        }
        # series: mean per round
        n = base["n_rounds"]
        base["series"] = [{
            "round": t + 1,
            "deals": round(statistics.mean(v["series"][t]["deals"] for v in variants), 1),
            "vague": round(statistics.mean(v["series"][t]["vague"] for v in variants), 1),
            "true": round(statistics.mean(v["series"][t]["true"] for v in variants), 1),
            "false": round(statistics.mean(v["series"][t]["false"] for v in variants), 1),
        } for t in range(n)]
        base["lw_by_round"] = [round(statistics.mean(v["lw_by_round"][t] for v in variants), 1)
                               for t in range(n)]
        base["seed"] = "avg"
        out.append(base)
    return out


def main() -> None:
    argv = sys.argv[1:]
    seeds = None
    if "--seeds" in argv:
        i = argv.index("--seeds")
        seeds = [int(x) for x in argv[i + 1:]]
        argv = argv[:i]

    if argv:  # explicit files
        arms = [analyze(RunResult.model_validate(json.loads(Path(p).read_text()))) for p in argv]
        arms.sort(key=lambda a: ARMS.index(a["scenario"]) if a["scenario"] in ARMS else 99)
        md = render(arms, f"seed {arms[0]['seed']}")
    else:
        use = seeds if seeds else [0]
        per_seed = []
        for sd in use:
            paths = [newest_fair(a, sd) for a in ARMS]
            if any(p is None for p in paths):
                miss = [a for a, p in zip(ARMS, paths) if p is None]
                raise SystemExit(f"seed {sd}: no lock-fix run for {miss} "
                                 "(need lock_rounds==0, 192-deal, 12-round files)")
            per_seed.append([analyze(RunResult.model_validate(json.loads(p.read_text())))
                             for p in paths])
        arms = _avg_arms(per_seed)
        md = render(arms, f"averaged over seeds {use}" if len(use) > 1 else "seed 0")

    out = RESULTS_DIR / "dynamics.md"
    out.write_text(md)
    print(md)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
