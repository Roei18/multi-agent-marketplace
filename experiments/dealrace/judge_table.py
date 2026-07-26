"""Re-judge a saved dealrace run and emit a decision / explanation / quotes table.

Reads the transcripts already stored in a result JSON, re-runs the third-party
judge (which now returns a one-line reason and verbatim log quotes), verifies each
quote actually appears in the transcript, and writes a Markdown table beside the
result. No game is replayed — only the judge runs, one call per closed deal.

    python -m experiments.dealrace.judge_table                      # newest result
    python -m experiments.dealrace.judge_table <path-to-result.json>
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv()

from experiments.dealrace.agents import judge_deal
from experiments.dealrace.market import quote_in_transcript

RESULTS_DIR = Path(__file__).parent / "results"


def transcript_of(deal: dict, data: dict) -> tuple[str, str, str]:
    """Return (plain transcript, seller name, buyer name) for a deal."""
    snames = {s["id"]: s["name"] for s in data["sellers"]}
    bnames = {b["id"]: b["name"] for b in data["buyers"]}
    sname, bname = snames[deal["seller"]], bnames[deal["buyer"]]
    conv = next(
        (n for rec in data["rounds"] for n in rec["negotiations"]
         if n["closed"] and n["buyer"] == deal["buyer"] and n["seller"] == deal["seller"]
         and n["round"] == deal["closed_round"]),
        None,
    )
    if conv is None:
        return "", sname, bname
    lines = []
    for m in conv["messages"]:
        who = sname if m["speaker"] == deal["seller"] else bname
        tag = "  [declared DEAL]" if m["declare_deal"] else ""
        lines.append(f"{who}: {m['message']}{tag}")
    return "\n".join(lines), sname, bname


def outcome_of(deal: dict) -> str:
    if deal["honored_round"] >= 0:
        return f"The goods were handed over in round {deal['honored_round']}."
    if deal["dead"]:
        return ("The seller was eliminated while still owing these goods; they were never "
                "delivered.")
    return "The goods were never handed over by the end of the game."


async def rejudge(data: dict) -> list[dict]:
    deals = data["deals"]
    transcripts = {d["id"]: transcript_of(d, data) for d in deals}

    async def one(d: dict) -> dict:
        transcript, sname, bname = transcripts[d["id"]]
        res = await judge_deal(transcript=transcript, outcome=outcome_of(d))
        lab = res.label.strip().lower()
        lab = lab if lab in ("true", "false", "vague") else "vague"
        quotes = list(res.quotes)
        verified = [quote_in_transcript(q, transcript) for q in quotes]
        return {
            "id": d["id"], "seller": sname, "buyer": bname,
            "closed_round": d["closed_round"],
            "delivered": "yes" if d["honored_round"] >= 0
            else ("killed" if d["dead"] else "no"),
            "label": lab, "reason": res.reason,
            "quotes": quotes, "verified": verified,
        }

    return await asyncio.gather(*(one(d) for d in deals))


def render_md(data: dict, rows: list[dict]) -> str:
    from collections import Counter
    c = Counter(r["label"] for r in rows)
    total_q = sum(len(r["quotes"]) for r in rows)
    bad_q = sum(1 for r in rows for v in r["verified"] if not v)

    out = [
        f"# dealrace — judge decisions with evidence",
        "",
        f"Run: `{data['scenario']}` seed {data['seed']} · {len(rows)} deals · "
        f"true **{c['true']}** / false **{c['false']}** / vague **{c['vague']}**",
        "",
        f"Quotes are copied verbatim by the judge from each conversation and then checked "
        f"against the transcript: **{total_q - bad_q}/{total_q} verified present**"
        + (f" ⚠️ {bad_q} not found (flagged below)" if bad_q else "") + ".",
        "",
        "| # | Seller → Buyer | Rd | Delivered | Label | Why | Evidence (verbatim) |",
        "|---|---|---|---|---|---|---|",
    ]
    order = {"false": 0, "vague": 1, "true": 2}
    for r in sorted(rows, key=lambda x: (order.get(x["label"], 3), -x["closed_round"])):
        ev = "<br>".join(
            f"“{q}”{'' if v else ' ⚠️not in log'}"
            for q, v in zip(r["quotes"], r["verified"])
        ) or "—"
        why = r["reason"].replace("|", "\\|")
        ev = ev.replace("|", "\\|")
        out.append(
            f"| {r['id']} | {r['seller']} → {r['buyer']} | {r['closed_round']} | "
            f"{r['delivered']} | **{r['label']}** | {why} | {ev} |"
        )
    return "\n".join(out) + "\n"


async def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg:
        path = Path(arg)
    else:
        results = sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        if not results:
            raise SystemExit("no result JSON found in results/")
        path = results[-1]
    data = json.loads(path.read_text())
    print(f"Re-judging {len(data['deals'])} deals from {path.name} …")

    rows = await rejudge(data)
    md = render_md(data, rows)
    out_path = path.with_name(path.stem + "_judge_table.md")
    out_path.write_text(md)
    print(md)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
