#!/bin/bash
# Watchdog for the p=0.5 sweep: keeps the resumable driver alive until all 12
# (arm x seed) runs are saved. Survives an auto-sleep -- on wake it notices the
# driver exited (or a run crashed) and restarts it, skipping finished runs.
# Only a full shutdown/hibernate (WSL gone) needs a manual relaunch of THIS script:
#   cd <repo> && setsid nohup bash experiments/promises/results/_p05_watchdog.sh \
#      > experiments/promises/results/_p05_sweep.log 2>&1 < /dev/null &
REPO="/mnt/c/Users/roeib/OneDrive - mail.tau.ac.il/Research/MultiAgent/Error Attribution/multi-agent-marketplace"
cd "$REPO" || exit 1
R=experiments/promises/results
while true; do
  n=$(ls $R/*_p50_*.json 2>/dev/null | sed 's/_p50.*//' | sort -u | wc -l)
  if [ "$n" -ge 12 ]; then echo "[watchdog] all 12 done $(date '+%m-%d %H:%M:%S')"; break; fi
  echo "[watchdog] $n/12 done; (re)starting driver $(date '+%m-%d %H:%M:%S')"
  bash $R/_p05_driver.sh
  sleep 30
done
