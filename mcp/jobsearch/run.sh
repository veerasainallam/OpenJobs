#!/bin/bash
# Launcher for the jobsearch MCP server: creates the venv on first run, then starts the server (stdio).
set -e
cd "$(dirname "$0")"
# Claude Code cloud sandbox: trust the egress proxy CA (no-op elsewhere)
if [ -z "$SSL_CERT_FILE" ] && [ -f /root/.ccr/ca-bundle.crt ]; then export SSL_CERT_FILE=/root/.ccr/ca-bundle.crt; fi
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import mcp, httpx" 2>/dev/null; then
  python3 -m venv .venv >&2
  .venv/bin/pip install --quiet "mcp[cli]<2" httpx >&2
fi
exec .venv/bin/python server.py
