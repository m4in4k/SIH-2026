#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Create .venv and install backend requirements first; see README.md.' >&2
  exit 1
fi
if [[ ! -f frontend/dist/index.html ]]; then
  echo 'Build the React frontend first; see README.md.' >&2
  exit 1
fi
export PYTHONPATH="$project_dir/backend"
export MONGO_URI="${MONGO_URI:-mongodb://127.0.0.1:27017}"
export MONGO_DB="${MONGO_DB:-bitcoin_sentinel}"
.venv/bin/python -m app.worker &
worker_pid=$!
cleanup() { kill "$worker_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
