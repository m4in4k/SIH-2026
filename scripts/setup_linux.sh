#!/usr/bin/env bash
set -Eeuo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
[[ "$(uname -s)" == "Linux" ]] || { echo 'This installer is for Linux.' >&2; exit 1; }
python_bin="${PYTHON_BIN:-python3}"
node_bin="${NODE_BIN:-node}"
command -v "$python_bin" >/dev/null || { echo 'Python 3.12+ is required.' >&2; exit 1; }
"$python_bin" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit('Python 3.12+ is required.')
PY
command -v "$node_bin" >/dev/null || { echo 'Node.js 20+ is required.' >&2; exit 1; }
"$node_bin" -e 'if (parseInt(process.versions.node) < 20) process.exit(1)' || { echo 'Node.js 20+ is required.' >&2; exit 1; }
if ! command -v pnpm >/dev/null; then
  if command -v corepack >/dev/null 2>&1; then
    corepack enable >/dev/null 2>&1 || true
  fi
fi
command -v pnpm >/dev/null || { echo 'pnpm is required (install with: npm install -g pnpm or curl -fsSL https://get.pnpm.io/install.sh | sh)' >&2; exit 1; }
command -v mongod >/dev/null || { echo 'MongoDB mongod is required.' >&2; exit 1; }
command -v mongosh >/dev/null || { echo 'MongoDB mongosh is required.' >&2; exit 1; }
[[ -f geoip/GeoLite2-Country.mmdb && -f geoip/GeoLite2-ASN.mmdb ]] || echo 'Warning: GeoIP databases are missing; enrichment will be unavailable.' >&2
"$python_bin" -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r backend/requirements.lock.txt || .venv/bin/python -m pip install -r backend/requirements.txt
pnpm --dir frontend install --frozen-lockfile --ignore-scripts || pnpm --dir frontend install --ignore-scripts
pnpm --dir frontend run build
mkdir -p .runtime/logs .runtime/pids .runtime/mongo-data
[[ -w .runtime/logs && -w .runtime/pids && -w .runtime/mongo-data ]] || { echo 'Runtime directories must be writable by the current user.' >&2; exit 1; }
[[ -f .env ]] || ( [[ -f .env.example ]] && cp .env.example .env )
cat <<'EOF'
Linux setup complete. Review .env, then run:
  ./scripts/start_linux.sh
EOF
