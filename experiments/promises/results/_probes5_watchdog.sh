#!/bin/bash
# Keeps the two gpt-5 probes going until both saved; survives auto-sleep (auto-resumes
# on wake). Relaunch after full shutdown:
#   cd <repo> && setsid nohup bash experiments/promises/results/_probes5_watchdog.sh \
#      > experiments/promises/results/_probes5.log 2>&1 < /dev/null &
cd "/mnt/c/Users/roeib/OneDrive - mail.tau.ac.il/Research/MultiAgent/Error Attribution/multi-agent-marketplace" || exit 1
R=experiments/promises/results
while true; do
  n=$(ls $R/baseline_s99_gpt5_*.json $R/attributor_s99_gpt5_*.json 2>/dev/null | sed 's/_s99.*//' | sort -u | wc -l)
  if [ "$n" -ge 2 ]; then echo "[probes5] both done $(date '+%m-%d %H:%M:%S')"; break; fi
  echo "[probes5] $n/2 done; (re)starting driver $(date '+%m-%d %H:%M:%S')"
  bash $R/_probes5_driver.sh
  sleep 30
done
