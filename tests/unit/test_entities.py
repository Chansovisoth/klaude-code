import sqlite3

import httpx
import pytest
from klaude_core.entities import (
    EntityRecord,
    EntityResolver,
    EntityStore,
    WikimediaEntityClient,
)
from klaude_web.facade import Web
from klaude_web.providers import build_search_plan, build_search_query
from klaude_web.search import SearchResponse


@pytest.mark.parametrize(
    ("misspelled", "canonical"),
    [
        ("Cambodi", "Cambodia"),
        ("Camboida", "Cambodia"),
        ("Camobdia", "Cambodia"),
        ("Cambdia", "Cambodia"),
        ("Thialand", "Thailand"),
        ("Singapor", "Singapore"),
    ],
)
def test_location_typos_use_structured_vocabulary(misspelled, canonical):
    normalized = EntityResolver().normalize_query(misspelled)

    assert normalized.original_text == misspelled
    assert normalized.normalized_text == canonical
    assert len(normalized.corrections) == 1
    assert normalized.corrections[0].kind == "country"
    assert normalized.corrections[0].source == "structured_vocabulary"
    assert normalized.corrections[0].confidence >= 0.82


@pytest.mark.parametrize(
    "name",
    [
        "Qwen",
        "Hyprland",
        "DeepSeek",
        "OpenAI",
        "NumPy",
        "PyTorch",
        "EndeavourOS",
        "FlazeSlayer",
    ],
)
def test_valid_names_survive_without_correction(name):
    normalized = EntityResolver().normalize_query(name)

    assert normalized.normalized_text == name
    assert normalized.corrections == ()


@pytest.mark.parametrize(
    ("misspelled", "canonical"),
    [
        ("Hyprlnd", "Hyprland"),
        ("PyTorc", "PyTorch"),
        ("Deepsek", "DeepSeek"),
        ("Amercan Intercon School", "American Intercon School"),
    ],
)
def test_stable_technical_and_entity_names_allow_conservative_typos(
    misspelled,
    canonical,
):
    normalized = EntityResolver().normalize_query(misspelled)

    assert normalized.normalized_text == canonical
    assert normalized.corrections[0].corrected == canonical


@pytest.mark.parametrize("token", ["AI", "AIS", "Go", "R", "C", "JS", "TS"])
def test_short_tokens_are_never_fuzzy_rewritten(token):
    normalized = EntityResolver().normalize_query(token)

    assert normalized.normalized_text == token
    assert normalized.corrections == ()


def test_entity_store_uses_compact_name_and_alias_schema(tmp_path):
    db_path = tmp_path / "entities.sqlite"
    store = EntityStore(db_path)

    assert store.available is True
    with sqlite3.connect(db_path) as db:
        entity_columns = {
            row[1] for row in db.execute("PRAGMA table_info(entities)").fetchall()
        }
        alias_columns = {
            row[1] for row in db.execute("PRAGMA table_info(aliases)").fetchall()
        }

    assert {
        "canonical_name",
        "entity_type",
        "source",
        "source_id",
        "created_at",
        "updated_at",
        "last_seen_at",
        "confidence",
        "successful_resolution_count",
        "country",
        "language",
        "description",
        "domain",
    } <= entity_columns
    assert {"entity_id", "alias", "normalized_alias", "source", "confidence"} <= (
        alias_columns
    )


def test_entity_database_follows_configured_data_directory(tmp_path, monkeypatch):
    import klaude_core.config as config_module
    from klaude_core import Config

    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")

    assert Config().entities_db == tmp_path / "data" / "entities.sqlite"


def test_wikimedia_fallback_configuration_is_optional_and_keyless(
    tmp_path,
    monkeypatch,
):
    import klaude_core.config as config_module
    from klaude_core.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[entities]\n"
        "metadata_refresh_days = 120\n"
        "[entities.wikimedia]\n"
        "enabled = true\n"
        "timeout_seconds = 2.5\n"
        "max_results = 4\n"
    )
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")

    cfg = load_config()

    assert cfg.entity_resolution.wikimedia_enabled is True
    assert cfg.entity_resolution.wikimedia_timeout_seconds == 2.5
    assert cfg.entity_resolution.wikimedia_max_results == 4
    assert cfg.entity_resolution.metadata_refresh_days == 120


def test_trusted_entity_learning_persists_aliases_and_improves_repeated_lookup(
    tmp_path,
):
    db_path = tmp_path / "entities.sqlite"
    resolver = EntityResolver(db_path, structured_entities=())

    assert resolver.resolve_name("NexuzDB") is None
    assert resolver.learn_entity(
        EntityRecord(
            canonical_name="NexusDB",
            entity_type="software",
            aliases=("Nexus Database",),
            source="verified_search",
            domain="nexusdb.example",
            confidence=0.94,
        )
    )

    offline = EntityResolver(db_path, structured_entities=())
    first = offline.resolve_name("NexuzDB")
    second = offline.resolve_name("NexuzDB")
    stored = offline.store.get("NexusDB")

    assert first is not None
    assert first.entity.canonical_name == "NexusDB"
    assert first.source == "local_entity_cache"
    assert second is not None
    assert stored is not None
    assert "Nexus Database" in stored.aliases
    assert stored.successful_resolution_count >= 2


