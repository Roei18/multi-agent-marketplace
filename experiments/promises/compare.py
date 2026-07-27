"""Four-way comparison — baseline vs attributor vs lawyer+attributor vs contract.

Auto-discovers the newest run of each arm and lays the measurements out in one
table: volume (deals, delivered, ratio) and the promise distribution
(true / false-late / false-never / vague), plus voided and lawyer-blocked counts.
Every number is mechanical — regenerate any of it with rescore.py.

    python -m experiments.promises.compare                     # newest of each arm
    python -m experiments.promises.compare a.json b.json …     # explicit files
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
ORDER = ["baseline", "attributor", "lawyer_attributor", "contract_attributor"]
LABEL = {"baseline": "baseline", "attributor": "attributor",
         "lawyer_attributor": "lawyer+attr", "contract_attributor": "contract+attr"}


def newest(name: str) -> Path | None:
    hits = sorted(RESULTS_DIR.glob(f"{name}_s*.json"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def pct(n, d) -> str:
    return f"{100 * n / d:.0f}%" if d else "—"


def _backfill_rates(m: dict) -> dict:
    """Older runs stored only raw counts; derive the ratios so any run compares."""
    if "vague_rate" in m:
        return m
    made = int(m.get("deals_made", 0)) or 1
    concrete = int(m.get("true", 0)) + int(m.get("false", 0))
    def r(x, d):
        return round(x / d, 3) if d else 0.0
    m = dict(m)
    m.update({
        "vague_rate": r(int(m.get("vague", 0)), made),
        "concrete_rate": r(concrete, made),
        "true_rate": r(int(m.get("true", 0)), made),
        "false_rate": r(int(m.get("false", 0)), made),
        "false_late_rate": r(int(m.get("false_late", 0)), made),
        "false_never_rate": r(int(m.get("false_never", 0)), made),
        "kept_of_concrete": r(int(m.get("true", 0)), concrete),
        "broken_of_concrete": r(int(m.get("false", 0)), concrete),
        "voided_rate": r(int(m.get("deals_voided", 0)), made),
        "lawyer_block_rate": r(int(m.get("lawyer_blocked", 0)), made),
        "delivered_per_deal": m.get("delivered_per_deal",
                                    r(int(m.get("products_delivered", 0)), made)),
    })
    return m


def load(p: Path) -> dict:
    d = json.loads(p.read_text())
    m = _backfill_rates(d["measurements"])
    return {
        "name": d["scenario"],
        "seed": d["seed"],
        "n_rounds": d["n_rounds"],
        "made": int(m.get("deals_made", 0)),
        "m": m,
    }


def _pctf(x) -> str:
    return f"{100 * float(x):.0f}%"


def render(rows: list[dict]) -> str:
    cols = " | ".join(LABEL.get(r["name"], r["name"]) for r in rows)
    sep = "|".join(["---"] * (len(rows) + 1))
    seeds = ", ".join(f"`{r['name']}` seed {r['seed']}" for r in rows)

    def line(label, fn):
        return f"| {label} | " + " | ".join(fn(r) for r in rows) + " |"

    def rate(key):
        return lambda r: _pctf(r["m"].get(key, 0))

    L = [
        "# promises — four-way comparison (ratio-based)",
        "",
        f"{seeds} · {rows[0]['n_rounds']} rounds each. One seed — direction, not effect size.",
        "",
        "All comparison metrics are ratios in [0,1], so arms are comparable regardless of "
        "deal count. Every number is mechanical (LLM extracts the promised round + a verified "
        "quote; the verdict is arithmetic) and reproducible via `rescore.py`.",
        "",
        "## Promise distribution (share of all deals — supply-independent)",
        "",
        f"| | {cols} |",
        f"|{sep}|",
        line("**vague rate**", lambda r: f"**{_pctf(r['m'].get('vague_rate', 0))}**"),
        line("concrete rate", rate("concrete_rate")),
        line("true (on-time) rate", rate("true_rate")),
        line("false rate", rate("false_rate")),
        line("  · false-late", rate("false_late_rate")),
        line("  · false-never", rate("false_never_rate")),
        "",
        "## Honesty among sellers who committed to a round (supply-independent)",
        "",
        f"| | {cols} |",
        f"|{sep}|",
        line("**kept-of-concrete**", lambda r: f"**{_pctf(r['m'].get('kept_of_concrete', 0))}**"),
        line("broken-of-concrete", rate("broken_of_concrete")),
        "",
        "## Regulation intensity",
        "",
        f"| | {cols} |",
        f"|{sep}|",
        line("voided rate", rate("voided_rate")),
        line("lawyer-block rate", lambda r: _pctf(r["m"].get("lawyer_block_rate", 0))
             if r["m"].get("lawyer_block_rate") else "—"),
        "",
        "## Volume & delivery (context — delivered/deal is SUPPLY-BOUND, not a regime metric)",
        "",
        f"| | {cols} |",
        f"|{sep}|",
        line("deals made", lambda r: str(r["made"])),
        line("delivered / deal (supply-bound)", rate("delivered_per_deal")),
    ]
    return "\n".join(L) + "\n"


def main() -> None:
    if len(sys.argv) >= 3:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        paths = [p for p in (newest(n) for n in ORDER) if p]
        if len(paths) < 2:
            raise SystemExit("need at least two arm results in results/, or pass files explicitly")
    rows = [load(p) for p in paths]
    rows.sort(key=lambda r: ORDER.index(r["name"]) if r["name"] in ORDER else 99)
    md = render(rows)
    out = RESULTS_DIR / "compare_variants.md"
    out.write_text(md)
    print(md)
    print("(" + "  ·  ".join(p.name for p in paths) + f")\nSaved: {out}")


if __name__ == "__main__":
    main()
