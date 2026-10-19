"""Job Search MCP server — keyless job-listing APIs for Sai Santosh's pipeline.

Exposes free, no-key job sources as MCP tools:
  - Arbeitnow, RemoteOK, Remotive (remote/tech boards)
  - Greenhouse + Lever public board APIs (per-company ATS feeds)
  - fresh_jobs: fan-out across the keyless boards, merged + deduped

Run:  .venv/bin/python server.py   (stdio transport)
"""

from datetime import datetime, timedelta, timezone
import os
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("jobsearch")
UA = {"User-Agent": "jobsearch-mcp/1.0 (personal job-search automation)"}
TIMEOUT = 30.0

# The sandbox sets proxy env vars whose no_proxy wildcards (*[::1]) crash
# httpx's env parsing, so bypass trust_env and pass the proxy explicitly.
_PROXY = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or None
_CA = os.environ.get("SSL_CERT_FILE") or True


def _client() -> httpx.Client:
    return httpx.Client(headers=UA, timeout=TIMEOUT, trust_env=False,
                        proxy=_PROXY, verify=_CA, follow_redirects=True)

# His 8 target titles — used by fresh_jobs for loose title matching
TARGET_TITLES = [
    "Project Coordinator",
    "PMO Analyst",
    "Data Analyst",
    "Power BI Analyst",
    "Business Intelligence Analyst",
    "Project Controls Analyst",
    "Operations Analyst",
    "Reporting Analyst",
]


def _title_match(job_title: str, query: str) -> bool:
    """All significant words of the query must appear in the job title."""
    stop = {"and", "or", "the", "a", "an", "of", "for", "sr", "jr", "i", "ii", "iii"}
    words = [w for w in query.lower().split() if w not in stop]
    jt = job_title.lower()
    return all(w in jt for w in words)


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            # epoch seconds or ms
            if value > 1e12:
                value = value / 1000
            return datetime.fromtimestamp(value, tz=timezone.utc)
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _fresh(dt: datetime | None, hours: int) -> bool:
    if not dt:
        return True  # keep undated postings; flag them
    return datetime.now(timezone.utc) - dt <= timedelta(hours=hours)


def _norm(title, company, location, url, posted_at, source, remote=None, salary=None):
    return {
        "title": title,
        "company": company,
        "location": location,
        "remote": remote,
        "salary": salary,
        "url": url,
        "posted_at": posted_at,
        "source": source,
    }


# ---------------------------------------------------------------- Arbeitnow
@mcp.tool()
def search_arbitnow(keyword: str, location: str = "United States",
                    remote: bool | None = None,
                    posted_after_iso: str | None = None,
                    per_page: int = 50) -> dict:
    """Search Arbeitnow job board (free, keyless). posted_after_iso like '2026-10-18T00:00:00Z'."""
    params = {"search": keyword, "location": location, "per_page": min(per_page, 100)}
    if remote is not None:
        params["remote"] = str(remote).lower()
    if posted_after_iso:
        params["created_after"] = posted_after_iso
    with _client() as c:
        r = c.get("https://api.arbeitnow.com/v1/job-board", params=params)
        r.raise_for_status()
        data = r.json().get("data", [])
    return {"count": len(data), "jobs": [
        _norm(j.get("title"), j.get("company_name"), j.get("location"),
              j.get("url"), j.get("created_at"), "arbeitnow",
              remote=j.get("remote"), salary=j.get("salary"))
        for j in data
    ]}


# ---------------------------------------------------------------- RemoteOK
@mcp.tool()
def search_remoteok(tag: str = "data", location: str = "usa",
                    since_hours: int = 24) -> dict:
    """Search RemoteOK (free, keyless, remote-only). tag e.g. 'data', 'project manager'."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    loc_want = location.lower()
    with _client() as c:
        r = c.get("https://remoteok.com/api", params={"tag": tag})
        r.raise_for_status()
        items = r.json()[1:]  # [0] is metadata
    jobs = []
    for j in items:
        dt = _parse_dt(j.get("date"))
        if dt and dt < cutoff:
            continue
        loc = (j.get("location") or "").lower()
        # location filter: 'usa' also accepts worldwide/anywhere/remote postings
        if loc_want in ("usa", "united states", "us") and not (
                "usa" in loc or "united states" in loc or "u.s." in loc
                or loc.strip() in ("worldwide", "anywhere", "remote", "")):
            continue
        elif loc_want not in ("usa", "united states", "us") and loc_want not in loc:
            continue
        jobs.append(_norm(j.get("position"), j.get("company"), j.get("location"),
                          j.get("apply_url") or j.get("url"),
                          j.get("date"), "remoteok", remote=True,
                          salary=(j.get("salary_min") and f"{j.get('salary_min')}-{j.get('salary_max')}")))
    return {"count": len(jobs), "jobs": jobs}


# ---------------------------------------------------------------- Remotive
@mcp.tool()
def search_remotive(keyword: str, category: str | None = None,
                    since_hours: int = 24) -> dict:
    """Search Remotive (free, keyless, curated remote). category e.g. 'data', 'project-management'."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    params = {"search": keyword}
    if category:
        params["category"] = category
    with _client() as c:
        r = c.get("https://remotive.com/api/remote-jobs", params=params)
        r.raise_for_status()
        items = r.json().get("jobs", [])
    jobs = []
    for j in items:
        dt = _parse_dt(j.get("publication_date"))
        if dt and dt < cutoff:
            continue
        jobs.append(_norm(j.get("title"), j.get("company_name"),
                          j.get("candidate_required_location"), j.get("url"),
                          j.get("publication_date"), "remotive", remote=True,
                          salary=j.get("salary")))
    return {"count": len(jobs), "jobs": jobs}


