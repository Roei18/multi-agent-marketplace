#!/bin/bash
# Keeps the gpt-4o sweep going until all 12 (seed-0) runs are saved; survives auto-sleep
# (re-runs the resumable driver on wake). Launch detached:
#   cd <repo> && setsid nohup bash experiments/promises/run_gpt4o_watchdog.sh \
#      > experiments/promises/results/_gpt4o_sweep.log 2>&1 < /dev/null &
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1
R=experiments/promises/results
while true; do
  # seed-0 gpt-4o files only (exclude the s99 probes); 3 p's x 4 arms = 12
  files=$(ls $R/*_s0_gpt4o*.json 2>/dev/null | wc -l)
  if [ "$files" -ge 12 ]; then echo "[gpt4o] all 12 (seed 0) done $(date '+%m-%d %H:%M:%S')"; break; fi
  echo "[gpt4o] $files/12 done; (re)starting sweep $(date '+%m-%d %H:%M:%S')"
  bash "$REPO/experiments/promises/run_gpt4o_sweep.sh"
  sleep 30
done
