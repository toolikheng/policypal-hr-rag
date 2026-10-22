# PolicyPal — AI HR Policy Assistant

PolicyPal answers employee questions about HR policies in plain English, cites the
policy document and section it used, and refuses to guess when the policies don't
cover a question. It uses retrieval-augmented generation (RAG) with a local
embedding model, PostgreSQL + pgvector, and a local LLM through Ollama.

> All policy documents in this repository are **fictional sample data** for a
> made-up company, **Binaan Maju Sdn Bhd**. They are not real company policies
> and are not legal advice.

**Status:** work in progress. What works today:
- **Scaffold:** Docker Compose services for the database, API and UI, a `/health`
  endpoint, database migrations, tests, linting and CI.
- **Sample data and ingestion:** eight fictional policies are parsed, split into
  chunks, embedded with a local model, and stored in PostgreSQL + pgvector
  automatically when the API starts.

Asking questions (retrieval and answers) arrives in the next phase, and this README
will be updated to match.

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

The first build downloads the Python dependencies, including a CPU-only build of
PyTorch, and the embedding model. On the laptop used for development this took about
6 minutes, and the image is about 2.8 GB. Starting the stack takes about
35 seconds. On start, the API container applies database migrations, loads the sample
policies (skipping any that haven't changed), and then starts the API.

| What | Where |
|---|---|
| API health check | <http://localhost:8000/health> |
| API docs (Swagger) | <http://localhost:8000/docs> |
| Streamlit UI | <http://localhost:8501> |
| PostgreSQL (from your machine) | `localhost:5433` |

`curl localhost:8000/health` returns
`{"database":"ok","documents":8,"chunks":119,"version":"0.1.0","status":"ok"}` when the API
can reach a database whose schema is at the newest migration. If the database is down
or behind the code, it returns HTTP 503 with the reason.

Stop everything with `docker compose down`. Database data is kept in the `pgdata`
volume. `docker compose down -v` deletes it.

## Sample data

`data/policies/` holds eight fictional HR policies for Binaan Maju Sdn Bhd: leave,
medical claims, overtime, expense claims, travel, code of conduct, probation, and work
from home. Each one starts with **FICTIONAL SAMPLE DATA — NOT A REAL COMPANY POLICY**.
They are written to be realistic and a little messy, with numbered clauses, tables,
amendment notes and some deliberately similar-sounding sections, so that retrieval is
tested properly.

- The Markdown files are the source of truth. `make pdfs` renders them to PDF in
  `data/policies/pdf/`. Rendering is deterministic, and it needs the DejaVu fonts
  (`sudo apt install fonts-dejavu-core`).
- `data/upload-demo/` holds one extra policy (Training and Development). It is **not**
  loaded at start. It is kept back to demonstrate uploading a new policy, and as an
  unseen document when the system is evaluated.

## How ingestion works

```
policy file (.md / .pdf) -> sections -> chunks -> embeddings -> PostgreSQL (pgvector)
```

1. **Parse:**
   - Markdown headings, or larger-font lines in a PDF, become sections.
   - Each section remembers its heading path (e.g. `4. Annual Leave > 4.3 Carry
     Forward of Annual Leave`), which later becomes the citation.
   - PDF page headers and footers are removed.
2. **Chunk:**
   - A section of up to 250 words is one chunk.
   - Longer sections are split between paragraphs, with one paragraph of overlap.
   - Chunks never cross sections, and tables are never split.
3. **Embed:** each chunk, prefixed with its document title and section path, is turned
   into a 384-number vector by the local model `BAAI/bge-small-en-v1.5` (no API key).
4. **Store:** one transaction replaces the document's chunks in the `chunks` table,
   which has an HNSW index for fast similarity search.

Ingestion is **idempotent**: a file whose bytes, embedding model and chunker version
haven't changed is skipped. A changed file replaces its chunks, and a deleted file's
document is removed. Run it by hand with `make ingest`. It is safe to run any number
of times.

## Development

```bash
make setup     # create .venv, install dev dependencies, install the pre-commit hook
make db-up     # start only the database (needed by the database tests)
make test      # run the test suite
make lint      # Ruff (lint) + Black (format check)
make format    # auto-fix lint issues and reformat
make ingest    # load the sample policies again (inside the running api container)
make pdfs      # re-render the sample policy PDFs from their Markdown
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
- **Tests and the embedding model:** the tests use a small fake embedder that lives
  in `tests/`, so they run offline and fast. The real model is used in Docker.
- **CPU-only PyTorch:** `requirements.txt` installs PyTorch from the PyTorch CPU
  index. The Docker build fails if a CUDA build or any NVIDIA package is installed.
- **Migrations:** Alembic, in `migrations/versions/`. The API container runs
  `alembic upgrade head` on start.

## Project layout

```
policypal/          FastAPI backend (config, logging, database, API routes)
policypal/ingest/   parsing, chunking and the ingestion pipeline
ui/                 Streamlit UI. It talks to the API over HTTP only
migrations/         Alembic database migrations
data/               fictional sample policies (Markdown + PDF)
scripts/            developer scripts (PDF rendering)
tests/              unit tests (no database) and integration tests (PostgreSQL)
docker/             container start-up script and database init SQL
Dockerfile          one Python image, used by both the api and ui services
docker-compose.yml  db (PostgreSQL + pgvector), api, ui
```

## Running on Windows (WSL2)

- Keep the repository in the Linux filesystem (e.g. `~/projects/policypal`), not under
  `/mnt/c/...`. File watching and Docker volumes are much faster there.
- Use **Docker Desktop with WSL integration** enabled for your distribution. This is
  the setup the project is developed and tested with. Check both of these:

  ```bash
  docker version --format '{{.Server.Platform.Name}}'   # should name Docker Desktop
  docker compose version
  ```

- Don't run a second Docker Engine inside WSL at the same time. After a WSL restart
  it can take over the Docker socket. `docker compose` then fails with "unknown
  command", and your containers seem to have disappeared (they are still in Docker
  Desktop). If you have one installed, stop it from starting:

  ```bash
  sudo systemctl disable --now docker.service docker.socket
  ```

  Disable `docker.socket` as well as `docker.service`: the socket unit can start the
  engine again on its own.
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
