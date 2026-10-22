"""Ingest the sample policies:  python -m policypal.ingest

Safe to run any number of times: unchanged files are skipped.
"""

import logging
from collections import Counter

from policypal.config import Settings
from policypal.db import make_engine
from policypal.embeddings import SentenceTransformerEmbedder
from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR, ingest_folder
from policypal.logging_setup import configure_logging

logger = logging.getLogger("policypal.ingest")


def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings.database_url)
    try:
        embedder = SentenceTransformerEmbedder(settings.embedding_model)
        results = ingest_folder(engine, embedder, SAMPLE_POLICIES_DIR, origin="sample")
    finally:
        engine.dispose()

    for result in results:
        logger.info(
            "ingest.document",
            extra={"slug": result.slug, "status": result.status, "chunks": result.chunks},
        )
    # Nested under one key: a status name such as "created" is a reserved log-record field.
    by_status = dict(Counter(result.status for result in results))
    logger.info("ingest.completed", extra={"documents_by_status": by_status})


if __name__ == "__main__":
    main()
