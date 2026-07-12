"""klaude-code configuration.

Precedence: ~/.config/klaude/config.toml overrides built-in defaults.
Hardware tiers map to model presets so the same repo runs on any machine.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("KLAUDE_CONFIG_DIR", Path.home() / ".config" / "klaude"))
DATA_DIR = Path(os.environ.get("KLAUDE_DATA_DIR", Path.home() / ".local" / "share" / "klaude"))

TIER_PRESETS: dict[str, dict[str, str]] = {
    # <=8 GB RAM, no usable GPU
    "lite": {
        "coder": "qwen3:4b",
        "fast": "qwen3:1.7b",
        "vision": "",  # disabled
        "embed": "nomic-embed-text",
    },
    # ~16 GB RAM
    "standard": {
        "coder": "gpt-oss:20b",
        "fast": "qwen3:4b",
        "vision": "minicpm-v",
        "embed": "nomic-embed-text",
    },
    # 32 GB+ RAM (the Dell G5 tier)
    "full": {
        "coder": "qwen3-coder:30b",
        "fast": "qwen3:4b",
        "vision": "minicpm-v",
        "embed": "nomic-embed-text",
    },
}


def detect_tier() -> str:
    """Pick a tier from total system RAM."""
    try:
        with open("/proc/meminfo") as f:
            kb = int(next(line for line in f if line.startswith("MemTotal")).split()[1])
        gb = kb / 1024 / 1024
    except (OSError, StopIteration, ValueError):
        return "standard"
    if gb >= 28:
        return "full"
    if gb >= 12:
        return "standard"
    return "lite"


@dataclass
class Config:
    tier: str = ""
    ollama_url: str = "http://localhost:11434"
    searxng_url: str = "http://localhost:8888"
    crawl4ai_url: str = ""  # empty = tier disabled, fall through to trafilatura
    models: dict[str, str] = field(default_factory=dict)
    # permission policy per tool: ask | allow | deny
    permissions: dict[str, str] = field(default_factory=dict)
    max_agent_steps: int = 20
    retrieval_k: int = 6

    @property
    def data_dir(self) -> Path:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DATA_DIR

    @property
    def knowledge_dir(self) -> Path:
        p = self.data_dir / "knowledge.lance"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def docs_cache_dir(self) -> Path:
        p = self.data_dir / "docs-cache"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def sessions_db(self) -> Path:
        return self.data_dir / "sessions.db"

    @property
    def memory_file(self) -> Path:
        return self.data_dir / "memory.md"


DEFAULT_PERMISSIONS = {
    "run_shell": "ask",
    "write_file": "ask",
    "edit_file": "ask",
    "git_commit": "ask",
    # read-only tools are always allowed
    "read_file": "allow",
    "list_dir": "allow",
    "grep": "allow",
    "git_status": "allow",
    "git_diff": "allow",
    "web_search": "allow",
    "fetch_url": "allow",
    "query_knowledge": "allow",
}


def load_config() -> Config:
    cfg = Config()
    user: dict = {}
    path = CONFIG_DIR / "config.toml"
    if path.exists():
        with open(path, "rb") as f:
            user = tomllib.load(f)

    cfg.tier = user.get("models", {}).get("tier") or detect_tier()
    preset = dict(TIER_PRESETS.get(cfg.tier, TIER_PRESETS["standard"]))
    preset.update(user.get("models", {}).get("override", {}))
    cfg.models = preset

    services = user.get("services", {})
    cfg.ollama_url = services.get("ollama_url", cfg.ollama_url)
    cfg.searxng_url = services.get("searxng_url", cfg.searxng_url)
    cfg.crawl4ai_url = services.get("crawl4ai_url", cfg.crawl4ai_url)

    cfg.permissions = {**DEFAULT_PERMISSIONS, **user.get("permissions", {})}

    agent = user.get("agent", {})
    cfg.max_agent_steps = int(agent.get("max_steps", cfg.max_agent_steps))
    cfg.retrieval_k = int(agent.get("retrieval_k", cfg.retrieval_k))
    return cfg
