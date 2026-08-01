"""Publish a design-change study as a self-contained markdown report.

Each entry in STUDIES is one design point (a change to the market — e.g. the supply
parameter p). Running it selects the matching runs, computes the agreed measurement
shape, and writes `results/studies/<slug>.md` with an explanation of the change and
the tables. This is the durable, trackable record of what each change did.

Measurement shape (decided with the PI):

  DETERMINISTIC market measurements (no LLM)
    - total deals made
    - seller score: top & average   (net deals)
    - buyer score:  top & average   (goods owned)
  LLM-ASSISTED measurements (the vagueness judge is needed to know a time was pinned)
    - deal distribution: vague / true / false  (+ per-round dynamics)
  ATTRIBUTOR arm
    - fines given
    - dynamic of lying per round (false % and vague % by round)

    python -m experiments.promises.studies p04-scarce
    python -m experiments.promises.studies --all
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.promises.dynamics import ARMS, LABEL, analyze, _avg_arms
from experiments.promises.models import RunResult

RESULTS_DIR = Path(__file__).parent / "results"
STUDIES_DIR = RESULTS_DIR / "studies"

# Each design point we publish. Adding a change = adding one entry here.
STUDIES: dict[str, dict] = {
    "p06-standard": {
        "title": "Standard supply — p = 0.6",
        "p": 0.6,
        "seeds": [0, 1, 2],
        "desc": "The reference setting. Each seller draws goods geometrically with "
        "arrival probability **p = 0.6** (mean 1.5 goods/round, ~40% empty rounds). "
        "Over the game ~144 goods are produced against a maximum buyer demand of 96 "
        "(16 buyers × 6 deals), so **supply exceeds demand** — goods are not scarce, "
        "and a seller can be late at little cost to the buyer.\n\n"
        "> Note: these runs predate the per-deal delivery fix, so a few free-text "
        "buyers were over-served — `buyer top` here is inflated by ≤1 (true ceiling is "
        "6). Re-run at p = 0.6 to refresh if an exact baseline is needed.",
    },
    "p04-scarce": {
        "title": "Scarce supply — p = 0.4",
        "p": 0.4,
        "seeds": [0],
        "desc": "Lower the arrival probability to **p = 0.4** (mean 0.67 goods/round, "
        "~60% empty rounds). Over the game only ~64 goods are produced against a "
        "maximum demand of 96, so **demand exceeds supply** — being late or vague now "
        "has a real cost, because a good handed to one buyer is one another cannot get. "
        "Everything else (2-round buyer lock, one good per deal, matched supply RNG) is "
        "unchanged from p = 0.6. Includes the per-deal delivery fix (a buyer holding "
        "several open deals with one seller is no longer over-served).",
    },
}


def _select(arm: str, seed: int, p: float) -> Path | None:
    """Newest run for this arm/seed at supply p (8×16×12, single good, 2-round lock)."""
    hits = sorted(RESULTS_DIR.glob(f"{arm}_s{seed}_*.json"),
                  key=lambda q: q.stat().st_mtime, reverse=True)
    for q in hits:
        try:
            r = RunResult.model_validate(json.loads(q.read_text()))
        except Exception:
            continue
        if (r.n_sellers == 8 and r.n_rounds == 12 and abs(r.heads_prob - p) < 1e-9
                and all(d.quantity == 1 for d in r.deals)
                and all(d.lock_rounds == 1 for d in r.deals)):
            return q
    return None


def _rate(x, d):
    return round(x / d, 3) if d else 0.0


def render(study: dict, arms: list[dict], seeds: list[int]) -> str:
    cols = " | ".join(LABEL.get(a["scenario"], a["scenario"]) for a in arms)
    sep = "|".join(["---"] * (len(arms) + 1))
    seed_txt = (f"seed {seeds[0]}" if len(seeds) == 1
                else f"averaged over seeds {seeds}")

    def row(label, fn):
        return f"| {label} | " + " | ".join(str(fn(a)) for a in arms) + " |"

    L = [
        f"# {study['title']}",
        "",
        study["desc"],
        "",
        f"**Setup:** 8 sellers × 16 buyers × 12 rounds, {seed_txt}. Four arms; matched "
        "supply across arms within a seed. Pure post-hoc measurement — "
        "`python -m experiments.promises.studies`.",
        "",
        "## Deterministic market measurements (no LLM)",
        "",
        f"| | {cols} |", f"|{sep}|",
        row("total deals made", lambda a: a["n_deals"]),
        row("seller score — top", lambda a: a["welfare"]["seller"]["top"]),
        row("seller score — average", lambda a: a["welfare"]["seller"]["mean"]),
        row("buyer score — top", lambda a: a["welfare"]["buyer"]["top"]),
        row("buyer score — average", lambda a: a["welfare"]["buyer"]["mean"]),
        "",
        "*Seller score = net deals (closed − voided); buyer score = goods owned. "
        "Top = the winner; average = across all 8 sellers / 16 buyers.*",
        "",
        "## LLM-assisted measurements (vagueness judge)",
        "",
        "How the closed deals split into vague / true / false. `true`/`false` need the "
        "judge to rule the commitment concrete and pin its round; the kept-vs-broken "
        "step is then arithmetic over the delivery log.",
        "",
        f"| | {cols} |", f"|{sep}|",
        row("vague %", lambda a: round(a["vague_rate"] * 100)),
        row("true %", lambda a: round(a["true_rate"] * 100)),
        row("false %", lambda a: round(a["false_rate"] * 100)),
        "",
        "**Per-round distribution** (deals close in odd rounds only; read vague / true / false):",
        "",
        "| round | " + " | ".join(LABEL.get(a["scenario"], a["scenario"]) for a in arms) + " |",
        "|" + "---|" * (len(arms) + 1),
    ]
    for t in range(len(arms[0]["series"])):
        rd = arms[0]["series"][t]["round"]
        if round(sum(a["series"][t]["deals"] for a in arms)) == 0:  # skip near-empty rounds
            continue
        cells = " | ".join(f"{a['series'][t]['vague']} / {a['series'][t]['true']} / "
                           f"{a['series'][t]['false']}" for a in arms)
        L.append(f"| {rd} | {cells} |")

    # attributor block — fines + lying dynamics for the arms that run the attributor
    L += [
        "",
        "## Attributor",
        "",
        "Fines = concrete promises the attributor voided (delivered late or never). "
        "Lying dynamics = the false and vague share among each round's deals.",
        "",
        f"| | {cols} |", f"|{sep}|",
        row("fines given (deals voided)", lambda a: a["fines"]),
    ]
    att = next((a for a in arms if a["scenario"] == "attributor"), None)
    if att:
        L += [
            "",
            "**Lying dynamics — the *attributor* arm, per round** (share of that round's "
            "deals that are false / vague):",
            "",
            "| round | " + " | ".join(str(s["round"]) for s in att["series"] if s["deals"]) + " |",
            "|" + "---|" * (sum(1 for s in att["series"] if s["deals"]) + 1),
            "| false % | " + " | ".join(str(round(100 * _rate(s["false"], s["deals"])))
                                        for s in att["series"] if s["deals"]) + " |",
            "| vague % | " + " | ".join(str(round(100 * _rate(s["vague"], s["deals"])))
                                        for s in att["series"] if s["deals"]) + " |",
        ]
    return "\n".join(L) + "\n"


def build(slug: str) -> Path:
    study = STUDIES[slug]
    p, seeds = study["p"], study["seeds"]
    per_seed = []
    for sd in seeds:
        paths = [_select(a, sd, p) for a in ARMS]
        if any(x is None for x in paths):
            miss = [a for a, x in zip(ARMS, paths) if x is None]
            raise SystemExit(f"{slug}: missing runs for {miss} at p={p}, seed {sd}")
        per_seed.append([analyze(RunResult.model_validate(json.loads(x.read_text())))
                         for x in paths])
    arms = _avg_arms(per_seed)
    STUDIES_DIR.mkdir(parents=True, exist_ok=True)
    out = STUDIES_DIR / f"{slug}.md"
    out.write_text(render(study, arms, seeds))
    return out


def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit("usage: studies.py <slug|--all>; slugs: " + ", ".join(STUDIES))
    slugs = list(STUDIES) if args[0] == "--all" else args
    for slug in slugs:
        if slug not in STUDIES:
            raise SystemExit(f"unknown study {slug!r}; choose from {', '.join(STUDIES)}")
        out = build(slug)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
