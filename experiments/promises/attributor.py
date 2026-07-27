"""The attributor (arm 2) — a mechanical oracle that voids false promises.

A deal is voided iff its verdict is `false-late` or `false-never`: the seller
committed to a specific delivery round and did not deliver by it. `vague` deals
(no time committed) and `true` deals (delivered on time) are never voided. Because
the verdict is already ground truth (arithmetic over the delivery log), this
attribution is exact by construction — no LLM, nothing to infer.

A later *inference* attributor (an LLM guessing breaches from the logs without the
delivery ground truth) would plug in here and be scored against this oracle.
"""

from __future__ import annotations

from .models import Deal

FALSE_VERDICTS = ("false-late", "false-never")


def void_false_promises(deals: list[Deal]) -> None:
    """Set `fined` on every deal whose promise was broken. Mutates in place."""
    for d in deals:
        d.fined = d.verdict in FALSE_VERDICTS


def score_sellers(deals: list[Deal]) -> dict[str, dict]:
    """Per seller: deals closed, how many were voided, and net = closed − voided."""
    out: dict[str, dict] = {}
    for d in deals:
        s = out.setdefault(d.seller, {"closed": 0, "voided": 0, "net": 0})
        s["closed"] += 1
        if d.fined:
            s["voided"] += 1
    for s in out.values():
        s["net"] = s["closed"] - s["voided"]
    return out
