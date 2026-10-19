from ..config import Config
from .base import Provider, ProviderError


def get_provider(config: Config) -> Provider:
    if config.provider == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider(config.ollama_model, config.ollama_host, config.temperature,
                              config.seed, config.max_tokens, config.ollama_timeout, config.ollama_keep_alive)
    if config.provider == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(config.anthropic_model, config.anthropic_api_key,
                                 config.temperature, config.max_tokens)
    raise ProviderError(f"Unknown PROVIDER '{config.provider}'. Use 'ollama' or 'anthropic'.")
