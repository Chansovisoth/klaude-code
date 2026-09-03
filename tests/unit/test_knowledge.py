import random
import sqlite3
from pathlib import Path

import lancedb
import pytest
from klaude_knowledge.chunker import chunk_markdown
from klaude_knowledge.hybrid import _rrf
from klaude_knowledge.indexing import IndexDocument, KnowledgeIndexer
from klaude_knowledge.store import KnowledgeStore

MD = """# Routing

Next.js has a file-system based router built on the concept of pages.

## Dynamic routes

To create a dynamic route you can use brackets in the filename, for example
`pages/posts/[id].js` matches `/posts/1`, `/posts/abc` and so on. Inside the
page you read the parameter from the router.

```js
const { id } = router.query
```

## API routes

Files under `pages/api` become API endpoints. Each file exports a default
handler receiving request and response objects, and they run server-side only.
This section needs to be long enough to become its own chunk so we pad it with
a bit of extra explanatory text about middleware, edge runtimes and handlers.
"""


def test_chunker_keeps_heading_context():
    chunks = chunk_markdown(MD, title="nextjs routing")
    assert chunks, "should produce at least one chunk"
    joined = " ".join(c.text for c in chunks)
    assert "router.query" in joined
    assert any("Routing" in c.section or "routes" in c.section for c in chunks)
    # code fence must survive intact in some chunk
    assert any("```js" in c.text and "```" in c.text.split("```js")[1] for c in chunks)


def test_store_roundtrip_and_keyword_search(tmp_path):
    store = KnowledgeStore(tmp_path)
    texts = [c.text for c in chunk_markdown(MD, "nextjs")]
    vecs = [[random.random() for _ in range(8)] for _ in texts]
    n = store.add("nextjs", texts, vecs, source="test://doc", sections=[""] * len(texts))
    assert n == len(texts)

    hits = store.keyword_search("nextjs", "dynamic route brackets", k=5)
    assert hits and "brackets" in hits[0]["text"]

    vhits = store.vector_search("nextjs", vecs[0], k=2)
    assert vhits and vhits[0]["text"] == texts[0]

    # re-learning same source must not duplicate
    n2 = store.add("nextjs", texts, vecs, source="test://doc", sections=[""] * len(texts))
    assert n2 == n
    staged_rows = store.fts.execute(
        "SELECT COUNT(*) FROM chunks_v2 WHERE library='nextjs'"
    ).fetchone()[0]
    assert staged_rows == n

    replacement = ["# Fresh docs\n\nApp Router cache tags are new here."]
    store.add("nextjs", replacement, [[random.random() for _ in range(8)]], source="test://doc")
    stale = store.keyword_search("nextjs", "dynamic route brackets", k=5)
    fresh = store.keyword_search("nextjs", "cache tags", k=5)
    assert stale == []
    assert fresh and "cache tags" in fresh[0]["text"]


def test_store_delete_source_keeps_identical_chunk_from_other_source(tmp_path):
    store = KnowledgeStore(tmp_path)
    text = "Shared chunk about reusable documentation."
    vec = [[random.random() for _ in range(8)]]
    store.add("docs", [text], vec, source="source://one")
    store.add("docs", [text], vec, source="source://two")

    store.delete_sources("docs", ["source://one"])

    hits = store.keyword_search("docs", "reusable documentation", k=5)
    assert len(hits) == 1
    assert hits[0]["source"] == "source://two"


def test_store_migrates_legacy_fts_schema_without_losing_keyword_rows(tmp_path):
    db = lancedb.connect(str(tmp_path))
    db.create_table(
        "docs",
        [
            {
                "id": "abc",
                "text": "Legacy keyword search survives migration.",
                "vector": [0.1, 0.2],
                "source": "source://legacy",
                "section": "",
                "learned_at": 1.0,
            }
        ],
    )
    fts = sqlite3.connect(tmp_path / "fts.db")
    fts.execute(
        "CREATE VIRTUAL TABLE chunks USING fts5(id UNINDEXED, collection UNINDEXED, text)"
    )
    fts.execute(
        "INSERT INTO chunks (id, collection, text) VALUES (?,?,?)",
        ("abc", "docs", "Legacy keyword search survives migration."),
    )
    fts.commit()
    fts.close()

    store = KnowledgeStore(tmp_path)

    hits = store.keyword_search("docs", "survives migration", k=5)
    assert len(hits) == 1
    assert hits[0]["source"] == "source://legacy"


class FakeConfig:
    def __init__(self, root: Path):
        self._root = root
        self.models = {"embed": "fake-embed"}

    @property
    def knowledge_dir(self):
        path = self._root / "knowledge"
        path.mkdir(exist_ok=True)
        return path

    @property
    def docs_cache_dir(self):
        path = self._root / "cache"
        path.mkdir(exist_ok=True)
        return path


class FakeOllama:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.embed_calls = 0

    def embed(self, model, texts):
        self.embed_calls += 1
        if self.fail:
            raise RuntimeError("embed failed")
        return [[float(i + 1), 0.0, 0.0] for i, _text in enumerate(texts)]


def test_embedding_failure_leaves_old_active_source_and_cache(tmp_path):
    from klaude_knowledge.hybrid import Knowledge

    cfg = FakeConfig(tmp_path)
    old = Knowledge(cfg, FakeOllama())
    assert old.learn_text("docs", "# Old\n\nstable", source="https://example.test/doc") > 0
    cache_path = old._cache_path("docs", "https://example.test/doc")
    assert cache_path.read_text() == "# Old\n\nstable"

    broken = Knowledge(cfg, FakeOllama(fail=True))
    with pytest.raises(RuntimeError, match="embed failed"):
        broken.learn_text("docs", "# New\n\nbroken", source="https://example.test/doc")

    assert cache_path.read_text() == "# Old\n\nstable"
    assert old.store.keyword_search("docs", "stable", k=5)
    assert old.store.keyword_search("docs", "broken", k=5) == []


def test_lancedb_stage_failure_leaves_old_active_source(tmp_path, monkeypatch):
    cfg = FakeConfig(tmp_path)
    store = KnowledgeStore(cfg.knowledge_dir)
    indexer = KnowledgeIndexer(cfg, store, FakeOllama())
    indexer.replace_source_atomic("docs", "learn:source", "source", "# Old\n\nalpha")

    def fail_insert(_library, _rows):
        raise RuntimeError("lance failed")

    monkeypatch.setattr(store, "_insert_v2_rows", fail_insert)
    with pytest.raises(RuntimeError, match="lance failed"):
        indexer.replace_source_atomic("docs", "learn:source", "source", "# New\n\nbeta")

    assert store.keyword_search("docs", "alpha", 5)
    assert store.keyword_search("docs", "beta", 5) == []


def test_fts_stage_failure_leaves_old_active_source(tmp_path, monkeypatch):
    cfg = FakeConfig(tmp_path)
    store = KnowledgeStore(cfg.knowledge_dir)
    indexer = KnowledgeIndexer(cfg, store, FakeOllama())
    indexer.replace_source_atomic("docs", "learn:source", "source", "# Old\n\nalpha")

    def fail_verify(_library, _version_id, _expected):
        raise RuntimeError("fts failed")

    monkeypatch.setattr(store, "verify_version_rows", fail_verify)
    with pytest.raises(RuntimeError, match="fts failed"):
        indexer.replace_source_atomic("docs", "learn:source", "source", "# New\n\nbeta")

    assert store.keyword_search("docs", "alpha", 5)
    assert store.keyword_search("docs", "beta", 5) == []


def test_activation_failure_leaves_staged_content_invisible(tmp_path, monkeypatch):
    cfg = FakeConfig(tmp_path)
    store = KnowledgeStore(cfg.knowledge_dir)
    indexer = KnowledgeIndexer(cfg, store, FakeOllama())
    indexer.replace_source_atomic("docs", "learn:source", "source", "# Old\n\nalpha")

    def fail_activate(_library, _owner, _source_versions):
        raise RuntimeError("activation failed")

    monkeypatch.setattr(store, "activate_versions", fail_activate)
    with pytest.raises(RuntimeError, match="activation failed"):
        indexer.replace_source_atomic("docs", "learn:source", "source", "# New\n\nbeta")

    assert store.keyword_search("docs", "alpha", 5)
    assert store.keyword_search("docs", "beta", 5) == []


def test_owner_snapshot_activation_adds_and_removes_files_atomically(tmp_path):
    cfg = FakeConfig(tmp_path)
    store = KnowledgeStore(cfg.knowledge_dir)
    indexer = KnowledgeIndexer(cfg, store, FakeOllama())

    indexer.replace_owner_snapshot_atomic(
        "docs",
        "docs:react",
        [
            IndexDocument("a.md", "# A\n\nalpha"),
            IndexDocument("b.md", "# B\n\nbeta"),
        ],
    )
    assert store.keyword_search("docs", "alpha", 5)
    assert store.keyword_search("docs", "beta", 5)

    indexer.replace_owner_snapshot_atomic(
        "docs",
        "docs:react",
        [IndexDocument("a.md", "# A2\n\ngamma")],
    )
    assert store.keyword_search("docs", "gamma", 5)
    assert store.keyword_search("docs", "beta", 5) == []


def test_recover_incomplete_staging_marks_rows_failed(tmp_path):
    store = KnowledgeStore(tmp_path)
    version_id = store.stage_version(
        "docs",
        "learn:source",
        "source",
        ["# Staged\n\nhidden"],
        [[0.1, 0.2]],
        "checksum",
    )

    assert store.keyword_search("docs", "hidden", 5) == []
    assert store.vector_search("docs", [0.1, 0.2], 5) == []
    assert store.recover_incomplete_operations() == 1
    versions = {row["version_id"]: row["status"] for row in store.debug_versions()}
    assert versions[version_id] == "failed"


