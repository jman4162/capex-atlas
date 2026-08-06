#!/usr/bin/env bash
# Repair an editable install broken by a file-sync service.
#
# This checkout lives under ~/Documents, which macOS syncs to iCloud Drive.
# iCloud occasionally resolves a write race inside .venv by duplicating the file
# with a " 2" suffix, which leaves the editable install's .pth in a state Python
# skips, and `import capex_atlas` starts failing even though nothing changed.
#
# The durable fix is to keep the virtualenv outside the synced tree:
#
#   export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/capex-atlas"
#
# Until then, run this.
set -euo pipefail
cd "$(dirname "$0")/.."

# -rf because iCloud duplicates directories as well as files, and a plain rm -f
# on a directory aborts the script before the reinstall happens.
removed=0
while IFS= read -r duplicate; do
  rm -rf "$duplicate"
  removed=$((removed + 1))
done < <(find .venv \( -name "* [0-9]" -o -name "* [0-9].*" \) 2>/dev/null)

echo "removed $removed sync-conflict file(s)"
uv sync --group dev --reinstall-package capex-atlas -q
uv run python -c "import capex_atlas; print('import ok:', capex_atlas.__version__)"
