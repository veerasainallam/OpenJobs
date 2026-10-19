# Job Search MCP Server

MCP server wrapping **free, keyless** job-listing APIs — ask Claude
"find me fresh Project Coordinator roles" and it queries live.

## Tools

| Tool | What it does |
|---|---|
| `fresh_jobs(title, hours=24)` | Fan-out across Arbeitnow + RemoteOK + Remotive; merged, deduped, title-matched |
| `search_arbitnow(keyword, location, remote, posted_after_iso)` | Arbeitnow board (keyless) |
| `search_remoteok(tag, location, since_hours)` | RemoteOK, remote-only (keyless) |
| `search_remotive(keyword, category, since_hours)` | Remotive, curated remote (keyless) |
| `search_greenhouse(board_token, created_after_iso, keyword)` | One company's Greenhouse board (keyless). Token = slug in `boards.greenhouse.io/{token}` |
| `search_lever(company_id, keyword, since_hours)` | One company's Lever postings (keyless). ID = slug in `lever.co/{company_id}` |
| `target_titles()` | Sai Santosh's 8 target titles |

All keyless — no API keys, no registration, $0.

## Setup (your machine)

```bash
cd jobsearch-mcp
python3 -m venv .venv
.venv/bin/pip install "mcp[cli]<2" httpx        # Windows: .venv\Scripts\pip install ...
```

## Connect

**Claude Desktop** — add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "jobsearch": {
      "command": "/absolute/path/to/jobsearch-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/jobsearch-mcp/server.py"]
    }
  }
}
```

**Claude Code** (terminal):
```bash
claude mcp add jobsearch -- /absolute/path/to/jobsearch-mcp/.venv/bin/python /absolute/path/to/jobsearch-mcp/server.py
```

**claude.ai / remote clients (web mode)** — run the server over streamable HTTP
on port 8000 and expose it with a tunnel:

```bash
# Named tunnel / your own domain (Host-header checks stay on):
./run.sh --http --allowed-host jobs.example.com

# cloudflared quick tunnel (random *.trycloudflare.com name each run):
./run.sh --http --allow-any-host
cloudflared tunnel --url http://localhost:8000
```

The MCP endpoint is `https://<tunnel-host>/mcp`. Add it in claude.ai →
Settings → Connectors → Add custom connector.

- Flags: `--host` (default `127.0.0.1`), `--port` (default `8000`, or `$PORT`),
  `--allowed-host` (repeatable, or `JOBSEARCH_ALLOWED_HOSTS=a.com,b.com`).
- Host-header (DNS-rebinding) protection is on by default; requests for any
  hostname other than localhost/allowed hosts get `421`. `--allow-any-host`
  turns it off — only use it with a tunnel, never by binding to `0.0.0.0`.
- There is **no authentication**: anyone with the tunnel URL can call the tools.
  They only read public job boards, but stop the tunnel when you're done.

Restart the client after adding. Then: *"Use jobsearch to find Project Coordinator
roles posted in the last 24 hours."*

## Per-company ATS monitoring

Keep a Google Sheet of board tokens for target employers, e.g.
`stripe`, `airbnb`, `shopify` (Greenhouse). Find any company's token/ID in its
careers-page URL (`boards.greenhouse.io/{token}`, `lever.co/{company}`).

## Notes

- Tested 2026-10-19: Greenhouse ✅ live data · RemoteOK ✅ · Lever ✅ (200, code path verified; most firms migrated off Lever — find current slugs from careers URLs) · Arbeitnow/Remotive ⚠️ unreachable from the build sandbox (proxy blocks), expected to work on a normal network.
- Paid upgrades (not included): Adzuna (free 1k–5k calls/day, key), JSearch (RapidAPI).
- Rate limits are polite defaults; don't hammer the boards.