def test_rrf_prefers_agreement():
    a = [
        {"id": "x", "text": "x", "vector_rank": 1},
        {
            "id": "y",
            "text": "y",
            "section": "Retrieval architecture",
            "vector_rank": 2,
        },
    ]
    b = [
        {"id": "y", "text": "y", "section": "", "keyword_rank": 1},
        {"id": "z", "text": "z", "keyword_rank": 2},
    ]
    merged = _rrf([a, b])
    assert merged[0]["id"] == "y"  # appears in both lists
    assert merged[0]["vector_rank"] == 2
    assert merged[0]["keyword_rank"] == 1
    assert merged[0]["section"] == "Retrieval architecture"
    assert merged[0]["rrf_rank"] == 1
    assert merged[0]["rrf_score"] > merged[1]["rrf_score"]


def test_accepted_hits_preserve_optional_reranker_order():
    from klaude_knowledge.hybrid import Knowledge, LibraryRoute

    class RetrievalConfig:
        retrieval_min_vector_similarity = 0.0
        retrieval_min_lexical_overlap = 0.0
        retrieval_min_combined_confidence = 0.0
        retrieval_min_global_confidence = 0.0

    knowledge = object.__new__(Knowledge)
    knowledge.cfg = RetrievalConfig()
    route = LibraryRoute(["docs"], 1.0, "explicit library")
    hits = [
        {
            "id": "heuristic-first",
            "text": "adaptive retrieval agent",
            "vector_distance": 0.0,
            "vector_rank": 1,
            "rerank_rank": 2,
        },
        {
            "id": "reranker-first",
            "text": "adaptive retrieval agent",
            "vector_distance": 1.0,
            "vector_rank": 2,
            "rerank_rank": 1,
        },
    ]

    accepted = knowledge._accepted_hits("adaptive retrieval agent", route, hits, 2)

    assert [hit["id"] for hit in accepted] == ["reranker-first", "heuristic-first"]


def test_knowledge_learn_text_skips_unchanged_indexed_source(tmp_path):
    from klaude_knowledge.hybrid import Knowledge

    class FakeConfig:
        models = {"embed": "fake-embed"}

        @property
        def knowledge_dir(self):
            path = tmp_path / "knowledge"
            path.mkdir(exist_ok=True)
            return path

        @property
        def docs_cache_dir(self):
            path = tmp_path / "cache"
            path.mkdir(exist_ok=True)
            return path

    class FakeOllama:
        def __init__(self):
            self.embed_calls = 0

        def embed(self, model, texts):
            self.embed_calls += 1
            return [[0.1, 0.2, 0.3] for _ in texts]

    ollama = FakeOllama()
    knowledge = Knowledge(FakeConfig(), ollama)
    text = "# Docs\n\nRepeated installs should skip embedding unchanged content."

    first = knowledge.learn_text("docs", text, source="https://example.test/docs")
    second = knowledge.learn_text("docs", text, source="https://example.test/docs")

    assert first > 0
    assert second == 0
    assert ollama.embed_calls == 1


def test_knowledge_matches_collections_named_in_question(tmp_path):
    from klaude_knowledge.hybrid import Knowledge

    class FakeConfig:
        models = {"embed": "fake-embed"}

        @property
        def knowledge_dir(self):
            path = tmp_path / "knowledge"
            path.mkdir(exist_ok=True)
            return path

        @property
        def docs_cache_dir(self):
            path = tmp_path / "cache"
            path.mkdir(exist_ok=True)
            return path

    class FakeOllama:
        def embed(self, model, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

    knowledge = Knowledge(FakeConfig(), FakeOllama())
    knowledge.store.add(
        "clang",
        ["AddressSanitizer documentation."],
        [[0.1, 0.2, 0.3]],
        source="clang",
    )
    knowledge.store.add(
        "godot",
        ["Godot 4.7 documentation."],
        [[0.1, 0.2, 0.3]],
        source="godot",
    )
    knowledge.store.add(
        "godot-2d",
        ["Godot 2D documentation."],
        [[0.1, 0.2, 0.3]],
        source="godot-2d",
    )

    matches = knowledge.matching_collections("what new features were added to Godot 4.7?")

    assert matches == ["godot", "godot-2d"]


def test_exact_library_query_routes_only_to_intended_library(tmp_path):
    from klaude_knowledge.hybrid import Knowledge

    knowledge = Knowledge(FakeConfig(tmp_path), FakeOllama())
    knowledge.store.add("react", ["React hooks documentation."], [[0.1, 0.2]], source="react")
    knowledge.store.add("vue", ["Vue refs documentation."], [[0.1, 0.2]], source="vue")

    route = knowledge.route_libraries("React hooks")

    assert route.libraries == ["react"]
    assert route.confidence >= 0.9


def test_unknown_topic_query_does_not_return_unrelated_local_chunks(tmp_path):
    from klaude_knowledge.hybrid import Knowledge

    knowledge = Knowledge(FakeConfig(tmp_path), FakeOllama())
    knowledge.store.add(
        "react",
        ["React component state and effects documentation."],
        [[0.1, 0.2]],
        source="react",
    )

    assert knowledge.query("quantum banana telescope", k=3) == []


def test_weak_vector_only_candidates_are_rejected(tmp_path, monkeypatch):
    from klaude_knowledge.hybrid import Knowledge

    knowledge = Knowledge(FakeConfig(tmp_path), FakeOllama())
    knowledge.store.add("react", ["React state documentation."], [[0.1, 0.2]], source="react")

    monkeypatch.setattr(
        knowledge.store,
        "vector_search",
        lambda _library, _vector, _k: [
            {
                "id": "weak",
                "text": "Completely unrelated text.",
                "source": "react",
                "section": "",
                "vector_distance": 999.0,
                "vector_rank": 1,
            }
        ],
    )
    monkeypatch.setattr(knowledge.store, "keyword_search", lambda *_args: [])

    assert knowledge.query("React hooks", "react", k=3) == []


def test_strong_lexical_candidates_can_pass_without_vector_match(tmp_path, monkeypatch):
    from klaude_knowledge.hybrid import Knowledge

    knowledge = Knowledge(FakeConfig(tmp_path), FakeOllama())
    knowledge.store.add(
        "nextjs",
        ["Dynamic route brackets are used in Next.js page filenames."],
        [[0.1, 0.2]],
        source="nextjs",
    )
    monkeypatch.setattr(knowledge.store, "vector_search", lambda *_args: [])

    hits = knowledge.query("dynamic route brackets", "nextjs", k=3)

    assert hits
    assert hits[0]["relevance_score"] >= 0.32


def test_global_retrieval_uses_stricter_thresholds(tmp_path):
    from klaude_knowledge.hybrid import Knowledge

    knowledge = Knowledge(FakeConfig(tmp_path), FakeOllama())
    knowledge.store.add(
        "nextjs",
        ["Cache tags revalidate route data."],
        [[0.1, 0.2]],
        source="nextjs",
    )
    knowledge.store.add("react", ["Component effects and state."], [[0.1, 0.2]], source="react")

    assert knowledge.query("cache tags revalidate", k=3)
    assert knowledge.query("cache banana telescope", k=3) == []


def test_query_as_context_returns_empty_context_when_confidence_is_low(tmp_path):
    from klaude_knowledge.hybrid import Knowledge

    knowledge = Knowledge(FakeConfig(tmp_path), FakeOllama())
    knowledge.store.add("react", ["React component state."], [[0.1, 0.2]], source="react")

    assert (
        knowledge.query_as_context("quantum banana telescope")
        == "No relevant local knowledge found."
    )


def test_cache_ttl(tmp_path):
    from klaude_web.cache import TTLCache

    c = TTLCache(tmp_path / "c.db")
    c.set("k", {"v": 1}, ttl_seconds=60)
    assert c.get("k") == {"v": 1}
    c.set("k2", "gone", ttl_seconds=-1)
    assert c.get("k2") is None


def test_cache_write_failures_are_nonfatal(tmp_path):
    import sqlite3

    from klaude_web.cache import TTLCache

    c = TTLCache(tmp_path / "c.db")
    c.set("expired", "gone", ttl_seconds=-1)
    writable = c.db

    class ReadOnlyConnection:
        def execute(self, sql, args=()):
            if sql.startswith(("INSERT", "DELETE")):
                raise sqlite3.OperationalError("attempt to write a readonly database")
            return writable.execute(sql, args)

        def commit(self):
            raise sqlite3.OperationalError("attempt to write a readonly database")

    c.db = ReadOnlyConnection()

    c.set("k", {"v": 1}, ttl_seconds=60)
    assert c.get("expired") is None


def test_permission_gate():
    import pytest
    from klaude_core import PermissionDenied, PermissionGate

    answers = iter(["n", "a"])
    gate = PermissionGate({"run_shell": "ask", "read_file": "allow"}, lambda t, d: next(answers))
    gate.check("read_file", "x")  # allow, no prompt
    with pytest.raises(PermissionDenied):
        gate.check("run_shell", "rm -rf /")  # answered n
    gate.check("run_shell", "ls")  # answered a -> becomes allow
    gate.check("run_shell", "ls")  # no prompt needed anymore


def test_agent_executes_text_form_tool_call():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": (
                        "I will look it up.\n\n"
                        "<function=web_search> "
                        "<parameter=query> Dieng city country   </tool_call>"
                    ),
                }
            return {"role": "assistant", "content": "Dieng is a place."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("look it up"))

    assert events[0].kind == "tool_start"
    assert events[0].payload == {
        "tool": "web_search",
        "args": {"query": "Dieng city country"},
    }
    assert events[1].kind == "tool_result"
    assert "found Dieng city country" in events[1].payload["result"]
    assert not any(
        event.kind == "text" and "<function=web_search>" in event.payload.get("content", "")
        for event in events
    )


