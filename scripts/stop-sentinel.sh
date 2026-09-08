#!/usr/bin/env bash
set -Eeuo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
state_root="${XDG_STATE_HOME:-${HOME}/.local/state}/sentinel-tool"
runtime_env="$state_root/runtime.env"

if [[ ! -f "$runtime_env" ]]; then
  printf 'Sentinel Tool has not been initialized.\n'
  exit 0
fi

cd "$project_dir"
docker compose --env-file "$runtime_env" -f compose.offline.yaml stop
printf 'Sentinel Tool stopped. Your accounts, cases, and results remain saved.\n'

