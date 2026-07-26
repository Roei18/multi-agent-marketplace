"""promises — a promise-market with a ground-truthable verdict.

A rebuild of dealrace whose measurement is sound by construction: an LLM only
*extracts* what a seller promised (delivery round + verbatim quote); the verdict
(true / false-late / false-never / vague) is pure arithmetic over the ground-truth
delivery log. See DESIGN.md.
"""