def test_agent_web_search_start_metadata_survives_text_form_tool_call():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": (
                        "<function=web_search> "
                        "<parameter=query>PIU university Cambodia</tool_call>"
                    ),
                }
            return {"role": "assistant", "content": "Verified."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: {
            "content": f"found {query}",
            "metadata": {
                "provider": "ddgs",
                "successful_providers": ["ddgs"],
            },
        },
        start_metadata=lambda args: {
            "provider": "ddgs",
            "query": args["query"],
            "canonical_tool": "web_search",
        },
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("look it up"))

    assert events[0].kind == "tool_start"
    assert events[0].payload["provider"] == "ddgs"
    assert events[0].payload["metadata"]["canonical_tool"] == "web_search"
    assert events[1].payload["metadata"]["provider"] == "ddgs"


def test_agent_web_search_start_metadata_survives_structured_tool_call():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "web_search",
                                "arguments": {"query": "AIS school Cambodia"},
                            }
                        }
                    ],
                }
            return {"role": "assistant", "content": "Verified."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: {
            "content": f"found {query}",
            "metadata": {
                "provider": "google",
                "successful_providers": ["google"],
            },
        },
        start_metadata=lambda args: {
            "provider": "google",
            "query": args["query"],
            "canonical_tool": "web_search",
        },
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    events = list(agent.run("do it"))

    assert events[0].kind == "tool_start"
    assert events[0].payload["provider"] == "google"
    assert events[1].payload["metadata"]["provider"] == "google"


def test_agent_resolves_search_alias_to_web_search_even_after_selector_miss():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                assert tools == []
                return {
                    "role": "assistant",
                    "content": "<function=search> <parameter=query>AIS school Cambodia</tool_call>",
                }
            return {"role": "assistant", "content": "Verified."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: [],
    )

    events = list(agent.run("AIS school in cambodia"))

    assert events[0].kind == "tool_start"
    assert events[0].payload["tool"] == "web_search"
    assert events[1].payload["metadata"]["web_research"]["budgets"] == {
        "web_actions_used": 1,
        "max_web_actions": 6,
        "search_calls_used": 1,
        "max_search_calls": 3,
        "fetch_calls_used": 0,
        "max_fetch_calls": 4,
    }
    assert "found AIS school Cambodia" in events[1].payload["result"]


def test_tool_aliases_resolve_to_existing_canonical_tools():
    from klaude_core.agent import canonical_tool_name, tool_aliases

    known_tools = {"web_search"}

    for alias, canonical in tool_aliases().items():
        assert canonical in known_tools
        assert canonical_tool_name(alias, known_tools) == canonical


def test_advertised_tools_exist_in_dispatcher_across_continuations():
    from klaude_core import Agent, PermissionGate, Tool

    seen_tool_names = []

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            names = [tool["function"]["name"] for tool in (tools or [])]
            seen_tool_names.append(names)
            assert set(names) <= {"web_search"}
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "web_search", "arguments": {"query": "AIS"}}}
                    ],
                    "content": "",
                }
            return {"role": "assistant", "content": "Done."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    list(agent.run("what is AIS"))

    assert seen_tool_names == [["web_search"], ["web_search"]]


def test_post_tool_error_continuation_retains_search_tools():
    from klaude_core import Agent, PermissionGate, Tool

    seen_tool_names = []

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            seen_tool_names.append([tool["function"]["name"] for tool in (tools or [])])
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": "<function=unknown_tool> <parameter=query>x</tool_call>",
                }
            assert messages[-1]["role"] == "tool"
            return {"role": "assistant", "content": "I could not dispatch that tool."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    list(agent.run("use search"))

    assert seen_tool_names == [["web_search"], ["web_search"]]


def test_followup_search_query_uses_previous_ais_context():
    from klaude_core.agent import _contextual_search_query

    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "what is AIS"},
        {"role": "user", "content": "school in cambodia"},
    ]

    query = _contextual_search_query("school in cambodia", "school in cambodia", messages)

    assert query == "AIS school cambodia"


def test_followup_school_uses_recent_disambiguation_context():
    from klaude_core.agent import _contextual_search_query

    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "what is AIS"},
        {
            "role": "assistant",
            "content": (
                '"AIS" can refer to several things. Based on the approximate '
                "Cambodia context, the most relevant candidate is American "
                "Intercon School - a Cambodian school."
            ),
        },
        {"role": "user", "content": "the school"},
    ]

    query = _contextual_search_query("the school", "the school", messages)

    assert query == "AIS school Cambodia"


def test_followup_my_location_uses_recent_ais_school_context():
    from klaude_core.agent import _contextual_search_query

    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "what is AIS"},
        {
            "role": "assistant",
            "content": (
                '"AIS" can refer to several things. Based on the approximate '
                "Cambodia context, the most relevant candidate is American "
                "Intercon School - a Cambodian school."
            ),
        },
        {"role": "user", "content": "find schools under the name AIS"},
        {"role": "assistant", "content": "I found AIS International School Laos, not Cambodia."},
        {"role": "user", "content": "no, in my location"},
    ]

    query = _contextual_search_query("in my location", "no, in my location", messages)

    assert query == "AIS school Cambodia"


def test_followup_school_here_uses_runtime_location_context():
    from klaude_core.agent import _contextual_search_query

    messages = [
        {
            "role": "system",
            "content": (
                "<runtime_context machine_generated=\"true\">\n"
                "- Timezone: Asia/Phnom_Penh\n"
                "- Approximate country: Cambodia\n"
                "</runtime_context>"
            ),
        },
        {"role": "user", "content": "what is AIS"},
        {"role": "assistant", "content": "AIS can mean several things."},
        {"role": "user", "content": "i meant the school here"},
    ]

    query = _contextual_search_query(
        "i meant the school here",
        "i meant the school here",
        messages,
    )

    assert query == "AIS school Cambodia"


def test_followup_at_my_location_does_not_need_country_from_user():
    from klaude_core.agent import RetrievalConversationState, _contextual_search_query

    state = RetrievalConversationState()
    messages = [
        {
            "role": "system",
            "content": (
                "<runtime_context machine_generated=\"true\">\n"
                "- Timezone: Asia/Phnom_Penh\n"
                "- Approximate country: Cambodia\n"
                "</runtime_context>"
            ),
        },
        {"role": "user", "content": "what is AIS"},
        {"role": "user", "content": "i meant the school here"},
    ]

    _contextual_search_query("i meant the school here", "i meant the school here", messages, state)
    query = _contextual_search_query("at my location", "at my location", messages, state)

    assert query == "AIS school Cambodia"


def test_phase1_entity_state_switches_ais_to_paragon_without_constraint_leak():
    from klaude_core import Agent, PermissionGate, Tool

    queries = []

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {"role": "assistant", "content": "ok"}

    def web_search(query):
        queries.append(query)
        metadata = {
            "search_results": [
                {
                    "title": query,
                    "url": "https://example.test/",
                    "snippet": query,
                }
            ]
        }
        if "AIS" in query:
            metadata["provider_metadata"] = {
                "entity_candidates": [
                    {
                        "canonical_name": "American Intercon School",
                        "aliases": ["AIS", "American Intercon School"],
                        "entity_type": "school",
                        "country": "Cambodia",
                        "domains": ["ais.edu.kh"],
                        "score": 0.91,
                    }
                ]
            }
        return {"content": f"found {query}", "metadata": metadata}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        web_search,
    )
    system_prompt = (
        '<runtime_context machine_generated="true">\n'
        "- Timezone: Asia/Phnom_Penh\n"
        "- Approximate country: Cambodia\n"
        "</runtime_context>"
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        system_prompt,
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    list(agent.run("What is AIS?"))
    list(agent.run("It's a school."))
    list(agent.run("What is Paragon?"))
    final_events = list(agent.run("It's a university."))

    state = agent.retrieval_state
    ais = next(entity for entity in state.entity_history if entity.mention == "AIS")
    paragon = next(entity for entity in state.entity_history if entity.mention == "Paragon")
    final_query = final_events[0].payload["args"]["query"]
    provenance = state.last_query_provenance

    assert ais.active is False
    assert ais.entity_category == "education"
    assert ais.entity_type == "school"
    assert ais.location == "Cambodia"
    assert paragon.active is True
    assert paragon.entity_category == "education"
    assert paragon.entity_type == "university"
    assert paragon.location is None
    assert final_query == "Paragon university Cambodia"
    assert "Paragon" in final_query
    assert "AIS" not in final_query
    assert "school" not in final_query.lower()
    assert queries[-1] == "Paragon university Cambodia"
    assert provenance is not None
    assert provenance.resolved_subject == "Paragon"
    assert provenance.subject_source == "previous_explicit_user_subject"
    assert "entity_type" in provenance.rejected_constraints
    assert "school from AIS" in provenance.rejected_constraints["entity_type"]
    assert "system prompt" not in repr(provenance).lower()
    assert "api_key" not in repr(provenance).lower()


def test_phase1_explicit_current_subject_beats_stale_query_state():
    from klaude_core.agent import (
        ConversationEntity,
        RetrievalConversationState,
        _contextual_search_query,
    )

    state = RetrievalConversationState(
        active_entities=[
            ConversationEntity(
                mention="AIS",
                canonical_name="American Intercon School",
                entity_category="education",
                entity_type="school",
                location="Cambodia",
                unresolved=False,
            )
        ]
    )
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "What is AIS?"},
        {"role": "assistant", "content": "AIS is American Intercon School in Cambodia."},
        {"role": "user", "content": "What is Paragon?"},
    ]

    query = _contextual_search_query(
        "AIS school Cambodia",
        "What is Paragon?",
        messages,
        state,
    )

    assert query == "Paragon"
    assert "AIS" not in query
    assert state.last_query_provenance is not None
    assert state.last_query_provenance.subject_source == "current_explicit_subject"
    assert state.last_query_provenance.topic_switched is True


