# Common PolicyPal commands. Run `make help` to list them.
VENV := .venv
BIN := $(VENV)/bin

.PHONY: help setup up down logs db-up test lint format lint-workflows migrate ingest pdfs

help: ## List available commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup: ## Create .venv, install dev dependencies, install the pre-commit hook
	python3 -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements-dev.txt
	$(BIN)/pre-commit install

up: ## Build and start all services in the background
	docker compose up --build -d

down: ## Stop all services (data is kept in the pgdata volume)
	docker compose down

logs: ## Follow logs from all services
	docker compose logs -f

db-up: ## Start only the database (enough for running the tests)
	docker compose up -d --wait db

test: ## Run the test suite (database tests need `make db-up`)
	$(BIN)/pytest

lint: ## Check linting (Ruff) and formatting (Black) without changing files
	$(BIN)/ruff check .
	$(BIN)/black --check .

format: ## Fix lint issues Ruff can fix and reformat code with Black
	$(BIN)/ruff check --fix .
	$(BIN)/black .

lint-workflows: ## Check GitHub Actions workflow files with actionlint (runs in Docker)
	docker run --rm -v "$(CURDIR)":/repo -w /repo rhysd/actionlint:1.7.12 -color

migrate: ## Apply database migrations inside the running api container
	docker compose exec api alembic upgrade head

ingest: ## Load the sample policies again inside the running api container (idempotent)
	docker compose exec api python -m policypal.ingest

pdfs: ## Re-render the sample policy PDFs from their Markdown (needs fonts-dejavu-core)
	$(BIN)/python scripts/build_pdfs.py
