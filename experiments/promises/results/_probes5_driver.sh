#!/bin/bash
# Same two probes as gpt-4o, but with gpt-5 agents (one tier above). Tagged 'gpt5',
# seed 99, 8x4x6. Judge stays default for comparable measurement. Resumable.
cd "/mnt/c/Users/roeib/OneDrive - mail.tau.ac.il/Research/MultiAgent/Error Attribution/multi-agent-marketplace" || exit 1
R=experiments/promises/results
M="openai/gpt-5"
for scen in baseline attributor; do
  if ls $R/${scen}_s99_gpt5_*.json >/dev/null 2>&1; then
    echo "skip $scen gpt5 (already done) $(date '+%m-%d %H:%M:%S')"; continue
  fi
  echo "=== PROBE $scen gpt5 START $(date '+%m-%d %H:%M:%S') ==="
  .venv/bin/python -m experiments.promises.run --scenario "$scen" \
    --sellers 8 --buyers 4 --rounds 6 --seed 99 --tag gpt5 \
    --buyer-model "$M" --seller-model "$M" --quiet
  echo "=== PROBE $scen gpt5 END $(date '+%m-%d %H:%M:%S') ==="
done
echo "GPT5 PROBES DONE $(date '+%m-%d %H:%M:%S')"
