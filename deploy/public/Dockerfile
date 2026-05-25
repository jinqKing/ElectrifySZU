# ── ElectrifySZU — Public API Server ────────────────────────────────────
#
# Minimal image: only modules needed for public-safe endpoints.
# Excludes: dorm/, apartment/, ranking/ (campus network-dependent).
#
# Build:
#   docker build -f deploy/public/Dockerfile -t electrifyszu-public .
#
# Run:
#   docker run -d --name electrifyszu-public \
#     -p 127.0.0.1:8000:8000 \
#     -v /path/to/data:/app/data \
#     -v /path/to/.env:/app/.env:ro \
#     electrifyszu-public
# ─────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random

WORKDIR /app

RUN pip install --no-cache-dir "httpx>=0.28.1"

# ── Copy only public-safe modules ────────────────────────────────────────

# Core infrastructure
COPY electrifyszu/__init__.py          electrifyszu/
COPY electrifyszu/config.py            electrifyszu/
COPY electrifyszu/database.py          electrifyszu/
COPY electrifyszu/logging.py           electrifyszu/
COPY electrifyszu/version.py           electrifyszu/

# Server handler types (shared utilities)
COPY electrifyszu/server/__init__.py   electrifyszu/server/
COPY electrifyszu/server/handlers/    electrifyszu/server/handlers/

# Subscription module (email-based, no campus dependency)
COPY electrifyszu/subscription/        electrifyszu/subscription/

# Public server entry point
COPY server_public.py                  server_public.py

# Create data directory for SQLite
RUN mkdir -p /app/data

# Non-root user
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; \
        r = urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3); \
        assert r.status == 200" || exit 1

CMD ["python", "server_public.py", "--host", "0.0.0.0", "--port", "8000"]
