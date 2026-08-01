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


def _env_paths() -> tuple[Path, Path]:
    return (Path.cwd() / ".env", CONFIG_DIR / ".env")


def _load_env_files() -> None:
    """Load simple KEY=VALUE entries without adding a runtime dependency."""
    for path in _env_paths():
        if not path.exists():
            continue
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _env_value(name: str, default: str = "") -> str:
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else default


def _provider_config_from_dict(
    current: WebProviderConfig,
    values: dict,
) -> WebProviderConfig:
    return WebProviderConfig(
        enabled=bool(values.get("enabled", current.enabled)),
        api_key_env=str(values.get("api_key_env", current.api_key_env)),
        last_resort_only=bool(values.get("last_resort_only", current.last_resort_only)),
        automatic_merge=bool(values.get("automatic_merge", current.automatic_merge)),
        default_depth=str(values.get("default_depth", current.default_depth)),
        timeout_seconds=int(values.get("timeout_seconds", current.timeout_seconds)),
        cooldown_seconds=int(values.get("cooldown_seconds", current.cooldown_seconds)),
        local_request_limit=int(values.get("local_request_limit", current.local_request_limit)),
    )


@dataclass
class RuntimeLocationConfig:
    mode: str = "local"
    configured_country: str = ""
    configured_region: str = ""
    allow_network_lookup: bool = False


@dataclass
class RuntimeContextConfig:
    enabled: bool = True
    provider: str = "auto"
    refresh_seconds: int = 300
    command_timeout_seconds: int = 3
    max_prompt_characters: int = 3500
    include_workspace: bool = True
    include_git: bool = True
    include_displays: bool = True
    include_disks: bool = True
    include_local_ip: bool = True
    show_install_suggestion: bool = True
    location: RuntimeLocationConfig = field(default_factory=RuntimeLocationConfig)


@dataclass
class WebBillingConfig:
    mode: str = "prepaid_free_search_allowance"
    allow_paid_overage: bool = False
    allow_auto_recharge: bool = False


@dataclass
class WebSearchLocationConfig:
    enabled: bool = True
    use_runtime_country: bool = True
    send_country_for_local_intent_only: bool = True
    maximum_inferred_location_weight: float = 0.10


@dataclass
class WebSearchBehaviorConfig:
    max_query_rewrites: int = 3
    max_provider_fallbacks: int = 4
    max_total_search_calls: int = 6
    max_fetch_attempts: int = 4
    max_repeated_query_similarity: float = 0.90


@dataclass
class WebVerificationConfig:
    max_domains: int = 2
    max_pages_per_domain: int = 4
    max_total_verification_pages: int = 6
    same_domain_only: bool = True
    respect_robots: bool = True


@dataclass
class WebSearchConfig:
    strategy: str = "quality"
    stop_when_sufficient: bool = True
    skip_unconfigured_providers: bool = True
    fallback_on_quota: bool = True
    fallback_on_unavailable: bool = True
    fallback_on_low_relevance: bool = True
    return_unrelated_results: bool = False
    max_provider_attempts: int = 3
    max_results_per_domain: int = 2
    candidate_discovery_threshold: float = 0.38
    final_verification_threshold: float = 0.72
    minimum_relevance: float = 0.62
    strict_entity_relevance: float = 0.78
    minimum_authority: float = 0.45
    max_attempts_per_provider: int = 2
    base_retry_delay_ms: int = 500
    maximum_retry_delay_seconds: int = 10
    honor_retry_after: bool = True
    cache_enabled: bool = True
    max_disambiguation_queries: int = 4
    minimum_confident_entity_score: float = 0.68
    minimum_winner_margin: float = 0.18
    location: WebSearchLocationConfig = field(default_factory=WebSearchLocationConfig)
    behavior: WebSearchBehaviorConfig = field(default_factory=WebSearchBehaviorConfig)


@dataclass
class WebProviderConfig:
    enabled: bool = True
    api_key_env: str = ""
    last_resort_only: bool = False
    automatic_merge: bool = True
    default_depth: str = "basic"
    timeout_seconds: int = 20
    cooldown_seconds: int = 300
    local_request_limit: int = 950


