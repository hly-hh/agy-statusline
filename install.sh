#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${AGY_STATUSLINE_DIR:-$HOME/.antigravity}"
SETTINGS_FILE="${AGY_SETTINGS_FILE:-$HOME/.gemini/antigravity-cli/settings.json}"
BACKUP_DIR="$INSTALL_DIR/backups"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$INSTALL_DIR" "$BACKUP_DIR" "$(dirname "$SETTINGS_FILE")"

ts="$(date +%Y%m%d_%H%M%S)"

if [[ -f "$INSTALL_DIR/status.py" ]]; then
  cp "$INSTALL_DIR/status.py" "$BACKUP_DIR/status.py.$ts.bak"
fi

if [[ -f "$SETTINGS_FILE" ]]; then
  cp "$SETTINGS_FILE" "$BACKUP_DIR/settings.json.$ts.bak"
fi

cp "$SCRIPT_DIR/status.py" "$INSTALL_DIR/status.py"
chmod +x "$INSTALL_DIR/status.py"

python3 - "$SETTINGS_FILE" "$INSTALL_DIR/status.py" <<'PY'
import json
import os
import sys

settings_file, status_script = sys.argv[1], sys.argv[2]

if os.path.exists(settings_file):
    with open(settings_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"Expected JSON object in {settings_file}")
else:
    data = {}

data["statusLine"] = {
    "type": "command",
    "command": f"python3 {status_script}",
}

tmp_file = f"{settings_file}.tmp"
with open(tmp_file, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
os.replace(tmp_file, settings_file)
PY

cat <<EOF
Installed agy-statusline successfully.

  Script:   $INSTALL_DIR/status.py
  Settings: $SETTINGS_FILE
  Backups:  $BACKUP_DIR

Reload inside agy with:
  /statusline off  ->  /statusline on
Or restart your agy session.
EOF
