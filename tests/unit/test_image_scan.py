"""The image vulnerability gate (Trivy) and the scanned-image-only publish.

The scripts are run here against a fake `docker` command on PATH, so the tests need no
Docker, network or registry. Whether the real gate works is seen in CI and CD runs.
"""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.helpers import REPO_ROOT

SCAN = REPO_ROOT / "scripts" / "scan-image.sh"
PUSH = REPO_ROOT / "scripts" / "push-image.sh"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CI = yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
CD = yaml.safe_load((WORKFLOWS / "cd.yml").read_text(encoding="utf-8"))
MAKEFILE = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

TRIVY = (
    "aquasec/trivy:0.75.0"
    "@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa"
)
GATE = ["--severity", "HIGH,CRITICAL", "--ignore-unfixed", "--scanners", "vuln", "--exit-code", "1"]

SCANNED_ID = "sha256:" + "a" * 64
OTHER_ID = "sha256:" + "b" * 64
PUSHED_DIGEST = "sha256:" + "c" * 64
NAME = "ghcr.io/owner/policypal"

# A stand-in for `docker`: logs every call, answers from environment variables.
FAKE_DOCKER = """#!/bin/sh
echo "$*" >> "$FAKE_LOG"
case "$1 $2" in
  "image inspect")
    case "$4" in
      "{{.Id}}") echo "$FAKE_LOCAL_ID" ;;
      *) echo "$FAKE_REPO_DIGESTS" ;;
    esac ;;
  "buildx imagetools") echo "$FAKE_REMOTE_DIGEST" ;;
  "run "*) exit "${FAKE_SCAN_EXIT:-0}" ;;
esac
"""


