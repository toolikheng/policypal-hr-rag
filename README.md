# PolicyPal — AI HR Policy Assistant

PolicyPal answers employee questions about HR policies in plain English, cites the
policy document and section it used, and refuses to guess when the policies don't
cover a question. It uses retrieval-augmented generation (RAG) with a local
embedding model, PostgreSQL + pgvector, and a local LLM through Ollama.

> All policy documents in this repository are **fictional sample data** for a
> made-up company, **Binaan Maju Sdn Bhd**. They are not real company policies
> and are not legal advice.

**Status:** work in progress. What works today:
- **Scaffold:** Docker Compose services for the database, API, UI and a local LLM, a
  `/health` endpoint, database migrations, tests, linting and CI.
- **Sample data and ingestion:** eight fictional policies are parsed, split into
  chunks, embedded with a local model, and stored in PostgreSQL + pgvector
  automatically when the API starts.
- **Question answering API:** `POST /ask` answers from the policies with citations
  (document and section), refuses when the policies don't cover a question, and quotes
  the policy text when no LLM is available. Admins can upload new policies.

The chat UI arrives in the next phase; for now, use the API (Swagger at `/docs`).

## Prerequisites

- Docker with the Compose plugin (`docker compose version`)
- Git
- For running tests and linters on your machine: Python 3.11+ and `make`
- Disk space: about 15 GB for the images and models (the Ollama image alone is about
  9.4 GB on disk, because it includes GPU libraries; the default model is about 2 GB).
- Memory: about 5 GB free for Docker (the default model uses about 3.6 GB while loaded).

No paid API keys and no GPU are needed.

## Quick start

```bash
git clone <this-repo-url> policypal && cd policypal
cp .env.example .env
docker compose up --build
```