def test_phase1_pronoun_resolution_uses_compatible_referents_only():
    from klaude_core.agent import (
        RetrievalConversationState,
        _resolve_subject_for_turn,
        _update_retrieval_state_from_user,
    )

    state = RetrievalConversationState()
    messages = [{"role": "system", "content": "system"}]
    messages.append(
        {"role": "user", "content": "Tell me about Paragon University and its founder."}
    )
    _update_retrieval_state_from_user(state, messages[-1]["content"], messages)
    messages.append({"role": "assistant", "content": "Paragon University has a founder."})
    messages.append({"role": "user", "content": "How old is he?"})

    person_resolution = _resolve_subject_for_turn("How old is he?", messages, state)

    assert person_resolution.subject == ""
    assert person_resolution.source is None
    assert state.active_entities[0].mention == "Paragon University"
    assert state.active_entities[0].entity_type == "university"

    neutral_resolution = _resolve_subject_for_turn("Where is it?", messages, state)

    assert neutral_resolution.subject == "Paragon University"
    assert neutral_resolution.source == "previous_explicit_user_subject"

    ambiguous_messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "What is AIS and Paragon?"},
        {"role": "assistant", "content": "Both are organizations."},
        {"role": "user", "content": "Where is it?"},
    ]

    ambiguous = _resolve_subject_for_turn("Where is it?", ambiguous_messages, state)

    assert ambiguous.ambiguous is True
    assert ambiguous.subject == ""


def test_resolved_ais_operating_followup_uses_canonical_establishment_query():
    from klaude_core.agent import (
        ConversationEntity,
        RetrievalConversationState,
        rewrite_followup_query,
    )

    state = RetrievalConversationState(
        active_entities=[
            ConversationEntity(
                mention="AIS",
                canonical_name="American Intercon School",
                entity_type="school",
                location="Cambodia",
                official_domains=("ais.edu.kh",),
                selected_meaning="American Intercon School",
                confidence=0.92,
                unresolved=False,
            )
        ]
    )
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "AIS school in Cambodia"},
        {
            "role": "assistant",
            "content": "AIS means American Intercon School in Cambodia.",
        },
        {"role": "user", "content": "how long have they been operating?"},
    ]

    rewrite = rewrite_followup_query(
        "how long have they been operating?",
        "how long have they been operating?",
        messages,
        state,
    )

    assert rewrite.standalone_query == (
        "When was American Intercon School in Cambodia established?"
    )
    assert "AIS school Cambodia" not in rewrite.standalone_query
    assert rewrite.explicit_constraints == ["founding date"]


def test_chairman_followup_keeps_resolved_ais_entity():
    from klaude_core.agent import (
        ConversationEntity,
        RetrievalConversationState,
        _update_retrieval_state_from_user,
    )

    entity = ConversationEntity(
        mention="AIS",
        canonical_name="American Intercon School",
        entity_type="school",
        location="Cambodia",
        official_domains=("ais.edu.kh",),
        selected_meaning="American Intercon School",
        confidence=0.92,
        unresolved=False,
    )
    state = RetrievalConversationState(active_entities=[entity])
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "what is AIS in Cambodia"},
        {
            "role": "assistant",
            "content": "AIS means American Intercon School in Cambodia.",
        },
        {"role": "user", "content": "Who was the chairman?"},
    ]

    _update_retrieval_state_from_user(state, messages[-1]["content"], messages)

    assert state.active_entities == [entity]
    assert state.active_entities[0].mention == "AIS"
    assert state.active_entities[0].canonical_name == "American Intercon School"
    assert state.last_standalone_query == (
        "American Intercon School Cambodia chairman"
    )


@pytest.mark.parametrize(
    ("followup", "role"),
    [
        ("Who was its chairman?", "chairman"),
        ("Who is the chairman?", "chairman"),
        ("Who was the chairwoman?", "chairwoman"),
        ("Who was the chairperson?", "chairperson"),
        ("Who is their principal?", "principal"),
        ("Who was the president?", "president"),
        ("Who is the director?", "director"),
    ],
)
def test_leadership_role_followups_preserve_active_entity(followup, role):
    from klaude_core.agent import (
        ConversationEntity,
        RetrievalConversationState,
        _update_retrieval_state_from_user,
    )

    entity = ConversationEntity(
        mention="AIS",
        canonical_name="American Intercon School",
        entity_type="school",
        location="Cambodia",
        official_domains=("ais.edu.kh",),
        selected_meaning="American Intercon School",
        confidence=0.92,
        unresolved=False,
    )
    state = RetrievalConversationState(active_entities=[entity])
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "what is AIS in Cambodia"},
        {
            "role": "assistant",
            "content": "AIS means American Intercon School in Cambodia.",
        },
        {"role": "user", "content": followup},
    ]

    _update_retrieval_state_from_user(state, followup, messages)

    assert state.active_entities == [entity]
    assert state.last_standalone_query == (
        f"American Intercon School Cambodia {role}"
    )


@pytest.mark.parametrize(
    "followup",
    [
        "Who founded it?",
        "When was it established?",
        "Where is its main campus?",
    ],
)
def test_relationship_and_attribute_followups_never_replace_active_entity(followup):
    from klaude_core.agent import (
        ConversationEntity,
        RetrievalConversationState,
        _update_retrieval_state_from_user,
    )

    entity = ConversationEntity(
        mention="AIS",
        canonical_name="American Intercon School",
        entity_type="school",
        location="Cambodia",
        selected_meaning="American Intercon School",
        unresolved=False,
    )
    state = RetrievalConversationState(active_entities=[entity])
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "what is AIS in Cambodia"},
        {
            "role": "assistant",
            "content": "AIS means American Intercon School in Cambodia.",
        },
        {"role": "user", "content": followup},
    ]

    _update_retrieval_state_from_user(state, followup, messages)

    assert state.active_entities == [entity]
    assert state.active_entities[0].canonical_name == "American Intercon School"


def test_attribute_words_in_an_explicit_entity_can_still_switch_topics():
    from klaude_core.agent import (
        ConversationEntity,
        RetrievalConversationState,
        _update_retrieval_state_from_user,
    )

    ais = ConversationEntity(
        mention="AIS",
        canonical_name="American Intercon School",
        entity_type="school",
        location="Cambodia",
        unresolved=False,
    )
    state = RetrievalConversationState(active_entities=[ais])
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "what is AIS in Cambodia"},
        {
            "role": "assistant",
            "content": "AIS means American Intercon School in Cambodia.",
        },
        {"role": "user", "content": "What is History Channel?"},
    ]

    _update_retrieval_state_from_user(state, messages[-1]["content"], messages)

    assert state.active_entities[0].mention == "History Channel"
    assert state.active_entities[0] is not ais


def test_recent_topic_prefers_user_anchor_over_previous_result_summary():
    from klaude_core.agent import _contextual_search_query

    messages = [
        {
            "role": "system",
            "content": (
                '<runtime_context machine_generated="true">\n'
                "- Timezone: Asia/Phnom_Penh\n"
                "- Approximate country: Cambodia\n"
                "</runtime_context>"
            ),
        },
        {"role": "user", "content": "where is Paragon"},
        {
            "role": "tool",
            "tool_name": "web_search",
            "content": "Found Paragon Indiana.",
        },
        {"role": "assistant", "content": "Paragon could mean Paragon, Indiana."},
        {"role": "user", "content": "i meant a university here"},
    ]

    query = _contextual_search_query(
        "i meant a university here",
        "i meant a university here",
        messages,
    )

    assert query == "Paragon university Cambodia"
    assert "Indiana" not in query


