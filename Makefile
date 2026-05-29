# ─────────────────────────────────────────────────────────────────────────────
# SecureAuth Platform — Developer shortcuts
# Usage: make <target>
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help up down build logs shell db-shell redis-shell test lint format \
        migrate migrate-create keys clean

# Default target: show help
help:
	@echo ""
	@echo "  SecureAuth Platform — Available commands"
	@echo "  ────────────────────────────────────────"
	@echo "  make up            Start all services (dev)"
	@echo "  make down          Stop all services"
	@echo "  make build         Rebuild the API image"
	@echo "  make logs          Follow logs from all services"
	@echo "  make shell         Open a bash shell in the API container"
	@echo "  make db-shell      Open psql inside the DB container"
	@echo "  make redis-shell   Open redis-cli inside the Redis container"
	@echo "  make test          Run the full test suite in isolated containers"
	@echo "  make lint          Run Black + Flake8 + isort checks"
	@echo "  make format        Auto-format code with Black + isort"
	@echo "  make migrate       Apply pending Alembic migrations"
	@echo "  make migrate-create name=<migration_name>  Create a new migration"
	@echo "  make keys          Generate RS256 key pair for JWT"
	@echo "  make clean         Remove containers, volumes and images"
	@echo ""

# ── Services ──────────────────────────────────────────────────────────────────

up:
	docker compose up --build -d
	@echo "✅ Services started. API available at http://localhost:8000/docs"

down:
	docker compose down

build:
	docker compose build --no-cache api

logs:
	docker compose logs -f

# ── Shells ────────────────────────────────────────────────────────────────────

shell:
	docker compose exec api bash

db-shell:
	docker compose exec db psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-secureauth}

redis-shell:
	docker compose exec redis redis-cli -a $${REDIS_PASSWORD:-redispassword}

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
	docker compose -f docker-compose.test.yml down -v

# Run tests locally (requires active venv and running db/redis)
test-local:
	uv run pytest tests/ -v --cov=app --cov-report=term-missing

# ── Code Quality ──────────────────────────────────────────────────────────────

lint:
	uv run black --check app/ tests/
	uv run flake8 app/ tests/
	uv run isort --check-only app/ tests/
	uv run bandit -c pyproject.toml -r app/

format:
	uv run black app/ tests/
	uv run isort app/ tests/

# ── Database ──────────────────────────────────────────────────────────────────

migrate:
	docker compose exec api python -m alembic upgrade head

# Usage: make migrate-create name=add_users_table
migrate-create:
	docker compose exec api python -m alembic revision --autogenerate -m "$(name)"

# ── Setup ─────────────────────────────────────────────────────────────────────

keys:
	uv run python scripts/generate_keys.py

# ── Cleanup ───────────────────────────────────────────────────────────────────

# WARNING: -v removes volumes (deletes all database data)
clean:
	docker compose down -v --rmi local
	@echo "🧹 Containers, volumes and local images removed."
