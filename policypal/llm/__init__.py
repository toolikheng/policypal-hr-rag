"""LLM providers: the prompt, the provider interface and the Ollama client."""

from dataclasses import dataclass

from policypal.config import Settings
from policypal.llm.base import LLMProvider, LLMStatus
from policypal.llm.ollama import OllamaProvider


@dataclass(frozen=True)
class LLMInfo:
    provider: str  # "ollama", or "extractive" when there is no LLM
    model: str | None
    status: LLMStatus


def build_llm(settings: Settings) -> LLMProvider | None:
    """The configured LLM, or None when LLM_PROVIDER=extractive (answers quote the policies).

    The fake LLM can't be chosen here: it exists only in the test suite.
    """
    if settings.llm_provider == "extractive":
        return None
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )


def describe_llm(llm: LLMProvider | None) -> LLMInfo:
    """Which LLM answers questions, and whether it is ready (checked now, for /health).

    No LLM means extractive mode, which is always ready.
    """
    if llm is None:
        return LLMInfo(provider="extractive", model=None, status="ok")
    return LLMInfo(provider=llm.name, model=llm.model, status=llm.status())
