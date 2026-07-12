import random

from klaude_knowledge.chunker import chunk_markdown
from klaude_knowledge.hybrid import _rrf
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
    all_rows = store.fts.execute(
        "SELECT COUNT(*) FROM chunks WHERE collection='nextjs'"
    ).fetchone()[0]
    assert all_rows == n


def test_rrf_prefers_agreement():
    a = [{"id": "x", "text": "x"}, {"id": "y", "text": "y"}]
    b = [{"id": "y", "text": "y"}, {"id": "z", "text": "z"}]
    merged = _rrf([a, b])
    assert merged[0]["id"] == "y"  # appears in both lists


def test_cache_ttl(tmp_path):
    from klaude_web.cache import TTLCache

    c = TTLCache(tmp_path / "c.db")
    c.set("k", {"v": 1}, ttl_seconds=60)
    assert c.get("k") == {"v": 1}
    c.set("k2", "gone", ttl_seconds=-1)
    assert c.get("k2") is None


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