def test_leadership_followup_uses_active_university_context():
    from klaude_core.agent import (
        ConversationEntity,
        RetrievalConversationState,
        _contextual_search_query,
    )

    state = RetrievalConversationState(
        active_entities=[
            ConversationEntity(
                mention="Paragon",
                canonical_name="Paragon International University",
                entity_category="education",
                entity_type="university",
                location="Cambodia",
                official_domains=("paragoniu.edu.kh",),
                unresolved=False,
            )
        ]
    )
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "where is Paragon"},
        {
            "role": "assistant",
            "content": "Paragon means Paragon International University in Cambodia.",
        },
        {"role": "user", "content": "who is the head of CS department?"},
    ]

    query = _contextual_search_query(
        "who is the head of CS department?",
        "who is the head of CS department?",
        messages,
        state,
    )

    assert query == (
        "Paragon International University Cambodia Computer Science department head"
    )
    assert "AIS" not in query
    assert "Software" not in query


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_claim_verification_followup_searches_without_automatic_fetch():
    from klaude_core import Agent, PermissionGate, Tool

    queries = []
    fetched_urls = []

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {"role": "assistant", "content": "Verified from the official page."}

    def web_search(query):
        queries.append(query)
        return {
            "content": "Found 1 relevant result.",
            "metadata": {
                "provider": "searxng",
                "search_results": [
                    {
                        "title": "American Intercon School - History",
                        "url": "https://ais.edu.kh/history",
                        "snippet": (
                            "American Intercon School was established on "
                            "October 10, 2005 in Cambodia."
                        ),
                    }
                ],
                "provider_metadata": {
                    "entity_candidates": [
                        {
                            "canonical_name": "American Intercon School",
                            "aliases": ["AIS", "American Intercon School"],
                            "entity_type": "school",
                            "country": "Cambodia",
                            "domains": ["ais.edu.kh"],
                            "score": 0.91,
                        }
                    ]
                },
            },
        }

    def fetch_url(url):
        fetched_urls.append(url)
        return {
            "content": (
                "American Intercon School was established on October 10, 2005 "
                "in Phnom Penh, Cambodia."
            ),
            "metadata": {},
        }

    tools = [
        Tool(
            "web_search",
            "Search the web.",
            {"type": "object", "properties": {"query": {"type": "string"}}},
            web_search,
        ),
        Tool(
            "fetch_url",
            "Fetch a page.",
            {"type": "object", "properties": {"url": {"type": "string"}}},
            fetch_url,
        ),
    ]
    agent = Agent(
        FakeOllama(),
        "fake-model",
        tools,
        PermissionGate({"web_search": "allow", "fetch_url": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search", "fetch_url"],
    )

    list(agent.run("AIS school in Cambodia"))
    list(agent.run("how long have they been operating?"))

    assert queries[-1] == "When was American Intercon School in Cambodia established?"
    assert queries[-1] != "AIS school Cambodia"
    assert fetched_urls == []


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_allows_model_planned_search_after_weak_scripted_search():
    from klaude_core import Agent, PermissionGate, Tool
    from klaude_core.agent import ConversationEntity

    queries = []

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                assert messages[-1]["role"] == "tool"
                assert messages[-1]["tool_name"] == "web_search"
                return {
                    "role": "assistant",
                    "content": (
                        "I haven't been able to find the current head of the "
                        "CS department."
                    ),
                }
            if self.calls == 2:
                assert messages[-1]["tool_name"] == "retrieval_controller"
                assert "Queries already tried:" in messages[-1]["content"]
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "web_search",
                                "arguments": {
                                    "query": (
                                        'site:paragoniu.edu.kh "Computer Science" '
                                        "department head"
                                    )
                                },
                            }
                        }
                    ],
                }
            return {"role": "assistant", "content": "Verified from the official site."}

    def web_search(query):
        queries.append(query)
        if query.startswith("site:paragoniu.edu.kh"):
            return {
                "content": "Found 1 relevant result.",
                "metadata": {
                    "provider": "exa",
                    "search_results": [
                        {
                            "title": "Computer Science - Paragon International University",
                            "url": "https://www.paragoniu.edu.kh/computer-science/",
                            "snippet": "Computer Science department leadership page.",
                        }
                    ],
                },
            }
        return {
            "content": "No search provider succeeded.",
            "metadata": {
                "provider": "none",
                "search_results": [],
                "provider_metadata": {
                    "accepted_result_count": 0,
                    "provider_attempts": [
                        {
                            "provider": "exa",
                            "status": "no_candidate_results",
                            "reason": "returned 12 results; none passed candidate discovery",
                        }
                    ],
                },
            },
        }

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        web_search,
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )
    entity = ConversationEntity(
        mention="Paragon",
        canonical_name="Paragon International University",
        entity_category="education",
        entity_type="university",
        location="Cambodia",
        official_domains=("paragoniu.edu.kh",),
        unresolved=False,
    )
    agent.retrieval_state.active_entities = [entity]
    agent.retrieval_state.entity_history = [entity]

    events = list(agent.run("who is the head of CS department?"))

    assert queries[0] == (
        "Paragon International University Cambodia Computer Science department head"
    )
    assert queries[1].startswith("site:paragoniu.edu.kh")
    assert "Computer Science" in queries[1]
    assert "AIS" not in " ".join(queries)
    assert events[-2].payload["content"] == "Verified from the official site."


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_explicit_provider_directive_becomes_structured_arg_and_clean_query():
    from klaude_core import Agent, PermissionGate, Tool

    seen_args = []

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {"role": "assistant", "content": "Found it."}

    def web_search(query, provider="", provider_strict=False):
        seen_args.append(
            {
                "query": query,
                "provider": provider,
                "provider_strict": provider_strict,
            }
        )
        return {
            "content": "Found 1 relevant result.",
            "metadata": {
                "provider": provider,
                "search_results": [
                    {
                        "title": "American Intercon School",
                        "url": "https://ais.edu.kh/",
                        "snippet": "American Intercon School Cambodia.",
                    }
                ],
            },
        }

    tool = Tool(
        "web_search",
        "Search the web.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "provider": {"type": "string"},
                "provider_strict": {"type": "boolean"},
            },
        },
        web_search,
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    events = list(
        agent.run("Search for Claude. Rules American Intercon School Cambodia using Exa.")
    )

    assert events[0].payload["args"]["provider"] == "exa"
    assert events[0].payload["args"]["provider_strict"] is True
    assert seen_args[0]["provider"] == "exa"
    assert seen_args[0]["provider_strict"] is True
    assert seen_args[0]["query"] == "American Intercon School Cambodia"
    assert "using Exa" not in seen_args[0]["query"]
    assert "Claude. Rules" not in seen_args[0]["query"]


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_provider_only_followup_reuses_topic_and_keeps_exa_provider():
    from klaude_core import Agent, PermissionGate, Tool

    seen_args = []

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {"role": "assistant", "content": "Found it."}

    def web_search(query, provider="", provider_strict=False):
        seen_args.append(
            {
                "query": query,
                "provider": provider,
                "provider_strict": provider_strict,
            }
        )
        return {
            "content": (
                "[1] Automatic Identification System\n"
                "https://example.test/ais\n"
                "AIS can refer to several things."
            ),
            "metadata": {
                "provider": provider or "searxng",
                "search_results": [
                    {
                        "title": "Automatic Identification System",
                        "url": "https://example.test/ais",
                        "snippet": "AIS can refer to several things.",
                    }
                ],
            },
        }

    tool = Tool(
        "web_search",
        "Search the web.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "provider": {"type": "string"},
                "provider_strict": {"type": "boolean"},
            },
        },
        web_search,
        start_metadata=lambda args: {
            "provider": args.get("provider") or "searxng",
            "query": args.get("query"),
        },
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    list(agent.run("what is AIS?"))
    use_events = list(agent.run("use exa to search"))
    can_events = list(agent.run("can you search using exa"))

    assert seen_args[1] == {
        "query": "AIS",
        "provider": "exa",
        "provider_strict": True,
    }
    assert use_events[0].payload["provider"] == "exa"
    assert use_events[0].payload["args"]["provider"] == "exa"
    assert use_events[0].payload["args"]["query"] == "AIS"
    assert seen_args[2] == {
        "query": "AIS",
        "provider": "exa",
        "provider_strict": True,
    }
    assert can_events[0].payload["provider"] == "exa"
    assert can_events[0].payload["args"]["provider"] == "exa"
    assert can_events[0].payload["args"]["query"] == "AIS"


def test_look_it_up_inherits_pending_foundation_evidence_gap():
    from klaude_core.agent import (
        ClaimIntent,
        ConversationEntity,
        EvidenceGap,
        RetrievalConversationState,
        _contextual_search_query,
        _should_plan_search,
    )

    state = RetrievalConversationState(
        active_entities=[
            ConversationEntity(
                mention="AIS",
                canonical_name="American Intercon School",
                entity_type="school",
                location="Cambodia",
                official_domains=("ais.edu.kh",),
                confidence=0.95,
                unresolved=False,
            )
        ],
        last_claim_intent=ClaimIntent.DURATION,
        pending_evidence_gap=EvidenceGap(
            requested_claim="establishment date",
            supported_by_existing_evidence=False,
            missing_fields=["founding_date"],
            requires_new_retrieval=True,
        ),
    )
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "AIS school in Cambodia"},
        {
            "role": "assistant",
            "content": "AIS means American Intercon School in Cambodia.",
        },
        {"role": "user", "content": "how long has it been operating?"},
        {"role": "assistant", "content": "I could not verify the founding date yet."},
        {"role": "user", "content": "look it up"},
    ]

    assert _should_plan_search("look it up", messages) is True
    query = _contextual_search_query("look it up", "look it up", messages, state)

    assert query == "When was American Intercon School in Cambodia established?"
    assert query != "AIS school Cambodia"


def test_web_unavailable_claim_triggers_registered_web_search_tool():
    from klaude_core import Agent, PermissionGate, Tool

    calls = []

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": "I cannot perform real-time web searches.",
                }
            assert messages[-1]["role"] == "tool"
            return {"role": "assistant", "content": "I searched instead."}

    def web_search(query):
        calls.append(query)
        return {
            "content": "Found 1 relevant result.",
            "metadata": {"provider": "searxng", "search_results": []},
        }

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        web_search,
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    events = list(agent.run("tell me the current public result for AIS"))

    assert calls
    assert events[-2].payload["content"] == "I searched instead."


