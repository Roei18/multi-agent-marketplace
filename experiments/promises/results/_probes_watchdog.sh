#!/bin/bash
# Keeps the two gpt-4o probes going until both are saved; survives auto-sleep (on wake
# it restarts the driver, skipping any finished probe). Relaunch after a full shutdown:
#   cd <repo> && setsid nohup bash experiments/promises/results/_probes_watchdog.sh \
#      > experiments/promises/results/_probes.log 2>&1 < /dev/null &
cd "/mnt/c/Users/roeib/OneDrive - mail.tau.ac.il/Research/MultiAgent/Error Attribution/multi-agent-marketplace" || exit 1
R=experiments/promises/results
while true; do
  n=$(ls $R/baseline_s99_*.json $R/attributor_s99_*.json 2>/dev/null | sed 's/_s99.*//' | sort -u | wc -l)
  if [ "$n" -ge 2 ]; then echo "[probes] both done $(date '+%m-%d %H:%M:%S')"; break; fi
  echo "[probes] $n/2 done; (re)starting driver $(date '+%m-%d %H:%M:%S')"
  bash $R/_probes_driver.sh
  sleep 30
done
