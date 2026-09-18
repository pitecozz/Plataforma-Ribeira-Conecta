PYTHON ?= python3
DATABASE_URL ?= postgresql://ribeira_app:ribeira_app_dev_only@127.0.0.1:55432/ribeira_dev
MIGRATION_DATABASE_URL ?= postgresql://ribeira_admin:ribeira_admin_dev_only@127.0.0.1:55432/ribeira_dev

.PHONY: install format lint typecheck test test-unit test-integration db-up db-down db-migrate db-reset api security

install:
	$(PYTHON) -m pip install -e '.[dev]'

format:
	ruff format src tests

lint:
	ruff check src tests

typecheck:
	mypy src

test-unit:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

test-integration:
	@RIBEIRA_TEST_DATABASE_URL=$(DATABASE_URL) PYTHONPATH=src $(PYTHON) -m unittest discover -s tests/integration -v

test: test-unit test-integration

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

db-migrate:
	@RIBEIRA_MIGRATION_DATABASE_URL=$(MIGRATION_DATABASE_URL) PYTHONPATH=src $(PYTHON) -m ribeira_platform.migrations upgrade

db-reset:
	@RIBEIRA_MIGRATION_DATABASE_URL=$(MIGRATION_DATABASE_URL) PYTHONPATH=src $(PYTHON) -m ribeira_platform.migrations clean upgrade

api:
	@RIBEIRA_DATABASE_URL=$(DATABASE_URL) PYTHONPATH=src $(PYTHON) -m ribeira_platform.api

security:
	bandit -q -r src
	pip-audit --skip-editable
	detect-secrets scan --all-files --exclude-files '(^|/)(\.git|\.venv|__pycache__|\.mypy_cache|\.ruff_cache)/' --exclude-files 'requirements.lock' --exclude-lines '(dev_only|ci_only|dev-only)'
	pip-audit --skip-editable --format cyclonedx-json --output sbom.cdx.json
