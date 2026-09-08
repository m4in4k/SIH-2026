#!/usr/bin/env bash
set -Eeuo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
state_root="${XDG_STATE_HOME:-${HOME}/.local/state}/sentinel-tool"
runtime_env="$state_root/runtime.env"
log_file="$state_root/launcher.log"
compose_file="$project_dir/compose.offline.yaml"
app_url="http://127.0.0.1:8080/dashboard?auth=signin"

mkdir -p "$state_root"
touch "$log_file"
chmod 700 "$state_root"
chmod 600 "$log_file"
exec > >(tee -a "$log_file") 2>&1

show_error() {
  local message="$1"
  if command -v zenity >/dev/null 2>&1; then
    zenity --error --title="Sentinel Tool" --text="$message" || true
  fi
  printf 'Sentinel Tool: %s\n' "$message" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || show_error "Docker Engine is required. Install it once, then open Sentinel Tool again."
docker compose version >/dev/null 2>&1 || show_error "The Docker Compose plugin is required."
docker info >/dev/null 2>&1 || show_error "Docker is not running or this account cannot access it."
[[ -f "$compose_file" ]] || show_error "The offline application files are incomplete."

if [[ ! -f "$runtime_env" ]]; then
  root_password="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  app_password="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
  image_name="sentinel-tool:0.2.0"
  if [[ -f "$project_dir/release.env" ]]; then
    configured_image="$(sed -n 's/^SENTINEL_IMAGE=//p' "$project_dir/release.env" | head -n 1)"
    [[ -n "$configured_image" ]] && image_name="$configured_image"
  fi
  umask 077
  {
    printf 'MONGO_ROOT_PASSWORD=%s\n' "$root_password"
    printf 'MONGO_APP_PASSWORD=%s\n' "$app_password"
    printf 'SENTINEL_IMAGE=%s\n' "$image_name"
    printf 'PORT=8080\n'
  } > "$runtime_env"
fi

set -a
# shellcheck disable=SC1090
source "$runtime_env"
set +a

if ! docker image inspect "$SENTINEL_IMAGE" >/dev/null 2>&1 || ! docker image inspect mongo:8.0.29 >/dev/null 2>&1; then
  archive="$project_dir/sentinel-offline-images.tar"
  [[ -f "$archive" ]] || show_error "Bundled application images were not found. Use the complete Sentinel offline release."
  printf 'Loading the offline application for first use…\n'
  docker load --input "$archive" || show_error "The bundled application images could not be loaded."
fi

cd "$project_dir"
printf 'Starting Sentinel Tool…\n'
docker compose --env-file "$runtime_env" -f "$compose_file" up -d --no-build --pull never || \
  show_error "Sentinel services could not start. See $log_file for details."

healthy=false
for _ in $(seq 1 45); do
  if docker compose --env-file "$runtime_env" -f "$compose_file" exec -T api \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" \
    >/dev/null 2>&1; then
    healthy=true
    break
  fi
  sleep 2
done

[[ "$healthy" == true ]] || show_error "Sentinel did not become ready. See $log_file for details."

printf 'Sentinel Tool is ready at %s\n' "$app_url"
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$app_url" >/dev/null 2>&1 &
elif command -v gio >/dev/null 2>&1; then
  gio open "$app_url" >/dev/null 2>&1 &
fi

