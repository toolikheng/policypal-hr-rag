"""Rules for the Dockerfile: cached dependencies, an always-fresh runtime stage.

Docker reuses a cached step while its text is unchanged, so `apt-get upgrade` in a cached
step would never pick up new Debian security fixes. The slow dependency stage stays
cached; the runtime stage, which upgrades the OS packages, is built without the cache.
"""

import re

import yaml

from tests.helpers import REPO_ROOT

DOCKERFILE = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
CD = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "cd.yml").read_text(encoding="utf-8"))
FROM_LINE = re.compile(r"^FROM\s+(\S+)\s+AS\s+(\S+)\s*$", re.MULTILINE | re.IGNORECASE)


def instructions(text: str) -> list[str]:
    """Each instruction on one line (continuations joined), comments dropped."""
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    return [" ".join(i.split()) for i in "\n".join(lines).replace("\\\n", " ").splitlines() if i]


def stages() -> dict[str, tuple[str, list[str]]]:
    """Stage name -> (parent image or stage, its instructions after FROM)."""
    matches = list(FROM_LINE.finditer(DOCKERFILE))
    result = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(DOCKERFILE)
        result[match.group(2)] = (match.group(1), instructions(DOCKERFILE[match.end() : end]))
    return result


STAGES = stages()


def runs(stage: str) -> str:
    return " ".join(i for i in STAGES[stage][1] if i.startswith("RUN "))


def test_every_stage_is_named_and_runtime_is_the_final_image() -> None:
    assert len(STAGES) == DOCKERFILE.count("\nFROM ") + DOCKERFILE.startswith("FROM ")
    assert list(STAGES)[-1] == "runtime"


def test_dependencies_and_runtime_share_one_pinned_base_image() -> None:
    base_image, _ = STAGES["base"]

    assert re.fullmatch(r"python:\d+\.\d+\.\d+-slim-\w+", base_image)
    assert STAGES["deps"][0] == "base"
    assert STAGES["runtime"][0] == "base"


def test_the_dependency_stage_installs_requirements_and_refuses_cuda() -> None:
    deps = runs("deps")

    assert "pip install -r requirements.txt" in deps
    assert "torch.version.cuda" in deps
    assert "grep -i '^nvidia'" in deps
    assert "SentenceTransformer(" in deps


def test_the_runtime_stage_upgrades_debian_packages_first() -> None:
    first_run = next(i for i in STAGES["runtime"][1] if i.startswith("RUN "))

    assert "apt-get update" in first_run
    assert "apt-get upgrade -y" in first_run
    assert "rm -rf /var/lib/apt/lists/*" in first_run


def test_the_runtime_stage_copies_dependencies_instead_of_installing_them() -> None:
    runtime = STAGES["runtime"][1]

    assert "pip install" not in runs("runtime")
    assert "COPY --from=deps /usr/local /usr/local" in runtime
    assert "COPY --from=deps /opt/huggingface /opt/huggingface" in runtime


def test_the_runtime_stage_is_offline_and_runs_as_a_normal_user() -> None:
    runtime = " ".join(STAGES["runtime"][1])

    assert "HF_HUB_OFFLINE=1" in runtime
    assert "USER policypal" in runtime
    assert 'CMD ["sh", "docker/api-entrypoint.sh"]' in runtime


def test_the_image_never_copies_the_whole_build_context() -> None:
    copies = [i.split()[1:] for _, body in STAGES.values() for i in body if i.startswith("COPY ")]
    # Everything but --flags and the last argument (the destination) is a source.
    sources = [arg for args in copies for arg in args[:-1] if not arg.startswith("--")]

    assert "requirements.txt" in sources
    assert "." not in sources
    assert "./" not in sources


def test_cd_builds_the_runtime_stage_without_the_cache() -> None:
    [job] = CD["jobs"].values()
    [build] = [s for s in job["steps"] if "docker/build-push-action" in s.get("uses", "")]

    assert build["with"]["no-cache-filters"] == "runtime"
    assert build["with"].get("target", "runtime") == "runtime"