def run_script(script: Path, *args: str, tmp_path: Path, **fake: str) -> tuple[int, list[str], str]:
    """Run a script with the fake docker; return its exit code, docker calls and stderr."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(0o755)
    log = tmp_path / "docker.log"
    log.touch()
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "FAKE_LOG": str(log),
        **fake,
    }
    result = subprocess.run(
        ["sh", str(script), *args], env=env, capture_output=True, text=True, check=False
    )
    return result.returncode, log.read_text(encoding="utf-8").splitlines(), result.stderr


def push(tmp_path: Path, **fake: str) -> tuple[int, list[str], str]:
    defaults = {
        "FAKE_LOCAL_ID": SCANNED_ID,
        "FAKE_REPO_DIGESTS": f"other/repo@{OTHER_ID} {NAME}@{PUSHED_DIGEST}",
        "FAKE_REMOTE_DIGEST": PUSHED_DIGEST,
    }
    return run_script(
        PUSH, SCANNED_ID, f"{NAME}:abc123", f"{NAME}:latest", tmp_path=tmp_path, **defaults | fake
    )


# --- scan-image.sh -------------------------------------------------------------------


def test_the_scan_runs_the_pinned_trivy_with_the_gate_settings(tmp_path: Path) -> None:
    code, calls, _ = run_script(SCAN, SCANNED_ID, tmp_path=tmp_path)

    assert code == 0
    [call] = calls
    args = call.split()
    assert args[:2] == ["run", "--rm"]
    assert TRIVY in args
    after_trivy = args[args.index(TRIVY) + 1 :]
    assert after_trivy == ["image", *GATE, SCANNED_ID]


def test_the_scan_fails_when_trivy_finds_a_fixable_vulnerability(tmp_path: Path) -> None:
    code, _, _ = run_script(SCAN, SCANNED_ID, tmp_path=tmp_path, FAKE_SCAN_EXIT="1")

    assert code == 1


def test_the_scan_needs_exactly_one_image(tmp_path: Path) -> None:
    code, calls, stderr = run_script(SCAN, tmp_path=tmp_path)

    assert code == 2
    assert stderr.startswith("usage: sh scripts/scan-image.sh")
    assert calls == []


# --- push-image.sh -------------------------------------------------------------------


def test_the_push_sends_every_tag_of_the_scanned_image_and_checks_each(tmp_path: Path) -> None:
    code, calls, _ = push(tmp_path)

    assert code == 0
    assert [c for c in calls if c.startswith("push ")] == [
        f"push {NAME}:abc123",
        f"push {NAME}:latest",
    ]
    assert sum(c.startswith("buildx imagetools inspect") for c in calls) == 2
    assert not [c for c in calls if c.startswith(("build ", "buildx build"))]


def test_nothing_is_pushed_when_a_tag_is_not_the_scanned_image(tmp_path: Path) -> None:
    code, calls, stderr = push(tmp_path, FAKE_LOCAL_ID=OTHER_ID)

    assert code == 1
    assert "not the scanned image" in stderr
    assert not [c for c in calls if c.startswith("push ")]


def test_the_push_fails_when_the_registry_has_a_different_image(tmp_path: Path) -> None:
    code, _, stderr = push(tmp_path, FAKE_REMOTE_DIGEST=OTHER_ID)

    assert code == 1
    assert "registry" in stderr


def test_the_push_fails_when_docker_recorded_no_digest_for_the_repository(
    tmp_path: Path,
) -> None:
    code, _, stderr = push(tmp_path, FAKE_REPO_DIGESTS=f"other/repo@{PUSHED_DIGEST}")

    assert code == 1
    assert "no pushed digest" in stderr


@pytest.mark.parametrize("args", [[], [SCANNED_ID]])
def test_the_push_needs_an_image_id_and_at_least_one_tag(tmp_path: Path, args: list[str]) -> None:
    code, calls, stderr = run_script(PUSH, *args, tmp_path=tmp_path)

    assert code == 2
    assert stderr.startswith("usage: sh scripts/push-image.sh")
    assert calls == []


# --- the workflows and the Makefile ----------------------------------------------------


def steps_by_action(job: dict) -> dict[str, dict]:
    return {s["uses"].split("@")[0]: s for s in job["steps"] if "uses" in s}


def run_lines(job: dict) -> str:
    return "\n".join(s.get("run", "") for s in job["steps"])


def assert_builds_once_into_docker_without_cache_for_runtime(job: dict) -> dict:
    builds = [s for s in job["steps"] if "docker/build-push-action" in s.get("uses", "")]
    assert len(builds) == 1, "exactly one build: a second build would make a different image"
    [build] = builds
    assert build["with"]["load"] is True
    assert build["with"].get("push", False) is False
    assert build["with"]["no-cache-filters"] == "runtime"
    assert "buildx build" not in run_lines(job)
    assert "docker build" not in run_lines(job)
    return build


def test_ci_builds_the_image_and_scans_it() -> None:
    job = CI["jobs"]["image-scan"]
    build = assert_builds_once_into_docker_without_cache_for_runtime(job)
    [tag] = build["with"]["tags"].splitlines()

    assert "docker/setup-buildx-action" in steps_by_action(job)
    assert f"sh scripts/scan-image.sh {tag}" in run_lines(job)


def test_cd_scans_and_pushes_one_image_id_taken_from_docker_after_the_build() -> None:
    [job] = CD["jobs"].values()
    steps = job["steps"]
    build = assert_builds_once_into_docker_without_cache_for_runtime(job)
    tags = build["with"]["tags"].splitlines()
    # Docker's own ID for the loaded image (the build's `imageid` output is the config
    # digest, which is not Docker's image ID with the containerd image store).
    image_id = "${{ steps.local-image.outputs.id }}"
    [local_image] = [s for s in steps if s.get("id") == "local-image"]
    [scan] = [s for s in steps if "scripts/scan-image.sh" in s.get("run", "")]
    [publish] = [s for s in steps if "scripts/push-image.sh" in s.get("run", "")]

    assert f"docker image inspect --format '{{{{.Id}}}}' \"{tags[0]}\"" in local_image["run"]
    assert scan["run"].strip() == f"sh scripts/scan-image.sh {image_id}"
    assert " ".join(publish["run"].split()) == " ".join(
        ["sh", "scripts/push-image.sh", image_id, *tags]
    )
    assert steps.index(build) < steps.index(local_image) < steps.index(scan) < steps.index(publish)


def test_make_image_scan_builds_runtime_without_the_cache_and_scans() -> None:
    target = MAKEFILE.split("\nimage-scan:", 1)[1].split("\n\n", 1)[0]

    assert "--no-cache-filter runtime" in target
    assert "sh scripts/scan-image.sh" in target
