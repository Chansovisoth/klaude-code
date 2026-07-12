.PHONY: setup dev up down test lint doctor

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
	uv run ruff check . && uv run mypy packages apps || true

doctor:
	uv run klaude doctor