def _default_web_providers() -> dict[str, WebProviderConfig]:
    return {
        "google": WebProviderConfig(api_key_env="GEMINI_API_KEY"),
        "parallel": WebProviderConfig(api_key_env="PARALLEL_API_KEY"),
        "tavily": WebProviderConfig(api_key_env="TAVILY_API_KEY"),
        "exa": WebProviderConfig(api_key_env="EXA_API_KEY"),
        "firecrawl": WebProviderConfig(api_key_env="FIRECRAWL_API_KEY"),
        "ddgs": WebProviderConfig(),
        "searxng": WebProviderConfig(last_resort_only=True, automatic_merge=False),
    }


@dataclass
class Config:
    tier: str = ""
    ollama_url: str = "http://localhost:11434"
    searxng_url: str = "http://localhost:8888"
    crawl4ai_url: str = ""  # empty = tier disabled, fall through to trafilatura
    crawl4ai_api_key: str = ""
    crawler_user_agent: str = "KlaudeBot/0.2 (+local documentation crawler)"
    web_provider: str = "quality"  # quality | auto | local | exa
    gemini_api_key: str = ""
    parallel_api_key: str = ""
    tavily_api_key: str = ""
    firecrawl_api_key: str = ""
    searxng_secret: str = ""
    exa_api_key: str = ""
    exa_base_url: str = "https://api.exa.ai"
    huggingface_api_key: str = ""
    huggingface_base_url: str = "https://huggingface.co"
    models: dict[str, str] = field(default_factory=dict)
    # permission policy per tool: ask | allow | deny
    permissions: dict[str, str] = field(default_factory=dict)
    max_agent_steps: int = 20
    retrieval_k: int = 6
    snapshot_retention: int = 3
    crawl_max_depth: int = 2
    crawl_max_pages: int = 50
    crawl_delay_min: float = 2.0
    crawl_delay_max: float = 5.0
    crawl_respect_robots: bool = True
    runtime_context: RuntimeContextConfig = field(default_factory=RuntimeContextConfig)
    web_billing: WebBillingConfig = field(default_factory=WebBillingConfig)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    web_verification: WebVerificationConfig = field(default_factory=WebVerificationConfig)
    web_providers: dict[str, WebProviderConfig] = field(default_factory=_default_web_providers)

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
    def docs_sources_dir(self) -> Path:
        p = self.data_dir / "docs-sources"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def skills_dir(self) -> Path:
        p = self.data_dir / "skills"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def sessions_db(self) -> Path:
        return self.data_dir / "sessions.db"

    @property
    def memory_file(self) -> Path:
        return self.data_dir / "memory.md"

    @property
    def runtime_context_cache_file(self) -> Path:
        return self.data_dir / "runtime-context.json"

    @property
    def web_provider_state_file(self) -> Path:
        return self.data_dir / "web-provider-state.json"

    @property
    def runtime_context_enabled(self) -> bool:
        return self.runtime_context.enabled

    @property
    def runtime_context_provider(self) -> str:
        return self.runtime_context.provider

    @property
    def runtime_context_refresh_seconds(self) -> int:
        return self.runtime_context.refresh_seconds

    @property
    def runtime_context_command_timeout_seconds(self) -> int:
        return self.runtime_context.command_timeout_seconds

    @property
    def runtime_context_max_prompt_characters(self) -> int:
        return self.runtime_context.max_prompt_characters

    @property
    def runtime_context_include_workspace(self) -> bool:
        return self.runtime_context.include_workspace

    @property
    def runtime_context_include_git(self) -> bool:
        return self.runtime_context.include_git

    @property
    def runtime_context_include_displays(self) -> bool:
        return self.runtime_context.include_displays

    @property
    def runtime_context_include_disks(self) -> bool:
        return self.runtime_context.include_disks

    @property
    def runtime_context_include_local_ip(self) -> bool:
        return self.runtime_context.include_local_ip

    @property
    def runtime_context_location_mode(self) -> str:
        return self.runtime_context.location.mode

    @property
    def runtime_context_location_country(self) -> str:
        return self.runtime_context.location.configured_country

    @property
    def runtime_context_location_region(self) -> str:
        return self.runtime_context.location.configured_region

    @property
    def runtime_context_location_allow_network(self) -> bool:
        return self.runtime_context.location.allow_network_lookup


DEFAULT_PERMISSIONS = {
    "run_shell": "ask",
    "write_file": "ask",
    "edit_file": "ask",
    "git_commit": "ask",
    # read-only tools are always allowed
    "read_file": "allow",
    "list_dir": "allow",
    "workspace_info": "allow",
    "grep": "allow",
    "git_status": "allow",
    "git_diff": "allow",
    "current_time": "allow",
    "weather_lookup": "allow",
    "web_search": "allow",
    "fetch_url": "allow",
    "code_search": "allow",
    "crawl_site": "ask",
    "huggingface_search": "allow",
    "huggingface_details": "allow",
    "huggingface_readme": "allow",
    "query_knowledge": "allow",
    "search_sessions": "allow",
    "list_recent_sessions": "allow",
    "list_commands": "allow",
    "remember_fact": "ask",
}


