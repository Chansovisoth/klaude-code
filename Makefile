.PHONY: setup dev up down test lint typecheck check doctor

setup:
	bash scripts/install.sh

up:
	docker compose up -d

down:
	docker compose down

dev:
	uv sync

test:
	uv run pytest -q

lint:
	RUFF_NO_CACHE=true .venv/bin/ruff check .

typecheck:
	uv run mypy packages apps

check: test lint

doctor:
	uv run klaude doctor
