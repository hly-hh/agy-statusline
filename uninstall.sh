#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${AGY_STATUSLINE_DIR:-$HOME/.antigravity}"
SETTINGS_FILE="${AGY_SETTINGS_FILE:-$HOME/.gemini/antigravity-cli/settings.json}"
BACKUP_DIR="$INSTALL_DIR/backups"

if [[ -f "$SETTINGS_FILE" ]]; then
  mkdir -p "$BACKUP_DIR"
  ts="$(date +%Y%m%d_%H%M%S)"
  cp "$SETTINGS_FILE" "$BACKUP_DIR/settings.json.$ts.bak"

  python3 - "$SETTINGS_FILE" "$INSTALL_DIR/status.py" <<'PY'
import json
import os
import sys

settings_file, status_script = sys.argv[1], sys.argv[2]

with open(settings_file, "r", encoding="utf-8") as f:
    data = json.load(f)

if isinstance(data, dict):
    sl = data.get("statusLine")
    if isinstance(sl, dict) and status_script in str(sl.get("command", "")):
        data.pop("statusLine", None)
        tmp_file = f"{settings_file}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_file, settings_file)
PY
fi

rm -f "$INSTALL_DIR/status.py"

echo "Uninstalled agy-statusline. Restart agy or run /statusline off to take effect."