def test_segment_user_input_keeps_greeting_and_lookup_intents():
    from klaude_core.agent import segment_user_input

    segments = segment_user_input("hi\nwhere is AIS?")

    assert [(segment.text, segment.intent) for segment in segments] == [
        ("hi", "greeting"),
        ("where is AIS?", "web_lookup"),
    ]
    assert segments[1].requires_retrieval is True


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_multi_intent_greeting_runs_lookup_before_answer():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            assert messages[-1]["role"] == "tool"
            assert "found where is AIS" in messages[-1]["content"]
            return {"role": "assistant", "content": "Hi! AIS is ambiguous."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    events = list(agent.run("hi\nwhere is AIS?"))

    assert events[0].kind == "tool_start"
    assert events[0].payload["args"]["query"] == "where is AIS"
    assert events[-2].payload["content"] == "Hi! AIS is ambiguous."


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_web_search_start_metadata_survives_automatic_routing():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {"role": "assistant", "content": "Found it."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
        start_metadata=lambda args: {
            "provider": "ddgs",
            "query": args["query"],
            "canonical_tool": "web_search",
        },
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    events = list(agent.run("where is AIS?"))

    assert events[0].kind == "tool_start"
    assert events[0].payload["provider"] == "ddgs"
    assert events[0].payload["query"] == "where is AIS"
    assert events[0].payload["metadata"]["canonical_tool"] == "web_search"


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_search_does_not_prefetch_candidate_or_verification_links():
    from klaude_core import Agent, PermissionGate, Tool

    fetched_urls = []

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {"role": "assistant", "content": "I verified the school pages."}

    def web_search(query):
        assert "AIS school" in query
        assert "Cambodia" in query
        return {
            "content": "Found 1 relevant result.",
            "metadata": {
                "provider": "searxng",
                "search_results": [
                    {
                        "title": "AIS Cambodia School",
                        "url": "https://americanintercon.edu.kh/",
                        "snippet": "AIS is a Cambodian school with campuses in Phnom Penh.",
                    }
                ],
            },
        }

    def fetch_url(url):
        fetched_urls.append(url)
        if url == "https://americanintercon.edu.kh/":
            return {
                "content": (
                    "AIS school home page with admissions, campuses, students, "
                    "and academic program information."
                ),
                "metadata": {
                    "verification_links": [
                        "https://americanintercon.edu.kh/about",
                        "https://americanintercon.edu.kh/contact",
                    ]
                },
            }
        return {
            "content": "American Intercon School is in Phnom Penh, Cambodia.",
            "metadata": {},
        }

    tools = [
        Tool(
            "web_search",
            "Search the web.",
            {"type": "object", "properties": {"query": {"type": "string"}}},
            web_search,
        ),
        Tool(
            "fetch_url",
            "Fetch a page.",
            {"type": "object", "properties": {"url": {"type": "string"}}},
            fetch_url,
        ),
    ]
    agent = Agent(
        FakeOllama(),
        "fake-model",
        tools,
        PermissionGate({"web_search": "allow", "fetch_url": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search", "fetch_url"],
    )

    events = list(agent.run("AIS school in Cambodia"))

    assert fetched_urls == []
    assert [
        event.payload.get("tool")
        for event in events
        if event.kind == "tool_result"
    ] == ["web_search"]


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_unfamiliar_name_runs_web_lookup_before_no_info_answer():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            assert messages[-1]["role"] == "tool"
            assert "found Who is chansovisoth" in messages[-1]["content"]
            return {"role": "assistant", "content": "I could not verify a public profile."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    events = list(agent.run("chansovisoth"))

    assert events[0].kind == "tool_start"
    assert events[0].payload["args"]["query"] == "Who is chansovisoth"


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_queries_local_knowledge_before_web_for_technical_question():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            assert messages[-1]["role"] == "tool"
            assert messages[-1]["tool_name"] == "query_knowledge"
            return {"role": "assistant", "content": "Camera3D uses projection settings."}

    tools = [
        Tool(
            "query_knowledge",
            "Search local knowledge.",
            {"type": "object", "properties": {"query": {"type": "string"}}},
            lambda query: f"local docs for {query}",
        ),
        Tool(
            "web_search",
            "Search web.",
            {"type": "object", "properties": {"query": {"type": "string"}}},
            lambda query: f"web for {query}",
        ),
    ]
    agent = Agent(
        FakeOllama(),
        "fake-model",
        tools,
        PermissionGate(
            {"query_knowledge": "allow", "web_search": "allow"},
            lambda tool, detail: "y",
        ),
        "system",
        tool_selector=lambda _message, _tools: ["query_knowledge", "web_search"],
    )

    events = list(agent.run("How does Godot Camera3D work?"))

    assert events[0].payload["tool"] == "query_knowledge"
    assert not any(
        event.payload.get("tool") == "web_search"
        for event in events
        if event.kind == "tool_start"
    )


def test_agent_rejects_stale_fetch_after_school_constraint():
    from klaude_core import Agent, PermissionGate, Tool

    fetched = []

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            if messages[-1]["role"] == "tool":
                return {"role": "assistant", "content": "Skipped stale source."}
            return {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "fetch_url",
                            "arguments": {"url": "https://ais-inc.com/"},
                        }
                    }
                ],
                "content": "",
            }

    def fetch_url(url):
        fetched.append(url)
        return "office furniture page"

    agent = Agent(
        FakeOllama(),
        "fake-model",
        [
            Tool(
                "fetch_url",
                "Fetch.",
                {"type": "object", "properties": {"url": {"type": "string"}}},
                fetch_url,
            )
        ],
        PermissionGate({"fetch_url": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["fetch_url"],
    )
    agent.messages.append(
        {
            "role": "tool",
            "tool_name": "web_search",
            "content": "Found AIS Inc.",
            "metadata": {
                "search_results": [
                    {
                        "title": "Homepage - AIS Inc",
                        "url": "https://ais-inc.com/",
                        "snippet": "Affordable office furniture.",
                    }
                ]
            },
        }
    )

    events = list(agent.run("it's a school"))

    assert fetched == []
    assert events[0].kind == "tool_result"
    assert events[0].payload["metadata"]["rejected_fetch_candidate"] is True


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_skips_near_duplicate_web_searches():
    from klaude_core import Agent, PermissionGate, Tool

    calls = []

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "web_search",
                                "arguments": {"query": "Rhett and Link"},
                            }
                        }
                    ],
                    "content": "",
                }
            if self.calls == 2:
                return {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "web_search",
                                "arguments": {"query": "who are Rhett and Link"},
                            }
                        }
                    ],
                    "content": "",
                }
            return {"role": "assistant", "content": "Done."}

    tool = Tool(
        "web_search",
        "Search.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: calls.append(query) or f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    events = list(agent.run("who are Rhett and Link"))

    assert calls == ["who are Rhett and Link"]
    assert any(
        event.kind == "tool_result"
        and event.payload["metadata"].get("duplicate_search_query")
        for event in events
    )


def test_agent_does_not_repeat_identical_provider_query_and_options():
    from klaude_core import Agent, PermissionGate, Tool

    calls = []

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls <= 2:
                return {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "web_search",
                                "arguments": {
                                    "query": "Cambodian startups",
                                    "provider": "tavily",
                                    "provider_strict": True,
                                    "max_results": 12,
                                },
                            }
                        }
                    ],
                    "content": "",
                }
            return {"role": "assistant", "content": "Done."}

    def web_search(query, provider="", provider_strict=False, max_results=12):
        calls.append((query, provider, provider_strict, max_results))
        return {
            "content": "Synthetic result",
            "metadata": {
                "search_results": [
                    {
                        "title": "Asteron Labs",
                        "url": "https://asteron.example/",
                        "snippet": "A Cambodian startup.",
                    }
                ]
            },
        }

    tool = Tool(
        "web_search",
        "Search.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "provider": {"type": "string"},
                "provider_strict": {"type": "boolean"},
                "max_results": {"type": "integer"},
            },
        },
        web_search,
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda _message, _tools: ["web_search"],
    )

    events = list(agent.run("show me some startups in Cambodia"))

    assert calls == [("Cambodian startups", "tavily", True, 12)]
    duplicate = next(
        event
        for event in events
        if event.kind == "tool_result"
        and event.payload["metadata"].get("duplicate_search_strategy")
    )
    assert '"provider":"tavily"' in duplicate.payload["metadata"][
        "search_attempt_fingerprint"
    ]


def test_agent_executes_json_text_form_tool_call():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": '<function=query_knowledge> {"query": "C++"} </tool_call>',
                }
            return {"role": "assistant", "content": "No local C++ docs found."}

    tool = Tool(
        "query_knowledge",
        "Search local knowledge.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"searched {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"query_knowledge": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("do you have local knowledge of C++?"))

    assert events[0].kind == "tool_start"
    assert events[0].payload == {
        "tool": "query_knowledge",
        "args": {"query": "C++"},
    }
    assert events[1].kind == "tool_result"
    assert "searched C++" in events[1].payload["result"]


def test_agent_executes_text_form_tool_call_with_newline_before_close():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": (
                        "<function=web_search> "
                        "<parameter=query> FlazeSlayer YouTube channel\n"
                        "</tool_call>"
                    ),
                }
            return {"role": "assistant", "content": "FlazeSlayer is a creator."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("more about them"))

    assert events[0].kind == "tool_start"
    assert events[0].payload == {
        "tool": "web_search",
        "args": {"query": "FlazeSlayer YouTube channel"},
    }
    assert events[1].kind == "tool_result"
    assert "found FlazeSlayer YouTube channel" in events[1].payload["result"]


def test_agent_strips_text_form_closing_tags_from_tool_args():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": (
                        "<function=fetch_url> "
                        "<parameter=url> https://www.twitch.tv/flaze_slayer "
                        "</parameter> </function> </tool_call>"
                    ),
                }
            return {"role": "assistant", "content": "Fetched the profile."}

    tool = Tool(
        "fetch_url",
        "Fetch a URL.",
        {"type": "object", "properties": {"url": {"type": "string"}}},
        lambda url: f"fetched {url}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"fetch_url": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("what games"))

    assert events[0].kind == "tool_start"
    assert events[0].payload == {
        "tool": "fetch_url",
        "args": {"url": "https://www.twitch.tv/flaze_slayer"},
    }
    assert "fetched https://www.twitch.tv/flaze_slayer" in events[1].payload["result"]


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_rewrites_vague_search_followup_with_recent_topic():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            assert messages[-1]["role"] == "tool"
            assert "found FlazeSlayer games" in messages[-1]["content"]
            if self.calls == 1:
                return {"role": "assistant", "content": "They play Minecraft and Roblox."}
            raise AssertionError("model should answer after the planned search")

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )
    agent.messages.extend(
        [
            {"role": "user", "content": "who is FlazeSlayer"},
            {"role": "assistant", "content": "FlazeSlayer is a gaming creator."},
        ]
    )

    events = list(agent.run("what games"))

    assert events[0].kind == "tool_start"
    assert events[0].payload == {
        "tool": "web_search",
        "args": {"query": "FlazeSlayer games"},
    }
    assert events[-2].payload["content"] == "They play Minecraft and Roblox."


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_followup_last_name_uses_person_name_not_university_acronym():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            assert messages[-1]["role"] == "tool"
            assert "found Chansovisoth Wattanak" in messages[-1]["content"]
            assert "PIU last name" not in messages[-1]["content"]
            if self.calls == 1:
                return {"role": "assistant", "content": "Their last name appears to be Wattanak."}
            raise AssertionError("model should answer after the planned search")

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )
    agent.messages.extend(
        [
            {"role": "user", "content": "who is Chansovisoth"},
            {
                "role": "tool",
                "tool_name": "web_search",
                "content": (
                    "[1] Chansovisoth Wattanak - Computer Science Senior at PIU\n"
                    "https://kh.linkedin.com/in/chansovisoth\n"
                    "Chansovisoth Wattanak's profile on LinkedIn."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Chansovisoth Wattanak is a computer science senior at "
                    "Paragon International University (PIU) in Cambodia."
                ),
            },
        ]
    )

    events = list(agent.run("what is their last name"))

    assert events[0].payload == {
        "tool": "web_search",
        "args": {"query": "Chansovisoth Wattanak"},
    }
    assert events[-2].payload["content"] == "Their last name appears to be Wattanak."


