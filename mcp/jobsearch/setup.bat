@echo off
REM One-click setup: creates venv, installs deps, registers with Claude Code.
cd /d "%~dp0"

where claude >nul 2>nul
if errorlevel 1 (
  echo ERROR: 'claude' CLI not found on PATH. Install Claude Code first: https://docs.anthropic.com/en/docs/claude-code
  pause
  exit /b 1
)

echo ^>^> Creating virtual environment...
py -m venv .venv
echo ^>^> Installing dependencies...
.venv\Scripts\pip install "mcp[cli]<2" httpx

echo ^>^> Registering MCP server with Claude Code...
claude mcp add jobsearch -- "%CD%\.venv\Scripts\python.exe" "%CD%\server.py"

echo.
echo Done! Verify with: claude mcp list
pause
