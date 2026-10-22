"""LLM providers: the prompt, the provider interface and the Ollama client."""

from policypal.config import Settings
from policypal.llm.base import LLMProvider
from policypal.llm.ollama import OllamaProvider


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