The first build downloads the Python dependencies, including a CPU-only build of
PyTorch, and the embedding model. On the laptop used for development this took about
5–6 minutes, and the image is about 2.8 GB. On start:
- the API container applies database migrations, loads the sample policies and any
  uploaded ones (skipping files that haven't changed), and then starts the API;
- the Ollama container downloads the LLM (`OLLAMA_MODEL`, default `llama3.2:3b`, about
  2 GB) the first time only. Until it is ready, answers quote the policy text instead.

`docker compose up -d --wait` returns once everything, including the model, is ready.

| What | Where |
|---|---|
| API health check | <http://localhost:8000/health> |
| API docs (Swagger) | <http://localhost:8000/docs> |
| Streamlit UI | <http://localhost:8501> |
| PostgreSQL (from your machine) | `localhost:5433` |
| Ollama (from your machine only) | `127.0.0.1:11434` |

`curl localhost:8000/health` returns:

```json
{"database":"ok","llm":{"provider":"ollama","model":"llama3.2:3b","status":"ok"},
 "documents":8,"chunks":119,"version":"0.1.0","status":"ok"}
```

- `status` is `ok`, or `degraded` (still HTTP 200) when the LLM isn't ready: questions
  are then answered by quoting the policy text.
- If the database is down or behind the code, it returns HTTP 503 with the reason.

Stop everything with `docker compose down`. Data is kept in volumes: `pgdata` (the
database), `uploads` (uploaded policies) and `ollama` (the model).
`docker compose down -v` deletes them.

## Asking questions

```bash
curl -s -X POST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "How many days of annual leave do I get after 3 years?"}'
```

A real response from the development laptop (shortened):

```json
{"answer": "According to policy [2], after 3 years of service, employees on M and SM grades receive 20 days of annual leave.",
 "mode": "llm", "refused": false, "model": "llama3.2:3b", "fallback_reason": null,
 "citations": [{"number": 2, "document_title": "Leave Policy",
                "section": "4.1 Annual Leave Entitlement", "text": "...", "similarity": 0.7723}],
 "latency_ms": {"retrieval": 60, "generation": 43953, "total": 44013}}
```

The answer is right for M and SM grades but leaves out the other grades (14 or 16 days),
which is typical of a small local model. It took 44 s because the model had to be
loaded first.

Every answer says how it was produced (`mode`):

| `mode` | When | What you get |
|---|---|---|
| `llm` | The local LLM answered and cited at least one excerpt correctly | The answer, with `[n]` markers matching `citations` |
| `extractive` | No LLM is configured, or the LLM failed (`fallback_reason` says why) | Up to three policy passages, quoted exactly, under "No AI summary available" |
| `refused` | The policies don't cover the question | Exactly `I couldn't find this in the policies.` and no citations |

To run without an LLM at all, set `LLM_PROVIDER=extractive` in `.env`.

### How answers stay grounded

1. **Search:** the question is embedded with the model's recommended query instruction
   ("Represent this sentence for searching relevant passages: "), and pgvector finds
   the 5 most similar chunks by cosine similarity.
2. **Refuse early:** if the best similarity is below `MIN_SIMILARITY` (0.65), the API
   refuses without calling the LLM. The value is a similarity score, not a probability.
   0.65 is provisional: it sits between the scores of 8 answerable and 8 unrelated
   hand-picked questions, and will be calibrated in the evaluation.
3. **Generate:** the excerpts that passed go to the LLM, numbered `[1]`…`[n]`. The
   prompt tells it to use only the excerpts, cite them, reply with the refusal
   sentence if they don't answer the question, and treat the excerpts as data, not
   instructions (a defence against instructions hidden in uploaded files; a
   mitigation, not a guarantee).
4. **Check:** citations are built by the server from the excerpts actually sent.
   Markers that don't match an excerpt are removed. A reply with no valid citation, or
   with nothing but markers, is replaced by the quoted passages. The model can't invent
   a source. But a citation shows where an answer came from, not that it is correct or
   complete.
5. **Fallback, never silent:** if Ollama is down, times out (`OLLAMA_TIMEOUT_SECONDS`,
   default 60) or hasn't downloaded the model, the API quotes the policy text and sets
   `fallback_reason`.

### Speed and model choice

Measured once on the development laptop (Intel Core i5-10300H, CPU only, WSL2,
Docker Desktop), with 8 questions per model. This is illustrative, not an evaluation:

| Model | Median time per answer | Memory while loaded | Notes |
|---|---|---|---|
| `llama3.2:3b` (default) | about 24 s | about 3.6 GB | All 7 cited answers matched the policies when checked by hand |
| `llama3.2:1b` | about 13 s | about 2.4 GB | Refused 2 answerable questions and gave one wrong answer; use only if memory is tight |

The first answer after the model has been unloaded also includes loading it: 33 s in
total for `3b` on an idle laptop, and 58 s while a second copy of the stack was running.
After `OLLAMA_TIMEOUT_SECONDS` (default 60) the API stops waiting and quotes the policy
text instead, so on a slower machine raise it in `.env`. Refusals take well under a
second because the LLM isn't called.

## Managing policies (admin)

Admin endpoints need the `X-Admin-Token` header, set with `ADMIN_TOKEN` in `.env`. It
is a shared demo token, not real user authentication. In Swagger, use **Authorize**.

```bash
curl -s localhost:8000/documents                       # list the policies
curl -s localhost:8000/documents/3                     # one policy, section by section
curl -s -X POST localhost:8000/documents -H "X-Admin-Token: change-me" \
  -F "file=@data/upload-demo/training-and-development-policy.md"   # upload (.md or .pdf)
curl -s -X POST localhost:8000/documents/reingest -H "X-Admin-Token: change-me"
```

A policy is identified by its file name (its *slug*, e.g. `leave-policy`). Uploads
never silently replace anything:

| Upload | Result |
|---|---|
| A new name | `201 created` |
| The same bytes again | `200 unchanged` |
| An existing uploaded policy, different content | `409` with a clear message; nothing changes |
| The same, with `?replace=true` | `200 updated` (old chunks replaced, not duplicated) |
| The name of a built-in sample policy | Always `409`: samples can't be replaced by upload |

Other errors: `401`/`403` (missing or wrong token), `413` (larger than `MAX_UPLOAD_MB`),
`415` (not `.md` or `.pdf`), `422` (unreadable file, e.g. a scanned PDF with no text).
Uploaded files are kept in the `uploads` volume and loaded again on every start.

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
document is removed. Run it by hand with `make ingest` (or `POST /documents/reingest`).
It is safe to run any number of times. Sample policies are loaded before uploads, and
if an uploaded file has a sample policy's name, the sample wins and the upload is
skipped with a warning.

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
- **Tests and the models:** the tests use a fake embedder and a fake LLM that live
  only in `tests/`, and simulate Ollama's HTTP replies (including timeouts and
  errors), so they run offline and fast. The real models are used in Docker.
- **CPU-only PyTorch:** `requirements.txt` installs PyTorch from the PyTorch CPU
  index. The Docker build fails if a CUDA build or any NVIDIA package is installed.
- **Migrations:** Alembic, in `migrations/versions/`. The API container runs
  `alembic upgrade head` on start.

## Project layout

```
policypal/          FastAPI backend (config, logging, database, catalogue, retrieval, answering)
policypal/api/      app factory, request/response models, routes
policypal/llm/      prompt, provider interface and the Ollama client
policypal/ingest/   parsing, chunking, the ingestion pipeline and uploads
ui/                 Streamlit UI. It talks to the API over HTTP only
migrations/         Alembic database migrations
data/               fictional sample policies (Markdown + PDF)
scripts/            developer scripts (PDF rendering)
tests/              unit tests (no database) and integration tests (PostgreSQL)
docker/             container start-up scripts and database init SQL
Dockerfile          one Python image, used by both the api and ui services
docker-compose.yml  db (PostgreSQL + pgvector), api, ui, ollama
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
- WSL2 gets half of the Windows machine's RAM by default. The local LLM needs about
  3.6 GB while loaded (`llama3.2:3b`), on top of about 1 GB for the rest of the stack.
  If WSL feels short of memory, set a limit in `%UserProfile%\.wslconfig`, for example:

  ```ini
  [wsl2]
  memory=10GB
  ```

  Then run `wsl --shutdown` from Windows and reopen your terminal.
- Docker Desktop keeps its images and volumes in one disk image, on `C:` by default.
  The Ollama image and models add more than 11 GB. If `C:` is short of space, move the
  disk image in Docker Desktop: **Settings → Resources → Advanced → Disk image
  location**.
- If a port is already in use (`8000`, `8501`, `5433` or `11434`), change `API_PORT`,
  `UI_PORT`, `DB_HOST_PORT` or `OLLAMA_HOST_PORT` in `.env`.
