# =====================================================================
# Seva Setu – Flask Portal
# Context: repository root.  The app source lives in the app/ subdir.
# =====================================================================
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install Python dependencies first (layer cached unless requirements change)
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install MCP requirements too (evals dashboard imported by app.py)
COPY requirements-mcp.txt .
RUN pip install --no-cache-dir -r requirements-mcp.txt

# Copy the entire repo so that evals/ and mcp_common/ are reachable
COPY . .

# Create upload + log directories that the app expects
RUN mkdir -p /var/sewasetu/uploads /var/log/sewasetu

ENV PYTHONPATH=/workspace
WORKDIR /workspace/app

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", "app:app"]
