# =====================================================================
# Seva Setu – Flask Portal  (Render deployment Dockerfile)
# Build context: repository root
# The Flask application source lives in the app/ sub-directory.
# =====================================================================
FROM python:3.11-slim

# System dependencies needed by psycopg2-binary and fpdf2
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# ── 1. Install Flask portal dependencies ──────────────────────────────
COPY app/requirements.txt ./requirements-portal.txt
RUN pip install --no-cache-dir -r requirements-portal.txt

# ── 2. Install MCP / evals dependencies (needed by evals blueprint) ───
COPY requirements-mcp.txt ./requirements-mcp.txt
# Remove pytest from mcp requirements – not needed at runtime
RUN grep -v 'pytest' requirements-mcp.txt > requirements-mcp-prod.txt \
    && pip install --no-cache-dir -r requirements-mcp-prod.txt

# ── 3. Copy the full repository ───────────────────────────────────────
COPY . .

# Create directories the app writes to
RUN mkdir -p /var/sewasetu/uploads /var/log/sewasetu

# Put the workspace on PYTHONPATH so that `from evals.dashboard import ...` works
ENV PYTHONPATH=/workspace

# Flask/gunicorn run from the app/ directory; app.py exports `app`
WORKDIR /workspace/app

EXPOSE 8000

# 2 workers is safe on Render's 512 MB free instances
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "app:app"]
