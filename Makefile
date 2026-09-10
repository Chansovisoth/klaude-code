.PHONY: setup dev up down test lint typecheck package-smoke check doctor

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
	uv run ruff check .

typecheck:
	uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src

package-smoke:
	uv run python scripts/package_smoke.py

check: test lint typecheck

doctor:
	uv run klaude doctor
