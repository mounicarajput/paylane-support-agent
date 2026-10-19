"""Settings from environment variables, optionally loaded from a .env file."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Config:
    provider: str = "ollama"  # ollama (primary, open source) | anthropic (optional)
    ollama_model: str = "qwen2.5:7b"
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_timeout: int = 900  # seconds to wait for one reply; a 7B model on a laptop CPU can be slow
    ollama_keep_alive: str = "60m"  # keep the model loaded between messages (Ollama's default is 5 minutes)
    ollama_num_ctx: int = 4096  # how much text the model holds at once; smaller means less memory
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_api_key: str = ""
    temperature: float = 0.0
    seed: int = 7  # Ollama only; Anthropic has no seed
    max_tokens: int = 1024

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv(ROOT / ".env")
        env = os.environ.get
        return cls(
            provider=env("PROVIDER", "ollama").lower(),
            ollama_model=env("OLLAMA_MODEL", cls.ollama_model),
            ollama_host=env("OLLAMA_HOST", cls.ollama_host),
            ollama_timeout=int(env("OLLAMA_TIMEOUT", cls.ollama_timeout)),
            ollama_keep_alive=env("OLLAMA_KEEP_ALIVE", cls.ollama_keep_alive),
            ollama_num_ctx=int(env("OLLAMA_NUM_CTX", cls.ollama_num_ctx)),
            anthropic_model=env("ANTHROPIC_MODEL", cls.anthropic_model),
            anthropic_api_key=env("ANTHROPIC_API_KEY", ""),
            temperature=float(env("TEMPERATURE", cls.temperature)),
            seed=int(env("SEED", cls.seed)),
            max_tokens=int(env("MAX_TOKENS", cls.max_tokens)),
        )
