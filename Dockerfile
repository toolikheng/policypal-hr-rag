# One image for both the API and the Streamlit UI (they run different commands).
FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so this layer is cached when only the code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy only what the app needs (never `COPY . .`), so local files such as .env
# can never end up inside the image.
COPY alembic.ini ./
COPY migrations/ migrations/
COPY policypal/ policypal/
COPY ui/ ui/
COPY docker/api-entrypoint.sh docker/api-entrypoint.sh

# Run as a normal user, not root.
RUN useradd --create-home --uid 1000 policypal
USER policypal

EXPOSE 8000 8501
CMD ["sh", "docker/api-entrypoint.sh"]
