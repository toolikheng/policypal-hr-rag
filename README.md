# PolicyPal — AI HR Policy Assistant

PolicyPal answers employee questions about HR policies in plain English, cites the
policy document and section it used, and refuses to guess when the policies don't
cover a question. It uses retrieval-augmented generation (RAG) with a local
embedding model, PostgreSQL + pgvector, and a local LLM through Ollama.

> All policy documents in this repository are **fictional sample data** for a
> made-up company, **Binaan Maju Sdn Bhd**. They are not real company policies
> and are not legal advice.

**Status:** work in progress. What works today: the project scaffold. That means
Docker Compose services for the database, API and UI, a `/health` endpoint,
database migrations, tests, linting and CI. The RAG features arrive in later phases,
and this README will be updated to match.

## Prerequisites

- Docker with the Compose plugin (`docker compose version`)
- Git
- For running tests and linters on your machine: Python 3.11+ and `make`

No paid API keys and no GPU are needed.

## Quick start

```bash
git clone <this-repo-url> policypal && cd policypal
cp .env.example .env
docker compose up --build
```

The first build downloads the Python base image and dependencies, which takes a few
minutes. Later starts are much faster.

| What | Where |
|---|---|
| API health check | <http://localhost:8000/health> |
| API docs (Swagger) | <http://localhost:8000/docs> |
| Streamlit UI | <http://localhost:8501> |
| PostgreSQL (from your machine) | `localhost:5433` |

`curl localhost:8000/health` returns `{"status":"ok","database":"ok",...}` when the API
can reach a migrated database. If the database is down or not migrated, it returns
HTTP 503 with the reason.

Stop everything with `docker compose down`. Database data is kept in the `pgdata`
volume. `docker compose down -v` deletes it.

## Development

```bash
make setup     # create .venv, install dev dependencies, install the pre-commit hook
make db-up     # start only the database (needed by the database tests)
make test      # run the test suite
make lint      # Ruff (lint) + Black (format check)
make format    # auto-fix lint issues and reformat
make help      # list all commands
```

- **Tests:** they run against a separate `policypal_test` database. It is created
  automatically the first time the database container starts. If the database isn't
  running, the database tests are skipped with a clear message (`pytest -ra` shows why).
  In CI they fail instead.
- **Code style:** the pre-commit hook runs Ruff and Black on every commit.
- **CI:** GitHub Actions (`.github/workflows/ci.yml`) runs lint and tests on every
  push and pull request. The tests use a PostgreSQL + pgvector service container.
  `make lint-workflows` checks the workflow files locally with actionlint.
- **Configuration:** every setting is an environment variable, documented in
  `.env.example`. Never commit `.env`.
- **Migrations:** Alembic, in `migrations/versions/`. The API container runs
  `alembic upgrade head` on start.

## Project layout

```
policypal/          FastAPI backend (config, logging, database, API routes)
ui/                 Streamlit UI. It talks to the API over HTTP only
migrations/         Alembic database migrations
tests/              unit tests (no database) and integration tests (PostgreSQL)
docker/             container start-up script and database init SQL
Dockerfile          one Python image, used by both the api and ui services
docker-compose.yml  db (PostgreSQL + pgvector), api, ui
```

## Running on Windows (WSL2)

- Keep the repository in the Linux filesystem (e.g. `~/projects/policypal`), not under
  `/mnt/c/...`. File watching and Docker volumes are much faster there.
- Use Docker Desktop with WSL integration enabled for your distribution, or Docker
  Engine installed inside WSL. Check with `docker compose version`.
- WSL2 gets half of the Windows machine's RAM by default. Later phases add a local LLM
  that needs several GB. If WSL feels short of memory, set a limit in
  `%UserProfile%\.wslconfig`, for example:

  ```ini
  [wsl2]
  memory=10GB
  ```

  Then run `wsl --shutdown` from Windows and reopen your terminal.
- If a port is already in use (`8000`, `8501` or `5433`), change `API_PORT`, `UI_PORT`
  or `DB_HOST_PORT` in `.env`.
