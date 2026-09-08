#!/usr/bin/env bash
set -Eeuo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
applications_dir="${XDG_DATA_HOME:-${HOME}/.local/share}/applications"
desktop_dir="${XDG_DESKTOP_DIR:-${HOME}/Desktop}"
launcher="$applications_dir/sentinel-tool.desktop"
icon="$project_dir/frontend/public/og.png"

mkdir -p "$applications_dir"
chmod +x "$project_dir/scripts/launch-sentinel.sh" "$project_dir/scripts/stop-sentinel.sh"

{
  printf '%s\n' '[Desktop Entry]'
  printf '%s\n' 'Type=Application'
  printf '%s\n' 'Name=Sentinel Tool'
  printf '%s\n' 'Comment=Offline Bitcoin investigation workspace'
  printf 'Exec=%q\n' "$project_dir/scripts/launch-sentinel.sh"
  printf 'Icon=%s\n' "$icon"
  printf '%s\n' 'Terminal=false'
  printf '%s\n' 'Categories=Utility;Security;'
  printf '%s\n' 'StartupNotify=true'
} > "$launcher"
chmod +x "$launcher"

if [[ -d "$desktop_dir" ]]; then
  cp "$launcher" "$desktop_dir/Sentinel Tool.desktop"
  chmod +x "$desktop_dir/Sentinel Tool.desktop"
fi

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$applications_dir" >/dev/null 2>&1 || true
printf 'Sentinel Tool is installed. Open it from the applications menu or desktop.\n'

