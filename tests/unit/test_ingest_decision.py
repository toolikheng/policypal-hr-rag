"""classify(): the one rule for what an incoming file means for the stored document.

Both the folder scan (startup, re-ingest) and uploads use it.
"""

import pytest

from policypal.ingest.pipeline import classify
from policypal.models import Document

SHA_A = "a" * 64
SHA_B = "b" * 64
V1 = "model|chunker-v1"
V2 = "model|chunker-v2"


def stored(origin: str, sha: str = SHA_A, version: str = V1) -> Document:
    return Document(
        slug="leave-policy", origin=origin, content_sha256=sha, pipeline_version=version
    )


@pytest.mark.parametrize(
    ("existing", "incoming_origin", "sha", "version", "expected"),
    [
        (None, "sample", SHA_A, V1, "new"),
        (None, "upload", SHA_A, V1, "new"),
        (stored("sample"), "sample", SHA_A, V1, "same"),
        (stored("upload"), "upload", SHA_A, V1, "same"),
        (stored("upload"), "upload", SHA_A, V2, "new_pipeline"),
        (stored("upload"), "upload", SHA_B, V1, "new_content"),
        (stored("sample"), "sample", SHA_B, V1, "new_content"),
        # A sample file takes over a slug that an upload used first.
        (stored("upload"), "sample", SHA_B, V1, "new_content"),
        # "Sample wins": an upload never replaces a sample...
        (stored("sample"), "upload", SHA_B, V1, "sample_owns_slug"),
        (stored("sample"), "upload", SHA_B, V2, "sample_owns_slug"),
        # ...and identical bytes change nothing, even if the sample's vectors are older.
        (stored("sample"), "upload", SHA_A, V1, "same"),
        (stored("sample"), "upload", SHA_A, V2, "same"),
    ],
)
def test_classify(
    existing: Document | None, incoming_origin: str, sha: str, version: str, expected: str
) -> None:
    assert classify(existing, incoming_origin, sha, version) == expected  # type: ignore[arg-type]