def test_low_confidence_or_untrusted_entities_are_not_learned(tmp_path):
    resolver = EntityResolver(tmp_path / "entities.sqlite", structured_entities=())

    assert not resolver.learn_entity(
        EntityRecord(
            canonical_name="Random typo prose",
            source="web_text",
            confidence=0.99,
        )
    )
    assert not resolver.learn_entity(
        EntityRecord(
            canonical_name="Weak Guess",
            source="verified_search",
            confidence=0.4,
        )
    )


class _FakeWikidataResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _wikidata_result(label="NexusDB", *, entity_id="Q123", description="software"):
    return {
        "search": [
            {
                "id": entity_id,
                "label": label,
                "description": description,
                "aliases": ["Nexus Database"],
                "match": {"type": "label", "text": label},
            }
        ]
    }


def test_wikimedia_is_used_only_after_local_resolution_misses_and_is_cached(tmp_path):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeWikidataResponse(_wikidata_result())

    db_path = tmp_path / "entities.sqlite"
    client = WikimediaEntityClient(user_agent="KlaudeTest/0.1", http_get=fake_get)
    resolver = EntityResolver(
        db_path,
        wikimedia_client=client,
        structured_entities=(),
    )

    first = resolver.resolve_name("NexuzDB", allow_wikimedia=True)

    assert first is not None
    assert first.entity.canonical_name == "NexusDB"
    assert len(calls) == 1
    assert calls[0][0] == "https://www.wikidata.org/w/api.php"
    assert calls[0][1]["params"]["search"] == "NexuzDB"
    assert "api_key" not in calls[0][1]["params"]
    assert calls[0][1]["headers"]["User-Agent"] == "KlaudeTest/0.1"

    def should_not_call(*args, **kwargs):
        raise AssertionError("Wikidata should not be called after the local cache learns")

    offline_client = WikimediaEntityClient(
        user_agent="KlaudeTest/0.1",
        http_get=should_not_call,
    )
    offline = EntityResolver(
        db_path,
        wikimedia_client=offline_client,
        structured_entities=(),
    )
    second = offline.resolve_name("NexuzDB", allow_wikimedia=True)

    assert second is not None
    assert second.source == "local_entity_cache"


def test_wikimedia_is_not_called_when_structured_name_is_confident():
    def should_not_call(*args, **kwargs):
        raise AssertionError("Wikidata should not be called for a known local name")

    client = WikimediaEntityClient(user_agent="KlaudeTest/0.1", http_get=should_not_call)
    resolver = EntityResolver(wikimedia_client=client)

    candidate = resolver.resolve_name("Qwen", allow_wikimedia=True)

    assert candidate is not None
    assert candidate.entity.canonical_name == "Qwen"


@pytest.mark.parametrize(
    "error",
    [
        httpx.TimeoutException("timeout"),
        httpx.ConnectError("offline"),
    ],
)
def test_wikimedia_failure_never_breaks_local_resolution(error, tmp_path):
    def failing_get(*args, **kwargs):
        raise error

    client = WikimediaEntityClient(user_agent="KlaudeTest/0.1", http_get=failing_get)
    resolver = EntityResolver(
        tmp_path / "entities.sqlite",
        wikimedia_client=client,
        structured_entities=(),
    )

    assert resolver.resolve_name("NexuzDB", allow_wikimedia=True) is None
    assert resolver.normalize_query("ordinary offline query").normalized_text == (
        "ordinary offline query"
    )


def test_ambiguous_wikidata_results_are_not_accepted(tmp_path):
    def fake_get(*args, **kwargs):
        return _FakeWikidataResponse(
            {
                "search": [
                    {
                        "id": "Q1",
                        "label": "Cambodia",
                        "description": "country in Southeast Asia",
                    },
                    {
                        "id": "Q2",
                        "label": "Cambodie",
                        "description": "unrelated entity",
                    },
                ]
            }
        )

    client = WikimediaEntityClient(user_agent="KlaudeTest/0.1", http_get=fake_get)
    resolver = EntityResolver(
        tmp_path / "entities.sqlite",
        wikimedia_client=client,
        structured_entities=(),
    )

    assert resolver.resolve_name("Cambodi", allow_wikimedia=True) is None


