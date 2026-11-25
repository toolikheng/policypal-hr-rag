# One image for both the API and the Streamlit UI (they run different commands).
#
# Three stages:
#   base     the pinned Python image and shared settings
#   deps     the slow part (Python packages, the embedding model), reused from the cache
#   runtime  the final image: upgrades the Debian packages, then copies in deps and the app
# Docker reuses a cached step while its text is unchanged, so a cached `apt-get upgrade`
# would never pick up new Debian security fixes. Build the runtime stage without the
# cache (CD does this; locally use the command below):
#   docker build --no-cache-filter runtime .
FROM python:3.12.14-slim-trixie AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/huggingface

WORKDIR /app


FROM base AS deps

# The build fails if a CUDA build of torch or any NVIDIA package slips in: this image
# must stay CPU-only (requirements.txt installs torch from the PyTorch CPU index).
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && python -c "import sys, torch; sys.exit(f'CUDA torch installed ({torch.version.cuda})' if torch.version.cuda else 0)" \
 && if pip list 2>/dev/null | grep -i '^nvidia'; then echo 'NVIDIA packages found: torch must be the CPU build' >&2; exit 1; fi

# Download the embedding model once, at build time: at run time the app never needs
# the internet.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}', device='cpu')"


FROM base AS runtime

# Install the Debian security fixes released since the base image was built.
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

# Python packages (pip installs everything under /usr/local) and the embedding model.
COPY --from=deps /usr/local /usr/local
COPY --from=deps /opt/huggingface /opt/huggingface
# Offline at run time; no progress bars, so every log line stays JSON.
ENV HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1

# Copy only what the app needs (never `COPY . .`), so local files such as .env
# can never end up inside the image. The upload-demo policy is deliberately left out.
COPY alembic.ini ./
COPY migrations/ migrations/
COPY policypal/ policypal/
COPY evaluation/ evaluation/
COPY ui/ ui/
COPY widget/ widget/
COPY data/policies/ data/policies/
COPY docker/api-entrypoint.sh docker/api-entrypoint.sh

# Run as a normal user, not root. Uploaded policies are saved in /app/uploads
# (a volume in Compose), which this user must own.
RUN useradd --create-home --uid 1000 policypal \
 && mkdir /app/uploads \
 && chown policypal:policypal /app/uploads
USER policypal

EXPOSE 8000 8501
CMD ["sh", "docker/api-entrypoint.sh"]
