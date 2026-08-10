#!/bin/bash
# Resumable p=0.5 sweep: runs the 12 (arm x seed) combos, SKIPPING any already saved.
# Re-run this any time it dies (machine slept, etc.) -- it picks up where it left off.
#   Detached launch (survives closing the terminal / Claude Code):
#     cd <repo> && setsid nohup bash experiments/promises/results/_p05_driver.sh \
#        > experiments/promises/results/_p05_sweep.log 2>&1 < /dev/null &
cd "/mnt/c/Users/roeib/OneDrive - mail.tau.ac.il/Research/MultiAgent/Error Attribution/multi-agent-marketplace" || exit 1
for seed in 0 1 2; do
  for arm in baseline attributor lawyer_attributor contract_attributor; do
    if ls experiments/promises/results/${arm}_s${seed}_p50_*.json >/dev/null 2>&1; then
      echo "skip $arm s$seed (already done) $(date +%H:%M:%S)"; continue
    fi
    echo "=== p05 $arm s$seed START $(date '+%m-%d %H:%M:%S') ==="
    .venv/bin/python -m experiments.promises.run --scenario "$arm" \
        --sellers 8 --buyers 16 --rounds 12 --p 0.5 --seed "$seed" --quiet
    echo "=== p05 $arm s$seed END $(date '+%m-%d %H:%M:%S') ==="
  done
done
echo "P05 ALL DONE $(date '+%m-%d %H:%M:%S')"
