"""Dump every VAGUE-verdict deal, per arm, with full evidence for hand-verification.

For each arm it writes results/vague_audit/<arm>.md listing, per vague deal: the
judge's verbatim quote (+ whether it was found in the log), the judge's reasoning,
and the FULL speaker-labelled transcript. Uses the newest *_judged.json per arm if
present, else the newest plain run.

    python -m experiments.promises.vague_dump
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
OUT_DIR = RESULTS_DIR / "vague_audit"
ARMS = ["baseline", "attributor", "lawyer_attributor", "contract_attributor"]


def newest(arm: str) -> Path | None:
    # Newest by time overall — fresh runs carry verdicts inline (the vagueness judge
    # runs during the run), so we always want the most recent run of the arm.
    hits = sorted(RESULTS_DIR.glob(f"{arm}_s*.json"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def dump_arm(arm: str) -> str:
    p = newest(arm)
    if p is None:
        return f"{arm}: no results found"
    r = RunResult.model_validate(json.loads(p.read_text()))
    snames = {s.id: s.name for s in r.sellers}
    bnames = {b.id: b.name for b in r.buyers}
    conv_by_key = {(n.round, n.buyer, n.seller): n
                   for rec in r.rounds for n in rec.negotiations if n.closed}
    vague = [d for d in r.deals if d.verdict == "vague"]

    L = [f"# Vague verdicts — {arm}",
         "",
         f"Source: `{p.name}`  ·  seed {r.seed}  ·  {r.n_rounds} rounds",
         f"**{len(vague)} vague of {len(r.deals)} deals "
         f"({round(100*len(vague)/(len(r.deals) or 1))}%)**",
         "",
         "Each entry: the judge's verbatim quote (verified = the quote was found in the "
         "transcript), the judge's reasoning, and the full conversation. Verify freely.",
         ""]
    for d in vague:
        L += ["---", "",
              f"## Deal #{d.id} — {snames.get(d.seller, d.seller)} ({d.seller}) "
              f"→ {bnames.get(d.buyer, d.buyer)} ({d.buyer}), closed round {d.closed_round}",
              "",
              f"- **judge quote:** {d.promise_quote!r}",
              f"- **quote verified in log:** {d.promise_quote_verified}",
              f"- **judge reasoning:** {d.extract_reasoning}",
              "",
              "**Full conversation:**", "```"]
        n = conv_by_key.get((d.closed_round, d.buyer, d.seller))
        if n:
            for m in n.messages:
                who = ("LAWYER" if m.speaker not in (d.seller, d.buyer)
                       else (snames.get(d.seller, d.seller) if m.speaker == d.seller
                             else bnames.get(d.buyer, d.buyer)))
                tag = ""
                if m.declare_deal:
                    tag = "  [declared DEAL]"
                elif m.proposed_contract:
                    tag = f"  [{m.proposed_contract}]"
                elif m.accepted_contract:
                    tag = "  [ACCEPTED]"
                L.append(f"{who}: {m.message}{tag}")
        else:
            L.append("(transcript not found)")
        L += ["```", ""]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{arm}.md"
    out.write_text("\n".join(L) + "\n")
    return f"{arm}: {len(vague)} vague of {len(r.deals)} -> {out}"


def main() -> None:
    for arm in ARMS:
        print(dump_arm(arm))


if __name__ == "__main__":
    main()
