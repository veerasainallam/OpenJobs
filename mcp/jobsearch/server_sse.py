"""SSE entrypoint for the Job Search MCP server (web-chat route).

Equivalent to `server.py --sse`; accepts the same flags (--port, --allowed-host,
--allow-any-host). Serves https://<tunnel-url>/sse for claude.ai custom connectors.

Run:  .venv/bin/python server_sse.py --allow-any-host
Then: cloudflared tunnel --url http://localhost:8000
"""

import runpy
import sys

if __name__ == "__main__":
    sys.argv.insert(1, "--sse")
    runpy.run_path(__file__.replace("server_sse.py", "server.py"), run_name="__main__")
