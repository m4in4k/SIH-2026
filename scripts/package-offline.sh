#!/usr/bin/env bash
set -Eeuo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
version="${1:-0.2.0}"
image_name="sentinel-tool:$version"
output_dir="${2:-$project_dir/dist-offline/Sentinel-Tool-$version-linux-x86_64}"
stage_dir="$(mktemp -d)"
trap 'rm -rf -- "$stage_dir"' EXIT

command -v docker >/dev/null 2>&1 || { printf 'Docker is required.\n' >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { printf 'sha256sum is required.\n' >&2; exit 1; }

cd "$project_dir"
docker build --tag "$image_name" .
docker pull mongo:8.0.29

mkdir -p "$stage_dir/scripts" "$stage_dir/deploy" "$stage_dir/frontend/public" "$stage_dir/geoip"
cp compose.offline.yaml "$stage_dir/"
cp deploy/mongo-init.js "$stage_dir/deploy/"
cp scripts/launch-sentinel.sh scripts/stop-sentinel.sh scripts/install-desktop-launcher.sh "$stage_dir/scripts/"
cp frontend/public/og.png "$stage_dir/frontend/public/"
cp OFFLINE.md "$stage_dir/"
printf 'SENTINEL_IMAGE=%s\n' "$image_name" > "$stage_dir/release.env"

if compgen -G "$project_dir/geoip/*.mmdb" >/dev/null; then
  cp "$project_dir"/geoip/*.mmdb "$stage_dir/geoip/"
fi
if [[ -f "$project_dir/geoip/README.md" ]]; then
  cp "$project_dir/geoip/README.md" "$stage_dir/geoip/"
fi

docker save --output "$stage_dir/sentinel-offline-images.tar" "$image_name" mongo:8.0.29
(
  cd "$stage_dir"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

mkdir -p "$(dirname -- "$output_dir")"
[[ ! -e "$output_dir" ]] || { printf 'Output already exists: %s\nChoose a new version or destination.\n' "$output_dir" >&2; exit 1; }
mv "$stage_dir" "$output_dir"
trap - EXIT
printf 'Offline release created at %s\n' "$output_dir"