def test_search_candidate_learning_requires_unambiguous_high_confidence(tmp_path):
    resolver = EntityResolver(tmp_path / "entities.sqlite", structured_entities=())
    metadata = {
        "ambiguity": {"is_ambiguous": False},
        "entity_candidates": [
            {
                "canonical_name": "American Intercon School",
                "aliases": ["AIS"],
                "entity_type": "school",
                "country": "Cambodia",
                "description": "a Cambodian school",
                "domains": ["ais.edu.kh"],
                "score": 0.91,
            }
        ],
    }

    learned = resolver.learn_from_search_metadata(metadata)
    cached = EntityResolver(
        tmp_path / "entities.sqlite",
        structured_entities=(),
    ).resolve_name("Amercan Intercon Schol")

    assert learned is not None
    assert learned.canonical_name == "American Intercon School"
    assert cached is not None
    assert cached.entity.canonical_name == "American Intercon School"

    metadata["ambiguity"] = {"is_ambiguous": True}
    assert resolver.learn_from_search_metadata(metadata) is None


def test_ais_cambodi_normalizes_before_location_ambiguity_and_query_planning():
    from klaude_core import Config

    cfg = Config()
    query = build_search_query("what is AIS Cambodi", cfg, 8)
    plan = build_search_plan("what is AIS Cambodi", cfg, 8)

    assert query.original_text == "what is AIS Cambodi"
    assert query.normalized_text == "what is AIS Cambodia"
    assert query.text == "AIS Cambodia"
    assert query.country == "KH"
    assert len(query.corrections) == 1
    assert query.corrections[0].original == "Cambodi"
    assert query.corrections[0].corrected == "Cambodia"
    assert query.corrections[0].kind == "country"
    assert query.corrections[0].confidence >= 0.9
    assert query.corrections[0].source == "structured_vocabulary"
    assert plan.primary_query == "AIS Cambodia"
    assert plan.related_queries == [
        "AIS school Cambodia",
        "What does AIS stand for Cambodia",
    ]
    assert plan.target_entity == "AIS"


def test_correction_diagnostics_preserve_input_and_planned_queries():
    from klaude_core import Config

    cfg = Config()
    query = build_search_query("what is AIS Cambodi", cfg, 8)
    response = SearchResponse(
        results=[],
        queries_attempted=["AIS Cambodia", "AIS school Cambodia"],
        provider_metadata={"result_count": 12, "plausible_candidate_count": 4},
    )
    web = object.__new__(Web)

    finalized = web._finalize_search_response(response, query, EntityResolver())

    assert finalized.provider_metadata["original_text"] == "what is AIS Cambodi"
    assert finalized.provider_metadata["normalized_text"] == "what is AIS Cambodia"
    assert finalized.provider_metadata["corrections"][0]["original"] == "Cambodi"
    assert finalized.provider_metadata["display_lines"] == [
        "Input: what is AIS Cambodi",
        "Normalized: what is AIS Cambodia",
        "Correction: Cambodi -> Cambodia [country]",
        "Queries: AIS Cambodia | AIS school Cambodia",
        "Returned 12 results; 4 plausible candidates.",
    ]


@pytest.mark.parametrize(
    ("followup", "expected_term"),
    [
        ("Who was the chairman?", "chairman"),
        ("Who was its chairman?", "chairman"),
        ("Who is the chairman?", "chairman"),
        ("Who is their principal?", "principal"),
        ("Who was the president?", "president"),
        ("Who is the director?", "director"),
        ("When was it established?", "established"),
        ("Where is its main campus?", "campus"),
    ],
)
def test_ais_typo_resolution_preserves_entity_for_relationship_followups(
    followup,
    expected_term,
):
    from klaude_core.agent import (
        RetrievalConversationState,
        _update_retrieval_state_from_tool_result,
        _update_retrieval_state_from_user,
    )

    state = RetrievalConversationState()
    first_messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "what is AIS Cambodi"},
    ]
    _update_retrieval_state_from_user(
        state,
        first_messages[-1]["content"],
        first_messages,
    )
    _update_retrieval_state_from_tool_result(
        state,
        "web_search",
        {
            "provider_metadata": {
                "original_text": "what is AIS Cambodi",
                "normalized_text": "what is AIS Cambodia",
                "corrections": [
                    {
                        "original": "Cambodi",
                        "corrected": "Cambodia",
                        "kind": "country",
                        "source": "structured_vocabulary",
                        "confidence": 0.95,
                    }
                ],
                "entity_candidates": [
                    {
                        "canonical_name": "American Intercon School",
                        "aliases": ["AIS"],
                        "entity_type": "school",
                        "country": "Cambodia",
                        "domains": ["ais.edu.kh"],
                        "score": 0.92,
                    }
                ],
            }
        },
    )
    entity = state.active_entities[0]
    assert entity.canonical_name == "American Intercon School"
    assert entity.location == "Cambodia"

    messages = [
        *first_messages,
        {
            "role": "assistant",
            "content": "AIS means American Intercon School in Cambodia.",
        },
        {"role": "user", "content": followup},
    ]
    _update_retrieval_state_from_user(state, followup, messages)

    assert state.active_entities[0] is entity
    assert "American Intercon School" in state.last_standalone_query
    assert "Cambodia" in state.last_standalone_query
    assert expected_term in state.last_standalone_query.lower()
