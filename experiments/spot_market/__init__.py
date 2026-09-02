"""spot_market — an instant-delivery variant of promises, built for equilibrium analysis.

No forward promises: a deal struck this round is for THIS round's stock only, and
resolves before the round ends. Every seller draws a fresh single-good-or-nothing
Bernoulli(p_s) every round (no accumulation, no memory of past draws). The verdict is
pure arithmetic (declare_deal x that seller's pre-drawn outcome) — no LLM judge or
promise-extraction step anywhere, unlike promises' free-text arms. Buyers act one at a
time in a fixed round-robin (buyer 1..M, repeated for K cycles = K*M total rounds), so
every round has the identical shape — a deliberately stationary transition rule, built
so a long horizon can be analyzed for equilibria rather than just measured empirically.
"""
