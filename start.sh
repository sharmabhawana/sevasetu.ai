#!/bin/sh
# =====================================================================
# Seva Setu – Single-container startup script
# Starts all three services inside one Render web service:
#   - Citizen MCP  on port 8001 (internal)
#   - Officer MCP  on port 8002 (internal)
#   - Flask portal on port 8000 (public, proxies /mcp/* to above)
# =====================================================================

set -e

echo "==> Starting Seva Setu services..."

# ── 1. Citizen MCP server (background) ──────────────────────────────
echo "Starting Citizen MCP on port 8001..."
cd /workspace
nohup python -m mcp_citizen.server > /var/log/sewasetu/citizen_mcp.log 2>&1 &
CITIZEN_PID=$!

# ── 2. Officer MCP server (background) ──────────────────────────────
echo "Starting Officer MCP on port 8002..."
nohup python -m mcp_officer.server > /var/log/sewasetu/officer_mcp.log 2>&1 &
OFFICER_PID=$!

# ── 3. Wait briefly for MCP servers to start ────────────────────────
sleep 3
# Verify MCP services are up (local health check)
if curl -s -o /dev/null http://127.0.0.1:8001/mcp; then
  echo "Citizen MCP responded successfully" >> /var/log/sewasetu/startup.log
else
  echo "Citizen MCP not reachable" >> /var/log/sewasetu/startup.log
fi
if curl -s -o /dev/null http://127.0.0.1:8002/mcp; then
  echo "Officer MCP responded successfully" >> /var/log/sewasetu/startup.log
else
  echo "Officer MCP not reachable" >> /var/log/sewasetu/startup.log
fi

# ── 4. Flask portal (foreground – this is what Render monitors) ─────
echo "Starting Flask portal on port 8000..."
cd /workspace/app
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile - \
    app:app
