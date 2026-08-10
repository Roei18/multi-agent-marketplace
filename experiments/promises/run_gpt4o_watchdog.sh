#!/bin/bash
# Keeps the gpt-4o sweep going until all 24 runs are saved; survives auto-sleep
# (re-runs the resumable driver on wake). Launch detached:
#   cd <repo> && setsid nohup bash experiments/promises/run_gpt4o_watchdog.sh \
#      > experiments/promises/results/_gpt4o_sweep.log 2>&1 < /dev/null &
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1
R=experiments/promises/results
while true; do
  n=$(ls $R/*_gpt4o*.json 2>/dev/null | grep -vE "_s99_" | sed -E 's/_gpt4o.*//' | sort -u | wc -l)
  # 8 arm-seed combos x 3 p's would be 24 files, but arm_seed keys repeat across p;
  # count actual files instead:
  files=$(ls $R/*_gpt4o*.json 2>/dev/null | grep -vE "_s99_" | wc -l)
  if [ "$files" -ge 24 ]; then echo "[gpt4o] all 24 done $(date '+%m-%d %H:%M:%S')"; break; fi
  echo "[gpt4o] $files/24 done; (re)starting sweep $(date '+%m-%d %H:%M:%S')"
  bash "$REPO/experiments/promises/run_gpt4o_sweep.sh"
  sleep 30
done