def test_agent_pronoun_lookup_without_recent_topic_asks_before_searching():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {"role": "assistant", "content": "Who do you mean?"}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("what is their last name"))

    assert [event.kind for event in events] == ["text", "done"]
    assert events[0].payload["content"] == "Who do you mean?"


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_fetches_only_the_search_result_selected_by_the_model():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            assert messages[-1]["role"] == "tool"
            if self.calls == 1:
                assert "New Bio" in messages[-1]["content"]
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "fetch_url",
                                "arguments": {
                                    "url": "https://www.youtube.com/@Flazeslayer/search"
                                },
                            }
                        }
                    ],
                }
            assert "Minecraft and Roblox" in messages[-1]["content"]
            return {"role": "assistant", "content": "They mention Minecraft and Roblox."}

    def web_search(query):
        assert query == "FlazeSlayer games"
        return (
            "[1] FlazeSlayer - YouTube\n"
            "https://www.youtube.com/@Flazeslayer/search\n"
            "New Bio - I am Flaze."
        )

    def fetch_url(url):
        assert url == "https://www.youtube.com/@Flazeslayer/search"
        return "Description: I record a lot of games video like Minecraft and Roblox."

    tools = [
        Tool(
            "web_search",
            "Search the web.",
            {"type": "object", "properties": {"query": {"type": "string"}}},
            web_search,
        ),
        Tool(
            "fetch_url",
            "Fetch a URL.",
            {"type": "object", "properties": {"url": {"type": "string"}}},
            fetch_url,
        ),
    ]
    agent = Agent(
        FakeOllama(),
        "fake-model",
        tools,
        PermissionGate({"web_search": "allow", "fetch_url": "allow"}, lambda tool, detail: "y"),
        "system",
    )
    agent.messages.extend(
        [
            {"role": "user", "content": "who is FlazeSlayer"},
            {"role": "assistant", "content": "FlazeSlayer is a gaming creator."},
        ]
    )

    events = list(agent.run("what games"))

    assert [event.kind for event in events] == [
        "tool_start",
        "tool_result",
        "tool_start",
        "tool_result",
        "text",
        "done",
    ]
    assert events[2].payload == {
        "tool": "fetch_url",
        "args": {"url": "https://www.youtube.com/@Flazeslayer/search"},
    }
    assert events[-2].payload["content"] == "They mention Minecraft and Roblox."


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_directly_returns_requested_search_result_count():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            raise AssertionError("model should not run for an explicit raw result list")

    def web_search(query, max_results=12):
        assert query == "FlazeSlayer"
        assert max_results == 20
        return "\n\n".join(
            f"[{index}] Result {index}\nhttps://example.test/{index}\nSnippet {index}"
            for index in range(1, 21)
        )

    tool = Tool(
        "web_search",
        "Search the web.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
        },
        web_search,
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("show me 20 results about FlazeSlayer"))

    assert [event.kind for event in events] == ["tool_start", "tool_result", "text", "done"]
    assert events[0].payload == {
        "tool": "web_search",
        "args": {"query": "FlazeSlayer", "max_results": 20},
    }
    assert "[20] Result 20" in events[2].payload["content"]


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_raw_result_followup_uses_recent_topic_without_command_words():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            raise AssertionError("model should not run for an explicit raw result list")

    def web_search(query, max_results=12):
        assert query == "FlazeSlayer"
        assert max_results == 20
        return "[1] FlazeSlayer - YouTube\nhttps://www.youtube.com/@Flazeslayer/search\nBio"

    tool = Tool(
        "web_search",
        "Search the web.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
        },
        web_search,
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )
    agent.messages.extend(
        [
            {"role": "user", "content": "who is FlazeSlayer"},
            {"role": "assistant", "content": "FlazeSlayer is a gaming creator."},
        ]
    )

    events = list(agent.run("show me 20 search results"))

    assert events[0].payload == {
        "tool": "web_search",
        "args": {"query": "FlazeSlayer", "max_results": 20},
    }
    assert events[-2].payload["content"].startswith("[1] FlazeSlayer")


def test_agent_rewrites_model_raw_result_tool_query_to_recent_topic():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls > 1:
                return {"role": "assistant", "content": "Here are the results."}
            return {
                "role": "assistant",
                "content": (
                    "<function=web_search> "
                    "<parameter=query> show me 20 search results </tool_call>"
                ),
            }

    def web_search(query):
        assert query == "FlazeSlayer"
        return "[1] FlazeSlayer - YouTube\nhttps://www.youtube.com/@Flazeslayer/search\nBio"

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        web_search,
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda message, tools: ["web_search"],
    )
    agent.messages.extend(
        [
            {"role": "user", "content": "who is FlazeSlayer"},
            {"role": "assistant", "content": "FlazeSlayer is a gaming creator."},
        ]
    )

    events = list(agent.run("more results"))

    assert events[0].payload == {
        "tool": "web_search",
        "args": {"query": "FlazeSlayer"},
    }


def test_agent_does_not_search_low_info_raw_result_request_without_topic():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {"role": "assistant", "content": "What should I search for?"}

    tool = Tool(
        "web_search",
        "Search the web.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
        },
        lambda query, max_results=12: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("show me 20 search results"))

    assert [event.kind for event in events] == ["text", "done"]
    assert events[0].payload["content"] == "What should I search for?"


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_promised_search_is_converted_to_tool_call():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {"role": "assistant", "content": "I'll search for that."}
            assert messages[-1]["role"] == "tool"
            assert "found FlazeSlayer" in messages[-1]["content"]
            return {"role": "assistant", "content": "Here are the results."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("FlazeSlayer"))

    assert events[0].kind == "tool_start"
    assert events[-2].payload["content"] == "Here are the results."


def test_agent_suppresses_structured_tool_call_preamble():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": "I cannot find anything yet.",
                    "tool_calls": [
                        {"function": {"name": "web_search", "arguments": {"query": "FlazeSlayer"}}}
                    ],
                }
            return {"role": "assistant", "content": "FlazeSlayer is a YouTube creator."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("who is FlazeSlayer"))

    assert events[0].kind == "tool_start"
    assert not any(
        event.kind == "text" and "cannot find" in event.payload.get("content", "")
        for event in events
    )


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_runs_web_search_before_no_info_answer():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            assert messages[-1]["role"] == "tool"
            assert "found who is FlazeSlayer" in messages[-1]["content"]
            if self.calls == 1:
                return {"role": "assistant", "content": "FlazeSlayer is a YouTube creator."}
            raise AssertionError("model should answer after the planned search")

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda message, tools: ["web_search"],
    )

    events = list(agent.run("who is FlazeSlayer"))

    assert events[0].kind == "tool_start"
    assert events[0].payload == {
        "tool": "web_search",
        "args": {"query": "who is FlazeSlayer"},
    }
    assert events[1].kind == "tool_result"
    assert events[-2].payload["content"] == "FlazeSlayer is a YouTube creator."


@pytest.mark.skip(reason="superseded by model-directed retrieval tests")
def test_agent_fallback_search_uses_recent_topic_for_pronoun_followup():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            assert messages[-1]["role"] == "tool"
            assert "found FlazeSlayer play minecraft" in messages[-1]["content"]
            if self.calls == 1:
                return {"role": "assistant", "content": "They appear to play Minecraft."}
            raise AssertionError("model should answer after the planned search")

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda message, tools: ["web_search"],
    )
    agent.messages.extend(
        [
            {"role": "user", "content": "who is FlazeSlayer"},
            {"role": "assistant", "content": '"FlazeSlayer" appears to be a creator.'},
        ]
    )

    events = list(agent.run("do they play minecraft"))

    assert events[0].kind == "tool_start"
    assert events[0].payload == {
        "tool": "web_search",
        "args": {"query": "FlazeSlayer play minecraft"},
    }
    assert events[-2].payload["content"] == "They appear to play Minecraft."


def test_agent_return_direct_tool_skips_model_summary():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {
                "role": "assistant",
                "content": "<function=list_commands> {} </tool_call>",
            }

    tool = Tool(
        "list_commands",
        "Show commands.",
        {"type": "object", "properties": {}},
        lambda: "Usage: klaude [OPTIONS] COMMAND [ARGS]...",
        return_direct=True,
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"list_commands": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("what commands can I use?"))

    assert [event.kind for event in events] == ["tool_start", "text", "done"]
    assert events[1].payload["content"] == "Usage: klaude [OPTIONS] COMMAND [ARGS]..."


