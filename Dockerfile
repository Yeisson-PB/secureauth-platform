# ─────────────────────────────────────────────
# Stage 1: builder
# Exports a requirements.txt desde uv.lock
# ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:0.4.20 /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml .
COPY uv.lock* .

# Export dependencies as requirements.txt (sin hashes para simplicidad)
# Esto convierte uv.lock → requirements.txt estándar que pip puede usar
RUN uv export --frozen --no-dev --no-hashes --no-emit-project -o requirements.txt

# ─────────────────────────────────────────────
# Stage 2: runtime
# Instala dependencias con pip directo al sistema
# ─────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# Copiar requirements del builder e instalar con pip
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY app/ ./app/

RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
