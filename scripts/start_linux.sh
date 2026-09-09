#!/usr/bin/env bash
set -Eeuo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
[[ "$(uname -s)" == "Linux" ]] || { echo 'This launcher is for Linux.' >&2; exit 1; }
[[ -x .venv/bin/python && -d frontend/node_modules ]] || { echo 'Run ./scripts/setup_linux.sh first.' >&2; exit 1; }
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
mkdir -p .runtime/logs .runtime/pids .runtime/mongo-data
pid_dir="$project_dir/.runtime/pids"
log_dir="$project_dir/.runtime/logs"
start_one() { local name="$1"; shift; if [[ -f "$pid_dir/$name.pid" ]] && kill -0 "$(<"$pid_dir/$name.pid")" 2>/dev/null; then return; fi; nohup "$@" >"$log_dir/$name.log" 2>&1 & echo $! >"$pid_dir/$name.pid"; }
if ! mongosh --quiet --eval 'db.adminCommand({ping:1}).ok' mongodb://127.0.0.1:27017 >/dev/null 2>&1; then
  start_one mongo mongod --dbpath "$project_dir/.runtime/mongo-data" --bind_ip 127.0.0.1 --port 27017
fi
mongo_ready=false
for attempt in {1..30}; do
  if mongosh --quiet --eval 'db.adminCommand({ping:1}).ok' mongodb://127.0.0.1:27017 >/dev/null 2>&1; then
    mongo_ready=true
    break
  fi
  sleep 1
done
$mongo_ready || { echo 'MongoDB did not become ready within 30 seconds. See .runtime/logs/mongo.log.' >&2; exit 1; }
export PYTHONPATH="$project_dir/backend"
export MONGO_URI="${MONGO_URI:-mongodb://127.0.0.1:27017}"
export MONGO_DB="${MONGO_DB:-bitcoin_sentinel}"
export COOKIE_SECURE="${COOKIE_SECURE:-false}"
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-http://127.0.0.1:5173,http://localhost:5173}"
case ",$ALLOWED_ORIGINS," in *,http://127.0.0.1:5173,*) ;; *) export ALLOWED_ORIGINS="$ALLOWED_ORIGINS,http://127.0.0.1:5173" ;; esac
case ",$ALLOWED_ORIGINS," in *,http://localhost:5173,*) ;; *) export ALLOWED_ORIGINS="$ALLOWED_ORIGINS,http://localhost:5173" ;; esac
export GEOIP_COUNTRY_DB="${GEOIP_COUNTRY_DB:-$project_dir/geoip/GeoLite2-Country.mmdb}"
export GEOIP_ASN_DB="${GEOIP_ASN_DB:-$project_dir/geoip/GeoLite2-ASN.mmdb}"
start_one worker .venv/bin/python -m app.worker
start_one api .venv/bin/uvicorn app.main:app --host "${BIND_ADDRESS:-127.0.0.1}" --port "${PORT:-8000}"
start_one frontend frontend/node_modules/.bin/vite --host 127.0.0.1 --port 5173
printf 'Sentinel Tool running at http://127.0.0.1:5173 (API http://127.0.0.1:%s)\n' "${PORT:-8000}"
