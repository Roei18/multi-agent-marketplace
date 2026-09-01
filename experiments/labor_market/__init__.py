"""labor_market — a scored VCG procurement auction with two reputation ablations.

Each round a principal picks one of N labor agents to do a fully abstract task
(one of K hidden types), scores every bidder as p_i(t) - alpha*b_i(t) using an
LLM-estimated success probability, and pays the winner the VCG critical-bid
price. Agents carry a persistent, self-authored strategy note across rounds and
are told why they did or didn't win. Three scenarios (baseline,
error_attribution, positive_market) differ only in what a FAILED winner suffers.
"""
