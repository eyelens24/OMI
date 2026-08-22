#!/usr/bin/env bash
# OMI local-only macOS launcher. No broker, vendor, or cloud connection.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "OMI needs Python 3. Install it, or set PYTHON_BIN to its full path." >&2
  exit 1
fi

cd "$ROOT"
echo "Starting OMI at http://127.0.0.1:8000 (local-only)"
exec "$PYTHON_BIN" run-omi.py
