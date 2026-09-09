#!/usr/bin/env bash
set -Eeuo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
pid_dir="$project_dir/.runtime/pids"
for name in frontend api worker mongo; do
  pid_file="$pid_dir/$name.pid"
  if [[ -f "$pid_file" ]]; then
    pid="$(<"$pid_file")"
    kill "$pid" 2>/dev/null || true
    rm -f "$pid_file"
  fi
done
printf 'Sentinel Tool stopped. Data remains in .runtime/mongo-data.\n'