def load_config() -> Config:
    _load_env_files()
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
    cfg.crawl4ai_api_key = services.get(
        "crawl4ai_api_key",
        os.environ.get("CRAWL4AI_API_KEY", cfg.crawl4ai_api_key),
    )

    web = user.get("web", {})
    cfg.web_provider = web.get("provider", os.environ.get("KLAUDE_WEB_PROVIDER", cfg.web_provider))
    if cfg.web_provider not in {"quality", "local", "exa", "auto"}:
        raise ValueError("web.provider must be one of: quality, local, exa, auto")
    billing = web.get("billing", {})
    cfg.web_billing.mode = billing.get("mode", cfg.web_billing.mode)
    if cfg.web_billing.mode not in {
        "strict_zero_cost",
        "prepaid_free_search_allowance",
        "manual_paid_opt_in",
    }:
        raise ValueError(
            "web.billing.mode must be one of: strict_zero_cost, "
            "prepaid_free_search_allowance, manual_paid_opt_in"
        )
    cfg.web_billing.allow_paid_overage = bool(
        billing.get("allow_paid_overage", cfg.web_billing.allow_paid_overage)
    )
    cfg.web_billing.allow_auto_recharge = bool(
        billing.get("allow_auto_recharge", cfg.web_billing.allow_auto_recharge)
    )

    search = web.get("search", {})
    cfg.web_search.strategy = search.get("strategy", cfg.web_search.strategy)
    if cfg.web_search.strategy not in {"quality", "legacy"}:
        raise ValueError("web.search.strategy must be one of: quality, legacy")
    cfg.web_search.stop_when_sufficient = bool(
        search.get("stop_when_sufficient", cfg.web_search.stop_when_sufficient)
    )
    cfg.web_search.skip_unconfigured_providers = bool(
        search.get("skip_unconfigured_providers", cfg.web_search.skip_unconfigured_providers)
    )
    cfg.web_search.fallback_on_quota = bool(
        search.get("fallback_on_quota", cfg.web_search.fallback_on_quota)
    )
    cfg.web_search.fallback_on_unavailable = bool(
        search.get("fallback_on_unavailable", cfg.web_search.fallback_on_unavailable)
    )
    cfg.web_search.fallback_on_low_relevance = bool(
        search.get("fallback_on_low_relevance", cfg.web_search.fallback_on_low_relevance)
    )
    cfg.web_search.return_unrelated_results = bool(
        search.get("return_unrelated_results", cfg.web_search.return_unrelated_results)
    )
    cfg.web_search.max_provider_attempts = int(
        search.get("max_provider_attempts", cfg.web_search.max_provider_attempts)
    )
    cfg.web_search.max_results_per_domain = int(
        search.get("max_results_per_domain", cfg.web_search.max_results_per_domain)
    )
    search_relevance = search.get("relevance", {})
    cfg.web_search.candidate_discovery_threshold = float(
        search_relevance.get(
            "candidate_discovery_threshold",
            search.get(
                "candidate_discovery_threshold",
                cfg.web_search.candidate_discovery_threshold,
            ),
        )
    )
    cfg.web_search.final_verification_threshold = float(
        search_relevance.get(
            "final_verification_threshold",
            search.get(
                "final_verification_threshold",
                cfg.web_search.final_verification_threshold,
            ),
        )
    )
    cfg.web_search.minimum_relevance = float(
        search.get("minimum_relevance", cfg.web_search.minimum_relevance)
    )
    cfg.web_search.strict_entity_relevance = float(
        search_relevance.get(
            "strict_entity_threshold",
            search.get("strict_entity_relevance", cfg.web_search.strict_entity_relevance),
        )
    )
    cfg.web_search.minimum_authority = float(
        search.get("minimum_authority", cfg.web_search.minimum_authority)
    )
    cfg.web_search.max_attempts_per_provider = int(
        search.get("max_attempts_per_provider", cfg.web_search.max_attempts_per_provider)
    )
    cfg.web_search.base_retry_delay_ms = int(
        search.get("base_retry_delay_ms", cfg.web_search.base_retry_delay_ms)
    )
    cfg.web_search.maximum_retry_delay_seconds = int(
        search.get(
            "maximum_retry_delay_seconds",
            cfg.web_search.maximum_retry_delay_seconds,
        )
    )
    cfg.web_search.honor_retry_after = bool(
        search.get("honor_retry_after", cfg.web_search.honor_retry_after)
    )
    cfg.web_search.cache_enabled = bool(
        search.get("cache_enabled", cfg.web_search.cache_enabled)
    )
    cfg.web_search.max_disambiguation_queries = int(
        search.get("max_disambiguation_queries", cfg.web_search.max_disambiguation_queries)
    )
    cfg.web_search.minimum_confident_entity_score = float(
        search.get(
            "minimum_confident_entity_score",
            cfg.web_search.minimum_confident_entity_score,
        )
    )
    cfg.web_search.minimum_winner_margin = float(
        search.get("minimum_winner_margin", cfg.web_search.minimum_winner_margin)
    )
    search_location = search.get("location", {})
    cfg.web_search.location.enabled = bool(
        search_location.get("enabled", cfg.web_search.location.enabled)
    )
    cfg.web_search.location.use_runtime_country = bool(
        search_location.get(
            "use_runtime_country",
            cfg.web_search.location.use_runtime_country,
        )
    )
    cfg.web_search.location.send_country_for_local_intent_only = bool(
        search_location.get(
            "send_country_for_local_intent_only",
            cfg.web_search.location.send_country_for_local_intent_only,
        )
    )
    cfg.web_search.location.maximum_inferred_location_weight = float(
        search_location.get(
            "maximum_inferred_location_weight",
            cfg.web_search.location.maximum_inferred_location_weight,
        )
    )
    search_behavior = search.get("behavior", {})
    cfg.web_search.behavior.max_query_rewrites = int(
        search_behavior.get(
            "max_query_rewrites",
            cfg.web_search.behavior.max_query_rewrites,
        )
    )
    cfg.web_search.behavior.max_provider_fallbacks = int(
        search_behavior.get(
            "max_provider_fallbacks",
            cfg.web_search.behavior.max_provider_fallbacks,
        )
    )
    cfg.web_search.behavior.max_total_search_calls = int(
        search_behavior.get(
            "max_total_search_calls",
            cfg.web_search.behavior.max_total_search_calls,
        )
    )
    cfg.web_search.behavior.max_fetch_attempts = int(
        search_behavior.get(
            "max_fetch_attempts",
            cfg.web_search.behavior.max_fetch_attempts,
        )
    )
    cfg.web_search.behavior.max_repeated_query_similarity = float(
        search_behavior.get(
            "max_repeated_query_similarity",
            cfg.web_search.behavior.max_repeated_query_similarity,
        )
    )

    verification = web.get("verification", {})
    cfg.web_verification.max_domains = int(
        verification.get("max_domains", cfg.web_verification.max_domains)
    )
    cfg.web_verification.max_pages_per_domain = int(
        verification.get(
            "max_pages_per_domain",
            cfg.web_verification.max_pages_per_domain,
        )
    )
    cfg.web_verification.max_total_verification_pages = int(
        verification.get(
            "max_total_verification_pages",
            cfg.web_verification.max_total_verification_pages,
        )
    )
    cfg.web_verification.same_domain_only = bool(
        verification.get("same_domain_only", cfg.web_verification.same_domain_only)
    )
    cfg.web_verification.respect_robots = bool(
        verification.get("respect_robots", cfg.web_verification.respect_robots)
    )

    provider_values = web.get("providers", {})
    cfg.web_providers = {
        name: _provider_config_from_dict(
            current,
            provider_values.get(name, {}) if isinstance(provider_values, dict) else {},
        )
        for name, current in cfg.web_providers.items()
    }
    cfg.gemini_api_key = web.get("gemini_api_key", _env_value("GEMINI_API_KEY", cfg.gemini_api_key))
    cfg.parallel_api_key = web.get(
        "parallel_api_key",
        _env_value("PARALLEL_API_KEY", cfg.parallel_api_key),
    )
    cfg.tavily_api_key = web.get(
        "tavily_api_key",
        _env_value("TAVILY_API_KEY", cfg.tavily_api_key),
    )
    cfg.firecrawl_api_key = web.get(
        "firecrawl_api_key",
        _env_value("FIRECRAWL_API_KEY", cfg.firecrawl_api_key),
    )
    cfg.searxng_secret = web.get(
        "searxng_secret",
        _env_value("SEARXNG_SECRET", cfg.searxng_secret),
    )
    cfg.exa_api_key = web.get("exa_api_key", _env_value("EXA_API_KEY", cfg.exa_api_key))
    cfg.exa_base_url = web.get("exa_base_url", cfg.exa_base_url)

    huggingface = user.get("huggingface", {})
    cfg.huggingface_api_key = huggingface.get(
        "api_key",
        os.environ.get("HUGGINGFACE_API_KEY", cfg.huggingface_api_key),
    )
    cfg.huggingface_base_url = huggingface.get("base_url", cfg.huggingface_base_url)

    cfg.permissions = {**DEFAULT_PERMISSIONS, **user.get("permissions", {})}

    agent = user.get("agent", {})
    cfg.max_agent_steps = int(agent.get("max_steps", cfg.max_agent_steps))
    cfg.retrieval_k = int(agent.get("retrieval_k", cfg.retrieval_k))

    knowledge = user.get("knowledge", {})
    cfg.snapshot_retention = int(knowledge.get("snapshot_retention", cfg.snapshot_retention))

    crawler = user.get("crawler", {})
    cfg.crawler_user_agent = crawler.get("user_agent", cfg.crawler_user_agent)
    cfg.crawl_max_depth = int(crawler.get("max_depth", cfg.crawl_max_depth))
    cfg.crawl_max_pages = int(crawler.get("max_pages", cfg.crawl_max_pages))
    cfg.crawl_delay_min = float(crawler.get("delay_min", cfg.crawl_delay_min))
    cfg.crawl_delay_max = float(crawler.get("delay_max", cfg.crawl_delay_max))
    cfg.crawl_respect_robots = bool(crawler.get("respect_robots", cfg.crawl_respect_robots))

    runtime = user.get("runtime_context", {})
    cfg.runtime_context.enabled = bool(runtime.get("enabled", cfg.runtime_context.enabled))
    cfg.runtime_context.provider = runtime.get("provider", cfg.runtime_context.provider)
    if cfg.runtime_context.provider not in {"auto", "fastfetch", "neofetch", "native", "off"}:
        raise ValueError(
            "runtime_context.provider must be one of: auto, fastfetch, neofetch, native, off"
        )
    cfg.runtime_context.refresh_seconds = int(
        runtime.get("refresh_seconds", cfg.runtime_context.refresh_seconds)
    )
    cfg.runtime_context.command_timeout_seconds = int(
        runtime.get(
            "command_timeout_seconds",
            cfg.runtime_context.command_timeout_seconds,
        )
    )
    cfg.runtime_context.max_prompt_characters = int(
        runtime.get("max_prompt_characters", cfg.runtime_context.max_prompt_characters)
    )
    cfg.runtime_context.include_workspace = bool(
        runtime.get("include_workspace", cfg.runtime_context.include_workspace)
    )
    cfg.runtime_context.include_git = bool(
        runtime.get("include_git", cfg.runtime_context.include_git)
    )
    cfg.runtime_context.include_displays = bool(
        runtime.get("include_displays", cfg.runtime_context.include_displays)
    )
    cfg.runtime_context.include_disks = bool(
        runtime.get("include_disks", cfg.runtime_context.include_disks)
    )
    cfg.runtime_context.include_local_ip = bool(
        runtime.get("include_local_ip", cfg.runtime_context.include_local_ip)
    )
    cfg.runtime_context.show_install_suggestion = bool(
        runtime.get("show_install_suggestion", cfg.runtime_context.show_install_suggestion)
    )
    location = runtime.get("location", {})
    cfg.runtime_context.location.mode = location.get(
        "mode",
        cfg.runtime_context.location.mode,
    )
    if cfg.runtime_context.location.mode not in {"configured", "local", "network", "off"}:
        raise ValueError(
            "runtime_context.location.mode must be one of: configured, local, network, off"
        )
    cfg.runtime_context.location.configured_country = location.get(
        "configured_country",
        cfg.runtime_context.location.configured_country,
    )
    cfg.runtime_context.location.configured_region = location.get(
        "configured_region",
        cfg.runtime_context.location.configured_region,
    )
    cfg.runtime_context.location.allow_network_lookup = bool(
        location.get(
            "allow_network_lookup",
            cfg.runtime_context.location.allow_network_lookup,
        )
    )
    return cfg
