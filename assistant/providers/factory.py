"""The client of a provider by its API (ASSISTANT-G35). No cache: a client is a key and an address, built for each
call from what the route read in that turn, so a changed key or policy applies to the next turn on every process
(the old product cleared a per-process cache on each change, ASSISTANT-G39)."""

from assistant.providers.anthropic import AnthropicProvider
from assistant.providers.base import Provider, ProviderUnavailable
from assistant.providers.deepseek import DeepSeekProvider
from assistant.providers.gemini import GeminiProvider
from assistant.providers.openai import OpenAIProvider

CLIENTS: dict[str, type[Provider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "deepseek": DeepSeekProvider,
}


def get_provider(*, kind: str, api_key: str, base_url: str) -> Provider:
    """The client of ``kind`` with ``api_key`` at ``base_url``; ``ProviderUnavailable`` without a key or for an
    unknown API."""
    client = CLIENTS.get(kind)
    if client is None:
        raise ProviderUnavailable(f"{kind}: no client for this API")
    return client(api_key=api_key, base_url=base_url)
