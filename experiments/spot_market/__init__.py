"""spot_market — an instant-delivery variant of promises, built for equilibrium analysis.

No forward promises: a deal struck this round is for THIS round's stock only, and
resolves the instant it closes. Each seller draws a fresh single-good-or-nothing
Bernoulli(p_s) at most once per cycle — not pre-drawn at the cycle's start, but the
moment that seller gets its FIRST closed deal that cycle; any later closer with the
same seller that cycle is automatically fooled, no draw needed, and a seller nobody
closes with never draws at all. The verdict is pure arithmetic (declare_deal x that
seller's draw, resolved live) — no LLM judge or promise-extraction step anywhere,
unlike promises' free-text arms. Buyers act one at a time in a fixed round-robin
(buyer 1..M, repeated for K cycles = K*M total rounds), so every round has the
identical shape — a deliberately stationary transition rule, built so a long horizon
can be analyzed for equilibria rather than just measured empirically.
"""
