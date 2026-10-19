#!/bin/bash
# One-click setup: creates venv, installs deps, registers with Claude Code.
set -e
cd "$(dirname "$0")"

if ! command -v claude >/dev/null 2>&1; then
  echo "ERROR: 'claude' CLI not found on PATH. Install Claude Code first: https://docs.anthropic.com/en/docs/claude-code"
  exit 1
fi

echo ">> Creating virtual environment..."
python3 -m venv .venv
echo ">> Installing dependencies..."
.venv/bin/pip install --quiet "mcp[cli]<2" httpx

PY="$(pwd)/.venv/bin/python"
SRV="$(pwd)/server.py"
echo ">> Registering MCP server with Claude Code..."
claude mcp add jobsearch -- "$PY" "$SRV"

echo ""
echo "Done! Verify with: claude mcp list"
echo "Then ask: use jobsearch to find Data Analyst roles posted in the last 24 hours."
