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

# Topics that no policy covers. The golden set asks about each one and expects a refusal.
UNCOVERED_TOPICS = {
    "bonus": r"\bbonus",
    "salary increments or pay reviews": r"increment|salary review|pay review|pay rise",
    "company car or car allowance": r"company car|car allowance|pool car",
    "gym or fitness membership": r"\bgym\b|fitness",
    "share or stock options": r"share option|stock option|share scheme|\bESOS\b",
    "childcare support": r"child ?care|nursery|creche",
    "long-service awards": r"long[- ]service",
    "relocation allowance": r"relocat",
    "sabbatical leave": r"sabbatical",
    "retirement": r"retire",
}

# The upload-demo policy's subject. The core set must not cover it, so the held-out
# document adds genuinely new information when it is uploaded.
HELD_OUT_TOPIC = r"\btraining\b|\bcourses?\b|training bond"
