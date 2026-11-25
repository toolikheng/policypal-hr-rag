"""Security floors for dependencies with known, fixed vulnerabilities.

The image scan (Trivy) is the real gate; these tests catch a downgrade before a build.
"""

import re
from importlib.metadata import version

from tests.helpers import REPO_ROOT

# pypdf 6.21.4 fixes ten HIGH CVEs found in 6.19.0 (PDF parsing of untrusted uploads).
PYPDF_FLOOR = (6, 21, 4)


def as_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def pinned_version(package: str) -> str:
    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(package)}==([\d.]+)\s*$", requirements, re.MULTILINE)
    assert match, f"{package} must be pinned with == in requirements.txt"
    return match.group(1)


def test_pypdf_is_pinned_at_or_above_the_security_floor() -> None:
    assert as_tuple(pinned_version("pypdf")) >= PYPDF_FLOOR


def test_the_installed_pypdf_matches_the_pin() -> None:
    assert version("pypdf") == pinned_version("pypdf")
