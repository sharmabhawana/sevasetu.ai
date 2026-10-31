# =====================================================================
# Seva Setu – ALL-IN-ONE Dockerfile
# Runs Flask portal + Citizen MCP + Officer MCP in a single container.
# This avoids needing separate Render private services.
# =====================================================================
FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# ── Install Flask portal dependencies ────────────────────────────────
COPY app/requirements.txt ./requirements-portal.txt
RUN pip install --no-cache-dir -r requirements-portal.txt

# ── Install MCP dependencies (no pytest at runtime) ──────────────────
COPY requirements-mcp.txt ./requirements-mcp.txt
RUN grep -v 'pytest' requirements-mcp.txt > requirements-mcp-prod.txt \
    && pip install --no-cache-dir -r requirements-mcp-prod.txt

# ── Copy full repository ──────────────────────────────────────────────
COPY . .

# Create runtime directories
RUN mkdir -p /var/sewasetu/uploads /var/log/sewasetu

# Make startup script executable
RUN chmod +x /workspace/start.sh

# PYTHONPATH so all modules (evals, mcp_common, etc.) are importable
ENV PYTHONPATH=/workspace

# Default env vars (overridden by Render env var settings)
ENV CITIZEN_MCP_HOST=0.0.0.0
ENV CITIZEN_MCP_PORT=8001
ENV OFFICER_MCP_HOST=0.0.0.0
ENV OFFICER_MCP_PORT=8002
ENV CITIZEN_MCP_BACKEND=http://127.0.0.1:8001
ENV OFFICER_MCP_BACKEND=http://127.0.0.1:8002

EXPOSE 8000

# All three processes start from this single script
CMD ["/workspace/start.sh"]
