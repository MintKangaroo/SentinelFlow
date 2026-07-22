PYTHON ?= python3

.PHONY: install install-web api web lint format-check typecheck test web-check compose-check check

install:
	$(PYTHON) -m pip install -e ".[dev]"

install-web:
	npm --prefix web ci

api:
	$(PYTHON) -m uvicorn sentinelflow.api.main:app --reload --port 8000

web:
	npm --prefix web run dev

lint:
	$(PYTHON) -m ruff check .

format-check:
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy src tests

test:
	$(PYTHON) -m pytest

web-check:
	npm --prefix web run typecheck
	npm --prefix web run test
	npm --prefix web run build

compose-check:
	docker compose config --quiet

check: lint format-check typecheck test web-check compose-check