# ---------------------------------------------------------------- Greenhouse
@mcp.tool()
def search_greenhouse(board_token: str, created_after_iso: str | None = None,
                      keyword: str | None = None) -> dict:
    """Search one company's Greenhouse board (free, keyless).
    board_token is the slug in boards.greenhouse.io/{token} (find it on the company's careers page URL)."""
    with _client() as c:
        r = c.get(f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs")
        r.raise_for_status()
        items = r.json().get("jobs", [])
    jobs = []
    for j in items:
        if created_after_iso and (j.get("updated_at") or "") < created_after_iso:
            continue
        if keyword and not _title_match(j.get("title", ""), keyword):
            continue
        loc = (j.get("location") or {}).get("name")
        jobs.append(_norm(j.get("title"), board_token, loc, j.get("absolute_url"),
                          j.get("updated_at"), "greenhouse"))
    return {"board": board_token, "count": len(jobs), "jobs": jobs}


# ---------------------------------------------------------------- Lever
@mcp.tool()
def search_lever(company_id: str, keyword: str | None = None,
                since_hours: int = 24) -> dict:
    """Search one company's Lever postings (free, keyless).
    company_id is the slug in lever.co/{company_id} (find it on the company's careers page URL)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    with _client() as c:
        r = c.get(f"https://api.lever.co/v0/postings/{company_id}", params={"mode": "json"})
        r.raise_for_status()
        items = r.json()
    jobs = []
    for j in items:
        dt = _parse_dt(j.get("createdAt"))
        if dt and dt < cutoff:
            continue
        if keyword and not _title_match(j.get("text", ""), keyword):
            continue
        cats = j.get("categories") or {}
        jobs.append(_norm(j.get("text"), company_id, cats.get("location"),
                          j.get("hostedUrl"), j.get("createdAt"), "lever",
                          remote=(cats.get("workplaceType") or "").lower() == "remote"))
    return {"company": company_id, "count": len(jobs), "jobs": jobs}


# ---------------------------------------------------------------- Fan-out
@mcp.tool()
def fresh_jobs(title: str, hours: int = 24) -> dict:
    """Fan-out: search Arbeitnow + RemoteOK + Remotive for fresh postings matching a job title.
    Merges, dedupes and returns postings from the last `hours` hours (default 24).
    title e.g. 'Project Coordinator', 'Data Analyst', 'Power BI Analyst'."""
    seen, merged = set(), []
    tag = title.lower().replace(" analyst", "").replace(" ", "-")
    sources = [
        ("arbeitnow", lambda: search_arbitnow(keyword=title, posted_after_iso=(
            datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat())["jobs"]),
        ("remoteok", lambda: search_remoteok(
            tag="data" if "analyst" in title.lower() else "project-manager",
            since_hours=hours)["jobs"]),
        ("remotive", lambda: search_remotive(keyword=title, since_hours=hours)["jobs"]),
    ]
    for name, fn in sources:
        try:
            for j in fn():
                if not _title_match(j["title"] or "", title):
                    continue
                key = ((j["title"] or "").lower(), (j["company"] or "").lower())
                if key in seen:
                    continue
                seen.add(key)
                merged.append(j)
        except Exception as e:
            merged.append({"source": name, "error": f"{type(e).__name__}: {e}"})
    return {"title": title, "hours": hours, "count": len(merged), "jobs": merged}


@mcp.tool()
def target_titles() -> dict:
    """List Sai Santosh's 8 target job titles for title-matching."""
    return {"titles": TARGET_TITLES}


def _run_http(host: str, port: int, allowed_hosts: list[str], allow_any_host: bool) -> None:
    """Serve over streamable HTTP at http://{host}:{port}/mcp (for tunnels / remote clients).

    Host-header (DNS-rebinding) protection stays on: only localhost plus
    `allowed_hosts` are accepted. A tunnel's public hostname must be added
    via --allowed-host / JOBSEARCH_ALLOWED_HOSTS, or explicitly waived with
    --allow-any-host (e.g. for cloudflared quick tunnels, whose name is random).
    """
    from mcp.server.transport_security import TransportSecuritySettings
    mcp.settings.host = host
    mcp.settings.port = port
    local = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=not allow_any_host,
        allowed_hosts=local + allowed_hosts,
        allowed_origins=[f"http://{h}" for h in local] + [f"https://{h}" for h in allowed_hosts],
    )
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="jobsearch MCP server")
    ap.add_argument("--http", action="store_true",
                    help="serve over streamable HTTP at /mcp instead of stdio")
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--allowed-host", action="append", default=[],
                    help="public hostname to accept (repeatable), e.g. jobs.example.com")
    ap.add_argument("--allow-any-host", action="store_true",
                    help="disable Host-header checks (needed for random quick-tunnel hostnames)")
    a = ap.parse_args()
    env_hosts = [h.strip() for h in os.environ.get("JOBSEARCH_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if a.http:
        _run_http(a.host, a.port, a.allowed_host + env_hosts, a.allow_any_host)
    else:
        mcp.run()
