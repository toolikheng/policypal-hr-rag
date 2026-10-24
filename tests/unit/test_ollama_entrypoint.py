"""docker/ollama-entrypoint.sh, run against a stand-in `ollama` command (no Docker, no model)."""

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from tests.helpers import REPO_ROOT

SCRIPT = REPO_ROOT / "docker" / "ollama-entrypoint.sh"

# Records each call. `serve` fails or runs until stopped; `show` succeeds only if the
# model is "downloaded".
STUB = """#!/bin/sh
echo "$*" >> "$STUB_LOG"
case "$1" in
  serve) [ "$STUB_SERVE" = fail ] && exit 1; exec sleep 30 ;;
  list) [ "$STUB_SERVE" = fail ] && exit 1; exit 0 ;;
  show) [ "$STUB_HAS_MODEL" = yes ] && exit 0; exit 1 ;;
  pull) exit 0 ;;
esac
"""


def start(tmp_path: Path, *, serve: str = "ok", has_model: str = "yes") -> subprocess.Popen:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "ollama"
    stub.write_text(STUB)
    stub.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "PULL_MODEL": "llama3.2:3b",
        "STUB_LOG": str(tmp_path / "calls.log"),
        "STUB_SERVE": serve,
        "STUB_HAS_MODEL": has_model,
    }
    return subprocess.Popen(["sh", str(SCRIPT)], env=env, stderr=subprocess.PIPE, text=True)


def calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def wait_for_call(tmp_path: Path, prefix: str, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not any(call.startswith(prefix) for call in calls(tmp_path)):
        assert time.monotonic() < deadline, f"no '{prefix}' call; calls: {calls(tmp_path)}"
        time.sleep(0.05)


def stop(process: subprocess.Popen) -> int:
    process.send_signal(signal.SIGTERM)
    return process.wait(timeout=5)


def test_exits_with_an_error_if_the_server_does_not_start(tmp_path: Path) -> None:
    process = start(tmp_path, serve="fail")

    try:
        exit_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        pytest.fail("the script kept waiting for a server that had already stopped")

    assert exit_code != 0
    assert "did not start" in process.stderr.read()  # type: ignore[union-attr]


def test_a_downloaded_model_is_not_downloaded_again(tmp_path: Path) -> None:
    process = start(tmp_path, has_model="yes")
    wait_for_call(tmp_path, "show")

    assert stop(process) == 0
    assert not any(call.startswith("pull") for call in calls(tmp_path))


def test_a_missing_model_is_downloaded_once(tmp_path: Path) -> None:
    process = start(tmp_path, has_model="no")
    wait_for_call(tmp_path, "pull")

    assert stop(process) == 0
    assert [call for call in calls(tmp_path) if call.startswith("pull")] == ["pull llama3.2:3b"]
