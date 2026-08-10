#!/bin/bash
# Two single-seed probes with gpt-4o AGENTS (judge stays default, for comparable
# measurement). Seed 99, small scale (8 sellers x 4 buyers x 6 rounds) so they finish
# quickly and never collide with the main data (different dims + seed). Resumable: skips
# a probe whose file already exists.
#   Issue 3 (baseline):   do strong BUYERS explore?
#   Issue 4 (attributor): do strong SELLERS still over-promise under fines?
cd "/mnt/c/Users/roeib/OneDrive - mail.tau.ac.il/Research/MultiAgent/Error Attribution/multi-agent-marketplace" || exit 1
R=experiments/promises/results
M="openai/gpt-4o"
for scen in baseline attributor; do
  if ls $R/${scen}_s99_*.json >/dev/null 2>&1; then
    echo "skip $scen s99 (already done) $(date '+%m-%d %H:%M:%S')"; continue
  fi
  echo "=== PROBE $scen s99 (gpt-4o agents) START $(date '+%m-%d %H:%M:%S') ==="
  .venv/bin/python -m experiments.promises.run --scenario "$scen" \
    --sellers 8 --buyers 4 --rounds 6 --seed 99 \
    --buyer-model "$M" --seller-model "$M" --quiet
  echo "=== PROBE $scen s99 END $(date '+%m-%d %H:%M:%S') ==="
done
echo "PROBES DONE $(date '+%m-%d %H:%M:%S')"
