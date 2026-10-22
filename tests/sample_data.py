"""Paths and facts about the committed sample policies, shared by several test modules."""

from policypal.ingest.pipeline import SAMPLE_POLICIES_DIR

POLICY_DIR = SAMPLE_POLICIES_DIR
UPLOAD_DEMO_DIR = SAMPLE_POLICIES_DIR.parent / "upload-demo"

FICTIONAL_LABEL = "FICTIONAL SAMPLE DATA — NOT A REAL COMPANY POLICY"

CORE_POLICY_SLUGS = [
    "leave-policy",
    "medical-claims-policy",
    "overtime-policy",
    "expense-claims-policy",
    "travel-policy",
    "code-of-conduct",
    "probation-and-confirmation-policy",
    "work-from-home-policy",
]
UPLOAD_DEMO_SLUG = "training-and-development-policy"

CORE_POLICIES = [POLICY_DIR / f"{slug}.md" for slug in CORE_POLICY_SLUGS]
UPLOAD_DEMO_POLICY = UPLOAD_DEMO_DIR / f"{UPLOAD_DEMO_SLUG}.md"
ALL_POLICIES = [*CORE_POLICIES, UPLOAD_DEMO_POLICY]
