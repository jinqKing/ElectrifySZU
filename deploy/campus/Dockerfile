# ── ElectrifySZU — Campus Proxy Server ──────────────────────────────────
#
# Runs on the campus-internal machine, behind SZU firewall.
# Handles only endpoints that need internal network access:
#   /api/status, /api/buildings, /api/building-ranking, /api/apartment/*
#
# This server is reached via SSH tunnel from the public server.
# No public port exposure needed.
#
# Build:
#   docker build -f deploy/campus/Dockerfile -t electrifyszu-campus .
#
# Run:
#   docker run -d --name electrifyszu-campus \
#     --network host \
#     -v /path/to/data:/app/data \
#     -v /path/to/.env:/app/.env:ro \
#     electrifyszu-campus
# ─────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir "httpx>=0.28.1" "xlrd>=2.0.1"

# ── Copy all modules (campus proxy needs everything) ─────────────────────

COPY electrifyszu/ electrifyszu/
COPY server_campus.py server_campus.py

# Create data directory for ranking cache etc.
RUN mkdir -p /app/data

# Non-root user
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["python", "server_campus.py", "--host", "127.0.0.1", "--port", "8000"]
