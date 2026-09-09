#!/usr/bin/env bash
set -Eeuo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
pid_dir="$project_dir/.runtime/pids"
for name in frontend api worker mongo; do
  pid_file="$pid_dir/$name.pid"
  if [[ -f "$pid_file" ]]; then
    pid="$(<"$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      for _ in {1..10}; do
        if ! kill -0 "$pid" 2>/dev/null; then break; fi
        sleep 0.3
      done
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$pid_file"
  fi
done
printf 'Sentinel Tool stopped. Data remains in .runtime/mongo-data.\n'
