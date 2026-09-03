import os

import klaude_core.config as config_module
from klaude_core.config import load_config


def test_source_root_resolves_visible_config_and_portable_data_dirs(tmp_path, monkeypatch):
    source_root = tmp_path / "klaude-code"
    monkeypatch.delenv("KLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("KLAUDE_DATA_DIR", raising=False)
    monkeypatch.delenv("KLAUDE_HOME", raising=False)
    monkeypatch.setattr(config_module, "SOURCE_ROOT", source_root)
    monkeypatch.setattr(config_module, "KLAUDE_HOME", source_root / ".klaude")

    assert config_module._resolve_config_dir() == source_root / "config"
    assert config_module._resolve_data_dir() == source_root / ".klaude" / "data"


def test_explicit_klaude_home_relocates_config_and_data_dirs(tmp_path, monkeypatch):
    home = tmp_path / "portable-home"
    monkeypatch.delenv("KLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("KLAUDE_DATA_DIR", raising=False)
    monkeypatch.setenv("KLAUDE_HOME", str(home))
    monkeypatch.setattr(config_module, "KLAUDE_HOME", home)

    assert config_module._resolve_config_dir() == home / "config"
    assert config_module._resolve_data_dir() == home / "data"


def test_explicit_config_and_data_dirs_override_klaude_home(tmp_path, monkeypatch):
    home = tmp_path / ".klaude"
    config_dir = tmp_path / "custom-config"
    data_dir = tmp_path / "custom-data"
    monkeypatch.setattr(config_module, "KLAUDE_HOME", home)
    monkeypatch.setenv("KLAUDE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("KLAUDE_DATA_DIR", str(data_dir))

    assert config_module._resolve_config_dir() == config_dir
    assert config_module._resolve_data_dir() == data_dir


def test_load_config_reads_ollama_runtime_options(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[ollama.options]\n"
        "num_ctx = 8192\n"
        "num_thread = 6\n"
        "num_gpu = 0\n"
        "num_predict = 4096\n"
        "\n[agent]\n"
        "max_code_continuations = 2\n"
    )
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DATA_DIR", data_dir)

    cfg = load_config()

    assert cfg.ollama_options == {
        "num_ctx": 8192,
        "num_thread": 6,
        "num_gpu": 0,
        "num_predict": 4096,
    }
    assert cfg.max_code_continuations == 2


def test_small_qwen_defaults_to_non_thinking_and_allows_override(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DATA_DIR", data_dir)

    cfg = load_config()
    assert cfg.ollama_think_for_model("qwen3.5:4b") is False
    assert cfg.ollama_think_for_model("qwen3-coder:30b") is None

    (config_dir / "config.toml").write_text("[ollama]\nthink = true\n")
    assert load_config().ollama_think_for_model("qwen3.5:4b") is True


def test_env_paths_ignore_unrelated_workdir_dotenv_when_source_root_is_known(
    tmp_path,
    monkeypatch,
):
    config_dir = tmp_path / ".klaude" / "config"
    source_root = tmp_path / "klaude-code"
    workdir = tmp_path / "app"
    config_dir.mkdir(parents=True)
    source_root.mkdir()
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "SOURCE_ROOT", source_root)

    paths = config_module._env_paths()

    assert config_dir / ".env" in paths
    assert source_root / ".env" in paths
    assert workdir / ".env" not in paths


def test_load_config_reads_dotenv_for_provider_keys(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DATA_DIR", data_dir)
    monkeypatch.delenv("CRAWL4AI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("HUGGINGFACE_API_KEY", raising=False)
    monkeypatch.delenv("KLAUDE_WEB_PROVIDER", raising=False)
    (config_dir / ".env").write_text(
        "CRAWL4AI_API_KEY=crawl4ai-from-dotenv\n"
        "GEMINI_API_KEY=gemini-from-dotenv\n"
        "PARALLEL_API_KEY=parallel-from-dotenv\n"
        "TAVILY_API_KEY=tavily-from-dotenv\n"
        "EXA_API_KEY=from-dotenv\n"
        "FIRECRAWL_API_KEY=firecrawl-from-dotenv\n"
        "HUGGINGFACE_API_KEY=huggingface-from-dotenv\n"
        "KLAUDE_WEB_PROVIDER=auto\n"
    )

    cfg = load_config()

    assert cfg.crawl4ai_api_key == "crawl4ai-from-dotenv"
    assert cfg.gemini_api_key == "gemini-from-dotenv"
    assert cfg.parallel_api_key == "parallel-from-dotenv"
    assert cfg.tavily_api_key == "tavily-from-dotenv"
    assert cfg.exa_api_key == "from-dotenv"
    assert cfg.firecrawl_api_key == "firecrawl-from-dotenv"
    assert cfg.huggingface_api_key == "huggingface-from-dotenv"
    assert cfg.web_provider == "auto"
    os.environ.pop("CRAWL4AI_API_KEY", None)
    os.environ.pop("GEMINI_API_KEY", None)
    os.environ.pop("PARALLEL_API_KEY", None)
    os.environ.pop("TAVILY_API_KEY", None)
    os.environ.pop("EXA_API_KEY", None)
    os.environ.pop("FIRECRAWL_API_KEY", None)
    os.environ.pop("HUGGINGFACE_API_KEY", None)
    os.environ.pop("KLAUDE_WEB_PROVIDER", None)


def test_config_dir_dotenv_precedes_project_dotenv(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(config_module, "SOURCE_ROOT", tmp_path)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    (config_dir / ".env").write_text("EXA_API_KEY=from-config-dotenv\n")
    (tmp_path / ".env").write_text("EXA_API_KEY=from-project-dotenv\n")

    cfg = load_config()

    assert cfg.exa_api_key == "from-config-dotenv"
    assert cfg.config_file == config_dir / "config.toml"


def test_exa_api_key_uses_project_dotenv_before_provider_construction(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(config_module, "SOURCE_ROOT", tmp_path)
    monkeypatch.setenv("EXA_API_KEY", "stale-shell-key")
    (tmp_path / ".env").write_text("EXA_API_KEY=  from-project-dotenv  # comment\n")

    cfg = load_config()

    assert cfg.exa_api_key == "from-project-dotenv"

    from klaude_web.providers import ProviderRegistry

    provider = ProviderRegistry(cfg).providers["exa"]
    assert provider.api_key() == "from-project-dotenv"


def test_tavily_api_key_uses_project_dotenv_before_provider_construction(
    tmp_path,
    monkeypatch,
):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(config_module, "SOURCE_ROOT", tmp_path)
    monkeypatch.setenv("TAVILY_API_KEY", "stale-shell-key")
    (tmp_path / ".env").write_text("TAVILY_API_KEY=  from-project-tavily  # comment\n")

    cfg = load_config()

    assert cfg.tavily_api_key == "from-project-tavily"

    from klaude_web.providers import ProviderRegistry

    provider = ProviderRegistry(cfg).providers["tavily"]
    assert provider.api_key() == "from-project-tavily"


def test_firecrawl_api_key_uses_project_dotenv_before_provider_construction(
    tmp_path,
    monkeypatch,
):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(config_module, "SOURCE_ROOT", tmp_path)
    monkeypatch.setenv("FIRECRAWL_API_KEY", "stale-shell-key")
    (tmp_path / ".env").write_text(
        "FIRECRAWL_API_KEY=  from-project-firecrawl  # comment\n"
    )

    cfg = load_config()

    assert cfg.firecrawl_api_key == "from-project-firecrawl"

    from klaude_web.providers import ProviderRegistry

    provider = ProviderRegistry(cfg).providers["firecrawl"]
    assert provider.api_key() == "from-project-firecrawl"


def test_exa_api_key_does_not_read_alternative_env_names(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(config_module, "SOURCE_ROOT", tmp_path)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setenv("EXA_KEY", "wrong")
    monkeypatch.setenv("EXA_TOKEN", "wrong")

    cfg = load_config()

    assert cfg.exa_api_key == ""


def test_load_config_reads_runtime_context_section(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[runtime_context]\n"
        "provider = 'native'\n"
        "refresh_seconds = 42\n"
        "include_local_ip = false\n"
        "\n"
        "[runtime_context.location]\n"
        "mode = 'configured'\n"
        "configured_country = 'KH'\n"
        "configured_region = 'Phnom Penh region'\n"
    )
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DATA_DIR", data_dir)

    cfg = load_config()

    assert cfg.runtime_context_provider == "native"
    assert cfg.runtime_context_refresh_seconds == 42
    assert cfg.runtime_context_include_local_ip is False
    assert cfg.runtime_context_location_mode == "configured"
    assert cfg.runtime_context_location_country == "KH"
    assert cfg.runtime_context_location_region == "Phnom Penh region"


def test_load_config_reads_web_search_provider_sections(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[web]\n"
        "provider = 'quality'\n"
        "\n"
        "[web.billing]\n"
        "mode = 'strict_zero_cost'\n"
        "allow_paid_overage = false\n"
        "allow_auto_recharge = false\n"
        "\n"
        "[web.search]\n"
        "minimum_relevance = 0.7\n"
        "strict_entity_relevance = 0.85\n"
        "max_results_per_domain = 1\n"
        "provider_order = ['exa', 'searxng']\n"
        "allow_explicit_provider_fallback = true\n"
        "cache_enabled = false\n"
        "max_disambiguation_queries = 3\n"
        "minimum_confident_entity_score = 0.71\n"
        "minimum_winner_margin = 0.2\n"
        "\n"
        "[web.search.relevance]\n"
        "candidate_discovery_threshold = 0.39\n"
        "final_verification_threshold = 0.73\n"
        "strict_entity_threshold = 0.86\n"
        "\n"
        "[web.search.location]\n"
        "enabled = true\n"
        "use_runtime_country = true\n"
        "send_country_for_local_intent_only = true\n"
        "maximum_inferred_location_weight = 0.08\n"
        "\n"
        "[web.search.behavior]\n"
        "max_query_rewrites = 2\n"
        "max_provider_fallbacks = 3\n"
        "max_web_actions = 7\n"
        "max_search_calls = 3\n"
        "max_fetch_calls = 5\n"
        "max_pages_per_domain = 2\n"
        "max_consecutive_failures = 2\n"
        "max_total_search_calls = 4\n"
        "max_fetch_attempts = 2\n"
        "max_repeated_query_similarity = 0.85\n"
        "\n"
        "[web.fetch]\n"
        "timeout_seconds = 12\n"
        "max_download_bytes = 750000\n"
        "max_content_characters = 16000\n"
        "max_redirects = 3\n"
        "cache_ttl_seconds = 7200\n"
        "\n"
        "[web.verification]\n"
        "max_domains = 3\n"
        "max_pages_per_domain = 5\n"
        "max_total_verification_pages = 7\n"
        "same_domain_only = true\n"
        "respect_robots = false\n"
        "\n"
        "[web.providers.google]\n"
        "enabled = false\n"
        "api_key_env = 'GEMINI_API_KEY'\n"
        "\n"
        "[web.providers.searxng]\n"
        "last_resort_only = true\n"
        "automatic_merge = false\n"
    )
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DATA_DIR", data_dir)

    cfg = load_config()

    assert cfg.web_provider == "quality"
    assert cfg.web_billing.mode == "strict_zero_cost"
    assert cfg.web_search.minimum_relevance == 0.7
    assert cfg.web_search.candidate_discovery_threshold == 0.39
    assert cfg.web_search.final_verification_threshold == 0.73
    assert cfg.web_search.strict_entity_relevance == 0.86
    assert cfg.web_search.max_results_per_domain == 1
    assert cfg.web_search.provider_order[:2] == ["exa", "searxng"]
    assert cfg.web_search.allow_explicit_provider_fallback is True
    assert cfg.web_search.cache_enabled is False
    assert cfg.web_search.max_disambiguation_queries == 3
    assert cfg.web_search.minimum_confident_entity_score == 0.71
    assert cfg.web_search.minimum_winner_margin == 0.2
    assert cfg.web_search.location.enabled is True
    assert cfg.web_search.location.maximum_inferred_location_weight == 0.08
    assert cfg.web_search.behavior.max_query_rewrites == 2
    assert cfg.web_search.behavior.max_provider_fallbacks == 3
    assert cfg.web_search.behavior.max_web_actions == 7
    assert cfg.web_search.behavior.max_search_calls == 3
    assert cfg.web_search.behavior.max_fetch_calls == 5
    assert cfg.web_search.behavior.max_pages_per_domain == 2
    assert cfg.web_search.behavior.max_consecutive_failures == 2
    assert cfg.web_search.behavior.max_total_search_calls == 4
    assert cfg.web_search.behavior.max_fetch_attempts == 2
    assert cfg.web_search.behavior.max_repeated_query_similarity == 0.85
    assert cfg.web_fetch.timeout_seconds == 12
    assert cfg.web_fetch.max_download_bytes == 750000
    assert cfg.web_fetch.max_content_characters == 16000
    assert cfg.web_fetch.max_redirects == 3
    assert cfg.web_fetch.cache_ttl_seconds == 7200
    assert cfg.web_verification.max_domains == 3
    assert cfg.web_verification.max_pages_per_domain == 5
    assert cfg.web_verification.max_total_verification_pages == 7
    assert cfg.web_verification.same_domain_only is True
    assert cfg.web_verification.respect_robots is False
    assert cfg.web_providers["google"].enabled is False
    assert cfg.web_providers["searxng"].last_resort_only is True
    assert cfg.web_providers["searxng"].automatic_merge is False
