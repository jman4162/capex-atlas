#!/usr/bin/env bash
# Prose linting for tracked docs and Python docstrings.
#
# Two linters, because measured on this repo their findings overlap on roughly one
# rule. slopscore reads Markdown and docstrings; slopless reads Markdown structure.
#
# Scope comes from `git ls-files`, so untracked drafts and the gitignored
# `*.local.md` design notes stay out. That doc is mostly quoted journalism; its score
# says nothing about prose we wrote.
#
#   ./scripts/slopcheck.sh            both linters
#   ./scripts/slopcheck.sh score      slopscore only (no Node needed)
#   ./scripts/slopcheck.sh less       slopless only
set -euo pipefail
cd "$(dirname "$0")/.."

which="${1:-all}"
docs=()
while IFS= read -r doc; do docs+=("$doc"); done < <(git ls-files '*.md')
status=0

if [[ "$which" == "all" || "$which" == "score" ]]; then
  # Two passes: slopscore takes either a file list or one directory with -r,
  # and errors when the two are mixed.
  echo "== slopscore: markdown =="
  uv run slopscore-lint scan "${docs[@]}" --fail-on medium || status=1
  echo "== slopscore: docstrings =="
  uv run slopscore-lint scan src -r --fail-on medium || status=1
fi

if [[ "$which" == "all" || "$which" == "less" ]]; then
  echo "== slopless: markdown structure =="
  if [[ ! -d node_modules/slopless ]]; then
    echo "slopless not installed; run 'npm ci' (needs Node 22+)" >&2
    exit 1
  fi
  npx --no-install slopless "${docs[@]}" > .slopless-findings.json || status=1
  python3 - <<'PY' || status=1
import json
import pathlib
import sys

raw = pathlib.Path(".slopless-findings.json")
findings = [
    (f["filePath"].split("/")[-1], m)
    for f in json.loads(raw.read_text())
    for m in f["messages"]
]
raw.unlink()
for name, m in findings:
    print(f"  {name}:{m['line']} {m['ruleId']}: {m['message'][:110]}")
print(f"  {len(findings)} finding(s)")
sys.exit(1 if findings else 0)
PY
fi

exit "$status"
