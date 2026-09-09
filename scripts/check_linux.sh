#!/usr/bin/env bash
set -Eeuo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
api_url="http://${BIND_ADDRESS:-127.0.0.1}:${PORT:-8000}/api/health"
command -v curl >/dev/null || { echo 'curl is required for the health check.' >&2; exit 1; }
curl --fail --silent --show-error "$api_url"
printf '\nSentinel Tool API is healthy. Frontend: http://127.0.0.1:5173\n'
