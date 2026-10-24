"""The CD workflow publishes the Docker image only for tested commits on main.

actionlint (make lint-workflows) checks the syntax; these tests pin the rules. Whether a
publish really works can only be seen on GitHub after a push to main.
"""

import yaml

from tests.helpers import REPO_ROOT

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CD = yaml.safe_load((WORKFLOWS / "cd.yml").read_text(encoding="utf-8"))
CI = yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
# PyYAML reads the key `on` as the boolean True.
TRIGGER = CD[True]
[JOB] = CD["jobs"].values()
STEPS = {step.get("uses", "").split("@")[0]: step for step in JOB["steps"]}


def test_it_runs_when_ci_finishes_on_main() -> None:
    assert TRIGGER == {
        "workflow_run": {"workflows": [CI["name"]], "types": ["completed"], "branches": ["main"]}
    }


def test_it_publishes_only_after_ci_passed_on_a_push_in_a_public_repository() -> None:
    condition = " ".join(JOB["if"].split())

    assert "github.event.workflow_run.conclusion == 'success'" in condition
    assert "github.event.workflow_run.event == 'push'" in condition
    assert "!github.event.repository.private" in condition


def test_it_builds_the_exact_commit_ci_tested() -> None:
    checkout = STEPS["actions/checkout"]

    assert checkout["with"]["ref"] == "${{ github.event.workflow_run.head_sha }}"


def test_the_image_is_tagged_with_the_commit_sha_and_latest() -> None:
    build = STEPS["docker/build-push-action"]["with"]
    tags = build["tags"].splitlines()

    assert build["push"] is True
    assert tags == [
        "${{ steps.image.outputs.name }}:${{ github.event.workflow_run.head_sha }}",
        "${{ steps.image.outputs.name }}:latest",
    ]
    assert "org.opencontainers.image.source=" in build["labels"]


def test_it_logs_in_with_the_built_in_token_and_needs_no_other_rights() -> None:
    login = STEPS["docker/login-action"]["with"]

    assert login["registry"] == "ghcr.io"
    assert login["password"] == "${{ secrets.GITHUB_TOKEN }}"
    assert CD["permissions"] == {"contents": "read", "packages": "write"}


def test_actions_are_pinned_to_a_version() -> None:
    for step in JOB["steps"]:
        if "uses" in step:
            assert "@v" in step["uses"], step["uses"]
