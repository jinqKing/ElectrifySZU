FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ELECTRIFYSZU_DATA_DIR=/app/data

WORKDIR /app

RUN pip install --no-cache-dir \
    "httpx>=0.28.1" \
    "xlrd>=2.0.1"

COPY . .

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/demo-status', timeout=3).read()" || exit 1

CMD ["python", "server.py", "--host", "127.0.0.1", "--port", "8000"]
