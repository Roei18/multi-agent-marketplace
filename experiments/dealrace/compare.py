"""Compare two dealrace runs side by side and write a concise report.

Answers two questions for each run and puts them next to each other:
  1. How did the environment do — how many deals closed, and how many broke?
  2. What kinds of promises were made — the true / false / vague split?

    python -m experiments.dealrace.compare <base.json> <attributor.json>
    python -m experiments.dealrace.compare   # auto: newest uniform vs newest attributor
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


def newest(glob: str) -> Path | None:
    hits = sorted(RESULTS_DIR.glob(glob), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def pct(n: float, d: float) -> str:
    return f"{100 * n / d:.0f}%" if d else "—"


def summarise(data: dict) -> dict:
    a = data["attribution"]
    closed = a["deals_closed"]
    return {
        "label": ("attributor (fines false promises)" if data.get("apply_attributor")
                  else "baseline (no fines)"),
        "scenario": data["scenario"], "seed": data["seed"],
        "n_rounds": data["n_rounds"],
        "closed": closed,
        "honored": a["deals_honored"],
        "broken": a["deals_never_honored"],
        "broken_pct": pct(a["deals_never_honored"], closed),
        "goods_drawn": a["goods_drawn_total"],
        "handed_over": a["units_handed_over"],
        "leftover": a.get("stock_leftover_total", 0),
        "true": a["judge_true"], "false": a["judge_false"], "vague": a["judge_vague"],
        "true_pct": pct(a["judge_true"], closed),
        "false_pct": pct(a["judge_false"], closed),
        "vague_pct": pct(a["judge_vague"], closed),
        "voided": a.get("deals_voided_by_attributor", 0),
    }


def render(base: dict, attr: dict) -> str:
    def row(name, key, fmt=lambda x: x):
        return f"| {name} | {fmt(base[key])} | {fmt(attr[key])} |"

    L = [
        "# dealrace — baseline vs attributor",
        "",
        f"Baseline: `{base['scenario']}` seed {base['seed']} · "
        f"Attributor: `{attr['scenario']}` seed {attr['seed']} · "
        f"{base['n_rounds']} rounds each. One seed each — direction, not effect size.",
        "",
        f"Both games are identical — no elimination, all sellers play all {base['n_rounds']} "
        "rounds, hidden stock, goods accumulate, buyer points race. The **only** difference: "
        "the attributor run voids each seller's broken clear promises from its score and tells "
        "the sellers so. So any gap below is the effect of the attributor alone.",
        "",
        "## 1. How did the environment do?",
        "",
        "| | baseline | attributor |",
        "|---|---|---|",
        row("deals closed", "closed"),
        row("delivered (honoured)", "honored"),
        f"| **deals broken** | **{base['broken']} ({base['broken_pct']})** | "
        f"**{attr['broken']} ({attr['broken_pct']})** |",
        row("goods drawn", "goods_drawn"),
        row("goods handed over", "handed_over"),
        row("unsold stock left over", "leftover"),
        "",
        "## 2. What kinds of promises were there?",
        "",
        "(third-party judge, timing-based: *true* = clear time + delivered, *false* = clear "
        "time + broken, *vague* = no time ever pinned)",
        "",
        "| | baseline | attributor |",
        "|---|---|---|",
        f"| true (kept clear promise) | {base['true']} ({base['true_pct']}) | "
        f"{attr['true']} ({attr['true_pct']}) |",
        f"| false (broken clear promise) | {base['false']} ({base['false_pct']}) | "
        f"{attr['false']} ({attr['false_pct']}) |",
        f"| **vague (no promise made)** | **{base['vague']} ({base['vague_pct']})** | "
        f"**{attr['vague']} ({attr['vague_pct']})** |",
        "",
        f"Attributor voided **{attr['voided']}** deals (the false ones) from seller scores; "
        "the base game fines nothing.",
        "",
        "## The comparison that matters",
        "",
        f"Vagueness: **{base['vague_pct']} → {attr['vague_pct']}** of deals. "
        "If it rises under the attributor, sellers are dodging the fine by not promising a "
        "time (vague deals are never voided). If it doesn't, the fine didn't change how they "
        "talk.",
    ]
    return "\n".join(L) + "\n"


def main() -> None:
    if len(sys.argv) >= 3:
        bpath, apath = Path(sys.argv[1]), Path(sys.argv[2])
    else:
        bpath = newest("baseline_s*.json")
        apath = newest("attributor_s*.json")
        if not bpath or not apath:
            raise SystemExit("need a baseline_* and an attributor_* result in results/, "
                             "or pass two paths explicitly")
    base = summarise(json.loads(bpath.read_text()))
    attr = summarise(json.loads(apath.read_text()))
    md = render(base, attr)
    out = RESULTS_DIR / "compare_base_vs_attributor.md"
    out.write_text(md)
    print(md)
    print(f"\n(base: {bpath.name}  ·  attributor: {apath.name})")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
