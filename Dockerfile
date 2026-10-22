# One image for both the API and the Streamlit UI (they run different commands).
FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so this layer is cached when only the code changes.
# The build fails if a CUDA build of torch or any NVIDIA package slips in: this image
# must stay CPU-only (requirements.txt installs torch from the PyTorch CPU index).
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && python -c "import sys, torch; sys.exit(f'CUDA torch installed ({torch.version.cuda})' if torch.version.cuda else 0)" \
 && if pip list 2>/dev/null | grep -i '^nvidia'; then echo 'NVIDIA packages found: torch must be the CPU build' >&2; exit 1; fi

# Download the embedding model once, at build time, then switch the Hugging Face
# libraries to offline mode: at run time the app never needs the internet.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
ENV HF_HOME=/opt/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}', device='cpu')"
# Offline at run time; no progress bars, so every log line stays JSON.
ENV HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1

# Copy only what the app needs (never `COPY . .`), so local files such as .env
# can never end up inside the image. The upload-demo policy is deliberately left out.
COPY alembic.ini ./
COPY migrations/ migrations/
COPY policypal/ policypal/
COPY ui/ ui/
COPY data/policies/ data/policies/
COPY docker/api-entrypoint.sh docker/api-entrypoint.sh

# Run as a normal user, not root.
RUN useradd --create-home --uid 1000 policypal
USER policypal

EXPOSE 8000 8501
CMD ["sh", "docker/api-entrypoint.sh"]
