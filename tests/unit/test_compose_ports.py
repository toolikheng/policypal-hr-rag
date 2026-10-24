"""Which network interfaces docker-compose.yml publishes each service on.

By default everything is reachable only from this machine (127.0.0.1). BIND_ADDRESS can
open the API and the UI to the network on purpose; the database and Ollama stay local
whatever it says (Ollama has no authentication; the database has a demo password).
"""

import pytest
import yaml

from tests.helpers import ENV_EXAMPLE, REPO_ROOT

COMPOSE = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def published(service: str) -> list[str]:
    return COMPOSE["services"][service]["ports"]


@pytest.mark.parametrize("service", ["api", "ui"])
def test_api_and_ui_listen_on_bind_address_which_defaults_to_this_machine(service: str) -> None:
    [port] = published(service)

    assert port.startswith("${BIND_ADDRESS:-127.0.0.1}:"), port


@pytest.mark.parametrize("service", ["db", "ollama"])
def test_the_database_and_ollama_are_always_local_only(service: str) -> None:
    [port] = published(service)

    assert port.startswith("127.0.0.1:"), port


def test_every_published_port_names_an_interface() -> None:
    # A bare "8000:8000" would mean every interface (0.0.0.0).
    for name, service in COMPOSE["services"].items():
        for port in service.get("ports", []):
            assert port.startswith(("127.0.0.1:", "${BIND_ADDRESS:-127.0.0.1}:")), name


def test_env_example_keeps_api_and_ui_local() -> None:
    assert "\nBIND_ADDRESS=127.0.0.1\n" in ENV_EXAMPLE.read_text(encoding="utf-8")