def test_agent_return_direct_tool_preserves_structured_metadata():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {
                "role": "assistant",
                "content": "<function=list_commands> {} </tool_call>",
            }

    metadata = {
        "content_type": "command_reference",
        "preserve_whitespace": True,
        "direct_render": True,
    }
    tool = Tool(
        "list_commands",
        "Show commands.",
        {"type": "object", "properties": {}},
        lambda: {
            "content": "Usage: klaude [OPTIONS] COMMAND [ARGS]...\n\nCLI COMMANDS",
            "metadata": metadata,
        },
        return_direct=True,
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"list_commands": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("what commands can I use?"))

    assert [event.kind for event in events] == ["tool_start", "text", "done"]
    assert events[1].payload["content"].endswith("\n\nCLI COMMANDS")
    assert events[1].payload["metadata"] == metadata


def test_structured_and_text_form_list_commands_render_identically():
    from klaude_core import Agent, PermissionGate, Tool

    metadata = {
        "content_type": "command_reference",
        "preserve_whitespace": True,
        "direct_render": True,
    }

    class StructuredOllama:
        def chat(self, model, messages, tools=None):
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "list_commands", "arguments": {}}}],
            }

    class TextFormOllama:
        def chat(self, model, messages, tools=None):
            return {
                "role": "assistant",
                "content": "<function=list_commands> {} </tool_call>",
            }

    def make_agent(ollama):
        tool = Tool(
            "list_commands",
            "Show commands.",
            {"type": "object", "properties": {}},
            lambda: {
                "content": "Usage: klaude [OPTIONS] COMMAND [ARGS]...\n\nCLI COMMANDS",
                "metadata": metadata,
            },
            return_direct=True,
        )
        return Agent(
            ollama,
            "fake-model",
            [tool],
            PermissionGate({"list_commands": "allow"}, lambda tool, detail: "y"),
            "system",
        )

    structured_events = list(make_agent(StructuredOllama()).run("show commands"))
    text_form_events = list(make_agent(TextFormOllama()).run("show commands"))

    assert structured_events[1].payload == text_form_events[1].payload


def test_agent_rejects_unnecessary_structured_list_commands_for_casual_prompt():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "list_commands", "arguments": {}}}],
                }
            assert messages[-1]["role"] == "tool"
            assert "unnecessary for this conversational request" in messages[-1]["content"]
            return {
                "role": "assistant",
                "content": "Hi! I'm Klaude, a local-first coding assistant.",
            }

    tool = Tool(
        "list_commands",
        "Return command reference.",
        {"type": "object", "properties": {}},
        lambda: "Usage: klaude [OPTIONS] COMMAND [ARGS]...",
        return_direct=True,
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"list_commands": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("hi, who might you be"))

    assert events[0].kind == "tool_result"
    assert events[0].payload["tool"] == "list_commands"
    assert events[0].payload["metadata"]["suppress_user_output"] is True
    assert events[-2].payload["content"].startswith("Hi! I'm Klaude")
    assert not any(
        "Usage: klaude" in event.payload.get("content", "")
        for event in events
        if event.kind == "text"
    )


def test_agent_rejects_unnecessary_text_form_list_commands_for_casual_prompt():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": "<function=list_commands> {} </tool_call>",
                }
            assert messages[-1]["role"] == "tool"
            return {
                "role": "assistant",
                "content": "I can help with code, local knowledge, and web research when needed.",
            }

    tool = Tool(
        "list_commands",
        "Return command reference.",
        {"type": "object", "properties": {}},
        lambda: "Usage: klaude [OPTIONS] COMMAND [ARGS]...",
        return_direct=True,
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"list_commands": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("what can you do"))

    assert events[0].kind == "tool_result"
    assert events[0].payload["metadata"]["recoverable_tool_policy"] is True
    assert "Usage: klaude" not in events[-2].payload["content"]


def test_agent_tool_selector_limits_tools_for_plain_chat():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.seen_tools = None

        def chat(self, model, messages, tools=None):
            self.seen_tools = tools
            return {"role": "assistant", "content": "Hello."}

    tool = Tool(
        "web_search",
        "Search the web.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    ollama = FakeOllama()
    agent = Agent(
        ollama,
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=lambda message, tools: [],
    )

    events = list(agent.run("hi there"))

    assert events[0].payload["content"] == "Hello."
    assert ollama.seen_tools == []


def test_agent_tool_selection_handles_command_then_casual_turns():
    from klaude_core import Agent, PermissionGate, Tool

    seen_tools = []

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            names = [tool["function"]["name"] for tool in (tools or [])]
            seen_tools.append(names)
            if names == ["list_commands"]:
                return {
                    "role": "assistant",
                    "content": "<function=list_commands> {} </tool_call>",
                }
            return {"role": "assistant", "content": "Hi! I'm Klaude."}

    tool = Tool(
        "list_commands",
        "Return command reference.",
        {"type": "object", "properties": {}},
        lambda: "Usage: klaude [OPTIONS] COMMAND [ARGS]...",
        return_direct=True,
    )

    def selector(message, tools):
        if message == "show commands":
            return ["list_commands"]
        return []

    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"list_commands": "allow"}, lambda tool, detail: "y"),
        "system",
        tool_selector=selector,
    )

    command_events = list(agent.run("show commands"))
    casual_events = list(agent.run("hi"))

    assert command_events[-2].payload["content"].startswith("Usage: klaude")
    assert casual_events[0].payload["content"] == "Hi! I'm Klaude."
    assert seen_tools == [["list_commands"], []]


def test_agent_passes_ollama_options_to_chat():
    from klaude_core import Agent, PermissionGate

    class CapturingOllama:
        def __init__(self):
            self.options = None

        def chat(self, model, messages, tools=None, options=None):
            self.options = options
            return {"role": "assistant", "content": "done"}

    ollama = CapturingOllama()
    agent = Agent(
        ollama,
        "fake-model",
        [],
        PermissionGate({}, lambda tool, detail: "y"),
        "system",
        ollama_options={"num_ctx": 8192, "num_thread": 6},
    )

    list(agent.run("hi"))

    assert ollama.options == {"num_ctx": 8192, "num_thread": 6}


def test_unknown_text_form_tool_call_produces_clean_tool_error():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def __init__(self):
            self.calls = 0

        def chat(self, model, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {
                    "role": "assistant",
                    "content": "<function=unknown_tool> <parameter=query> x </tool_call>",
                }
            assert messages[-1]["role"] == "tool"
            assert "unknown tool 'unknown_tool'" in messages[-1]["content"]
            return {"role": "assistant", "content": "I cannot use that tool."}

    tool = Tool(
        "web_search",
        "Search.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
        lambda query: f"found {query}",
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        [tool],
        PermissionGate({"web_search": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("use a tool"))

    assert events[0].kind == "tool_result"
    assert events[0].payload["result"] == "error: unknown tool 'unknown_tool'"
    assert not any(
        event.kind == "text" and "<function=unknown_tool>" in event.payload.get("content", "")
        for event in events
    )


def test_model_can_select_one_of_multiple_structured_search_results():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            assert messages[-1]["role"] == "tool"
            if messages[-1].get("tool_name") == "web_search":
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "fetch_url",
                                "arguments": {"url": "https://example.com/bio"},
                            }
                        }
                    ],
                }
            assert "usable biography text" in messages[-1]["content"]
            return {"role": "assistant", "content": "Fetched a usable source."}

    fetched = []

    def web_search(query):
        return {
            "content": "[1] A\nhttps://linkedin.com/in/example\n\n[2] B\nhttps://example.com/bio",
            "metadata": {
                "search_results": [
                    {"title": "A", "url": "https://linkedin.com/in/example", "snippet": ""},
                    {"title": "B", "url": "https://example.com/bio", "snippet": ""},
                ]
            },
        }

    def fetch_url(url):
        fetched.append(url)
        if "linkedin" in url:
            raise RuntimeError("blocked")
        return "usable biography text with enough detail to be considered useful"

    agent = Agent(
        FakeOllama(),
        "fake-model",
        [
            Tool(
                "web_search",
                "Search.",
                {"type": "object", "properties": {"query": {"type": "string"}}},
                web_search,
            ),
            Tool(
                "fetch_url",
                "Fetch.",
                {"type": "object", "properties": {"url": {"type": "string"}}},
                fetch_url,
            ),
        ],
        PermissionGate({"web_search": "allow", "fetch_url": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    events = list(agent.run("who is Example Person"))

    assert fetched == ["https://example.com/bio"]
    assert [event.kind for event in events[:4]] == [
        "tool_start",
        "tool_result",
        "tool_start",
        "tool_result",
    ]


def test_duplicate_search_result_urls_are_not_automatically_fetched():
    from klaude_core import Agent, PermissionGate, Tool

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {"role": "assistant", "content": "Done."}

    fetched = []

    def web_search(query):
        return {
            "content": "[1] A\nhttps://bad.example/page\n\n[2] A copy\nhttps://bad.example/page",
            "metadata": {
                "search_results": [
                    {"title": "A", "url": "https://bad.example/page", "snippet": ""},
                    {"title": "A copy", "url": "https://bad.example/page", "snippet": ""},
                ]
            },
        }

    def fetch_url(url):
        fetched.append(url)
        raise RuntimeError("blocked")

    agent = Agent(
        FakeOllama(),
        "fake-model",
        [
            Tool(
                "web_search",
                "Search.",
                {"type": "object", "properties": {"query": {"type": "string"}}},
                web_search,
            ),
            Tool(
                "fetch_url",
                "Fetch.",
                {"type": "object", "properties": {"url": {"type": "string"}}},
                fetch_url,
            ),
        ],
        PermissionGate({"web_search": "allow", "fetch_url": "allow"}, lambda tool, detail: "y"),
        "system",
    )

    list(agent.run("who is Example Person"))

    assert fetched == []
