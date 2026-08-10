#!/bin/bash
# gpt-4o sweep: 3 supply levels x SEED 0 x 4 arms = 12 runs at 8x16x12.
# EVERYTHING runs on gpt-4o (agents AND judge) via LLM_MODEL; files tagged 'gpt4o'.
# The 4 arms of each (seed,p) run in PARALLEL (each process is concurrency=1, so that's
# only 4 concurrent gpt-4o calls -- safe, and ~4x faster than serial). Seed-outer, so
# seed 0 finishes all three p's first (a full 3-point figure at ~half the total time).
# Portable + resumable: repo root from script location; already-saved runs are skipped.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1
PY="$REPO/.venv/bin/python"
export LLM_MODEL="openai/gpt-4o"
R=experiments/promises/results
for seed in 0; do
  for p in 0.6 0.5 0.4; do
    case "$p" in
      0.6) g="_[0-9]";; 0.5) g="_p50_";; 0.4) g="_p40_";;
    esac
    for arm in baseline attributor lawyer_attributor contract_attributor; do
      if ls $R/${arm}_s${seed}_gpt4o${g}*.json >/dev/null 2>&1; then
        echo "skip $arm s$seed p$p (done)"; continue
      fi
      echo "=== gpt4o $arm s$seed p$p START $(date '+%m-%d %H:%M:%S') ==="
      "$PY" -m experiments.promises.run --scenario "$arm" \
        --sellers 8 --buyers 16 --rounds 12 --p "$p" --seed "$seed" --tag gpt4o --quiet \
        > "$R/_gpt4o_${arm}_s${seed}_p${p}.log" 2>&1 &
    done
    wait   # let this (seed,p) wave of arms finish before the next
    echo "=== gpt4o wave seed $seed p $p DONE $(date '+%m-%d %H:%M:%S') ==="
  done
done
echo "GPT4O SWEEP DONE $(date '+%m-%d %H:%M:%S')"
