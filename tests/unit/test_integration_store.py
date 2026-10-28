"""Store metadata is bounded; only exact reviewed records can reach installation."""

import base64
import json
import uuid

import httpx
import pytest
from klaude_application import integration_store
from klaude_application.integration_store import IntegrationStore
from klaude_application.operation_journal import OperationFenceLost
from klaude_core.mcp_client import MCPRegistry

from .test_web_management import _review, _submit
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request

SHA = "a" * 40


def transport(state):
    def handle(request):
        state.setdefault("calls", []).append(request)
        assert "authorization" not in request.headers
        if state.get("offline"):
            return httpx.Response(503)
        if request.url.path == "/v0.1/servers":
            if request.url.params.get("search") == "ordering":
                return httpx.Response(200, json={"servers": [
                    {"server": {"name": "io.example/" + name, "title": title,
                                "version": "1", "description": "Ordering fixture",
                                "repository": {"url": "https://github.com/example/" + repo}},
                     "_meta": {"io.modelcontextprotocol.registry/official": {
                         "status": "active", "isLatest": True, "updatedAt": updated}}}
                    for name, title, repo, updated in (
                        ("recent", "Recent tools", "repo", "2026-10-28T00:00:00Z"),
                        ("popular", "Popular tools", "search", "2026-10-01T00:00:00Z"),
                    )
                ]})
            if request.url.params.get("search") == "many":
                return httpx.Response(200, json={"servers": [
                    {"server": {"name": f"io.example/server-{i}", "version": "1",
                                "description": "A catalog integration",
                                "repository": {"url": "https://github.com/example/search"}},
                     "_meta": {"io.modelcontextprotocol.registry/official": {
                         "status": "active", "isLatest": True}}}
                    for i in range(int(request.url.params["limit"]))
                ]})
            return httpx.Response(
                200,
                json={
                    "servers": [
                        {
                            "server": {
                                "name": "io.example/search",
                                "title": "Search tools",
                                "description": "Find project documentation",
                                "version": "2" if state.get("changed") else "1",
                                "repository": {"url": "https://github.com/example/search"},
                                "remotes": [
                                    {"type": "streamable-http", "url": "https://example.test/mcp"}
                                ],
                            },
                            "_meta": {
                                "io.modelcontextprotocol.registry/official": {
                                    "status": "active",
                                    "isLatest": True,
                                    "updatedAt": "2026-10-01T02:00:00+02:00",
                                }
                            },
                        },
                        {
                            "server": {
                                "name": "io.example/package",
                                "description": "Package setup",
                                "version": "1",
                                "packages": [],
                            },
                            "_meta": {
                                "io.modelcontextprotocol.registry/official": {
                                    "status": "active",
                                    "isLatest": True,
                                    "updatedAt": "2026-10-28T00:00:00Z",
                                }
                            },
                        },
                    ]
                },
            )
        if request.url.host == "skillsmp.com":
            if request.url.params.get("q") == "ordering":
                items = [
                    {"id": "popular", "name": "Popular older skill", "stars": 12500,
                     "githubUrl": "https://github.com/example/search/tree/main/skills/testing",
                     "updatedAt": "2026-10-01T00:00:00Z"},
                    {"id": "recent", "name": "Recent skill", "stars": 777,
                     "githubUrl": "https://github.com/example/repo/tree/main/skills/testing",
                     "updatedAt": "2026-10-28T00:00:00Z"},
                ]
                if request.url.params["sortBy"] == "recent":
                    items.reverse()
                return httpx.Response(200, json={"success": True, "data": {
                    "skills": items, "pagination": {"hasNext": False},
                }})
            if request.url.params.get("q") == "many":
                page = int(request.url.params["page"])
                return httpx.Response(200, json={"success": True, "data": {
                    "skills": [{"id": f"skill-{i}", "name": f"Skill {i}",
                                "githubUrl": "https://github.com/example/repo/tree/main/skills/testing"}
                               for i in range((page - 1) * 20, page * 20)],
                    "pagination": {"hasNext": page < 3},
                }})
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "skills": [
                            {
                                "id": "test",
                                "name": "testing",
                                "description": "Test a project",
                                "githubUrl": "https://github.com/example/repo/tree/main/skills/testing",
                                "stars": 42,
                                "updatedAt": "2026-10-27T18:00:00Z",
                            }
                        ],
                        "pagination": {"hasNext": False},
                    },
                },
            )
        if request.url.host == "skills.sh":
            return httpx.Response(
                200,
                json={"skills": [{"id": "other", "name": "repo-only", "source": "example/repo"}]},
            )
        if request.url.path in {"/repos/example/search", "/repos/example/repo"}:
            return httpx.Response(
                state.get("github_status", 200),
                json={"stargazers_count": state.get(
                    "stars", 12500 if request.url.path.endswith("/search") else 777
                )},
            )
        if "/git/matching-refs/" in request.url.path:
            return httpx.Response(200, json=[{"ref": "refs/heads/main", "object": {"sha": SHA}}])
        if "/git/commits/" in request.url.path:
            return httpx.Response(
                200, json={"sha": SHA, "committer": {"date": "2026-10-28T00:00:00Z"}}
            )
        if "/contents/" in request.url.path:
            assert request.url.params["ref"] == SHA
            path = "skills/testing/SKILL.md"
            body = b"---\nname: testing\nlicense: MIT\n---\nTest instructions."
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "path": path,
                    "encoding": "base64",
                    "size": len(body),
                    "content": base64.b64encode(body).decode(),
                },
            )
        raise AssertionError(str(request.url))

    return httpx.MockTransport(handle)


@pytest.fixture
def store(profile_browser):
    host, service, _, auth = profile_browser
    state = {}
    service.integration_store = IntegrationStore(service.cfg, transport=transport(state))
    return host, service, auth, state


def test_catalogs_cache_metadata_and_never_fetch_packages(store):
    host, service, auth, state = store
    assert _request(host, "GET", "/api/v1/session", **auth)[2]["integration_store"]
    for kind in ("mcps", "skills"):
        url = f"/api/v1/store/integrations?kind={kind}"
        status, _, data = _request(host, "GET", url, **auth)
        assert status == 200 and data["items"]
        assert "raw" not in json.dumps(data)
        before = len(state["calls"])
        assert _request(host, "GET", url, **auth)[2] == data
        assert len(state["calls"]) == before
    assert {r.url.host for r in state["calls"]} == {
        "registry.modelcontextprotocol.io",
        "skillsmp.com",
    }
    assert not list(service.cfg.skills_dir.iterdir())
    assert MCPRegistry(service.cfg.mcp_servers_file).load() == {}


def test_mcp_catalog_requests_forty_and_skills_keep_supported_source_pages(store):
    _, service, _, state = store
    result = service.integration_store.catalog("mcps", "many")
    assert len(result["items"]) == result["page_size"] == 40
    assert state["calls"][-1].url.params["limit"] == "40"
    pages = [service.integration_store.catalog("skills", "many", page=page) for page in (1, 2, 3)]
    assert all(len(page["items"]) == page["page_size"] == 20 for page in pages)
    assert len({item["id"] for page in pages for item in page["items"]}) == 60
    assert [page["more"] for page in pages] == [True, True, False]


def test_integration_ordering_uses_supported_source_sorts_and_separate_caches(store):
    host, service, auth, state = store
    facade = service.integration_store
    assert _request(host, "GET", "/api/v1/session", **auth)[2]["integration_store_sort"]
    stars = facade.catalog("skills", "ordering", sort="stars")
    recent = facade.catalog("skills", "ordering", sort="recent")
    assert [row["name"] for row in stars["items"]] == ["Popular older skill", "Recent skill"]
    assert [row["name"] for row in recent["items"]] == ["Recent skill", "Popular older skill"]
    assert [r.url.params["sortBy"] for r in state["calls"]] == ["stars", "recent"]
    before = len(state["calls"])
    assert facade.catalog("skills", "ordering", sort="stars") == stars
    assert facade.catalog("skills", "ordering", sort="recent") == recent
    assert len(state["calls"]) == before
    assert recent["items"][0]["updated_at"] == "2026-10-28T00:00:00Z"
    status, _, ordered = _request(
        host, "GET", "/api/v1/store/integrations?kind=mcps&sort=recent", **auth
    )
    assert status == 200 and ordered["sort"] == "recent"
    assert [row["name"] for row in ordered["items"]] == ["package", "Search tools"]
    assert ordered["items"][1]["updated_at"] == "2026-10-01T00:00:00Z"
    assert not any(r.url.host == "api.github.com" for r in state["calls"])
    before = len(state["calls"])
    for params in ("kind=skills&sort=bad", "kind=mcps&sort=stars&sort=recent",
                   "kind=skills&provider=skills.sh&sort=recent"):
        assert _request(host, "GET", "/api/v1/store/integrations?" + params, **auth)[0] == 503
    assert len(state["calls"]) == before


@pytest.mark.parametrize("value, expected", [
    ("2026-10-28T09:00:00+09:00", "2026-10-28T00:00:00Z"),
    ("2026-10-28 00:00 UTC", "2026-10-28T00:00:00Z"),
    ("2026-10-28", ""), ("not a date", ""), (None, ""),
])
def test_update_dates_remain_source_derived_and_timezone_aware(value, expected):
    assert integration_store._updated(value) == expected


def test_repository_stars_are_lazy_shared_and_distinct_from_catalog_metrics(store):
    host, service, auth, state = store
    assert _request(host, "GET", "/api/v1/session", **auth)[2]["integration_store_stars"]
    mcps = service.integration_store.catalog("mcps")["items"]
    skill = service.integration_store.catalog("skills")["items"][0]
    other = service.integration_store.catalog("skills", provider="skills.sh")["items"][0]
    assert not any(r.url.host == "api.github.com" for r in state["calls"])
    assert mcps[0]["github_repository"] == "example/search"
    for item, count in ((mcps[0], 12500), (skill, 777), (other, 777), (mcps[1], None)):
        status, _, result = _request(
            host, "GET", f"/api/v1/store/integrations/stars?id={item['id']}", **auth
        )
        assert status == 200 and result["id"] == item["id"]
        assert result["stars"] == count and not result["stale"]
    # The two Skill catalogs share a repository; SkillsMP's reported 42 is not
    # presented as a live GitHub count, and an absent repository stays unknown.
    assert len([r for r in state["calls"] if r.url.host == "api.github.com"]) == 2
    before = len(state["calls"])
    reloaded = IntegrationStore(service.cfg, transport=transport(state))
    assert reloaded.repository_stars(skill["id"])["stars"] == 777
    assert len(state["calls"]) == before
    for query in ("id=../secret", "id=" + "a" * 64,
                  f"id={skill['id']}&url=https://example.test", f"id={skill['id']}&id=x"):
        assert _request(host, "GET", "/api/v1/store/integrations/stars?" + query, **auth)[0] == 503
    assert _request(host, "GET", f"/api/v1/store/integrations/stars?id={skill['id']}")[0] == 401
    assert len(state["calls"]) == before


def test_repository_stars_zero_rate_limit_and_stale_expiry(store):
    _, service, _, state = store
    facade = service.integration_store
    item = facade.catalog("skills")["items"][0]
    state["stars"] = 0
    assert facade.repository_stars(item["id"])["stars"] == 0
    path = facade.root / "repository-stars.json"

    def expire(age):
        records = json.loads(path.read_text())
        value = records["example/repo"]
        value["attempted_at"] = integration_store.time.time() - 3601
        value["checked_at"] = integration_store.time.time() - age
        path.write_text(json.dumps(records))

    expire(3601)
    state["github_status"] = 429
    cached = facade.repository_stars(item["id"])
    assert cached["stars"] == 0 and cached["stale"]
    before = len(state["calls"])
    assert facade.repository_stars(item["id"]) == cached
    assert len(state["calls"]) == before
    expire(8 * 86400)
    unknown = facade.repository_stars(item["id"])
    assert unknown["stars"] is None and unknown["stale"]
    # Repeated failure after a negative cache expires still leaves it unknown.
    expire(8 * 86400)
    assert facade.repository_stars(item["id"])["stars"] is None


def test_cached_catalog_upgrade_keeps_stars_and_unsafe_repository_is_not_read(store):
    _, service, _, state = store
    facade = service.integration_store
    item = facade.catalog("mcps")["items"][0]
    for path in facade.root.glob("*.json"):
        value = json.loads(path.read_text())
        if "result" in value:
            for row in value["result"]["items"]:
                row.pop("github_repository", None)
            path.write_text(json.dumps(value))
    before = len(state["calls"])
    assert facade.catalog("mcps")["items"][0]["github_repository"] == "example/search"
    value = facade._read(item["id"])
    value["payload"]["repository_url"] = "https://github.com/example/search/tree/main"
    facade._save(item["id"], value)
    assert facade.repository_stars(item["id"])["stars"] is None
    assert len(state["calls"]) == before


def test_mcp_review_uses_fresh_plan_then_existing_disabled_writer(store):
    host, service, auth, state = store
    found = service.integration_store.catalog("mcps")["items"]
    assert found[0]["can_install"] and not found[1]["can_install"]
    draft = {"operation": "mcp-store-add", "id": found[0]["id"], "name": "store-search"}
    review = _review(host, auth, draft)
    assert review["operation"] == "mcp-add"
    before = len(state["calls"])
    receipt, body = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    assert len(state["calls"]) == before
    server = MCPRegistry(service.cfg.mcp_servers_file).load()["store-search"]
    assert server.enabled is False and server.url == "https://example.test/mcp"
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    state["changed"] = True
    with pytest.raises(ValueError, match="changed"):
        service.prepare("test", {**draft, "name": "other"})


def test_skill_requires_verified_exact_source_and_review_never_downloads(store):
    host, service, auth, state = store
    item = service.integration_store.catalog("skills")["items"][0]
    draft = {"operation": "skill-store-install", "id": item["id"], "name": "testing"}
    with pytest.raises(ValueError, match="Verify"):
        service.prepare("test", draft)
    url = f"/api/v1/store/integrations/detail?id={item['id']}&resolve=1"
    status, _, full = _request(host, "GET", url, **auth)
    assert status == 200 and full["revision"] == SHA and full["can_install"]
    before = len(state["calls"])
    review = _review(host, auth, draft)
    assert SHA in review["summary"] and "embedding" in review["summary"]
    assert len(state["calls"]) == before
    assert not list(service.cfg.skills_dir.iterdir())
    assert not any("/git/blobs/" in r.url.path for r in state["calls"])
    for bad in ("Testing", "test.name", "../bad", "x" * 81):
        with pytest.raises(ValueError):
            service.prepare("test", {**draft, "name": bad})
    existing = service.cfg.skills_dir / "testing"
    existing.mkdir()
    with pytest.raises(ValueError, match="already"):
        service.prepare("test", draft)


def test_repo_only_source_must_match_catalog_repository(store):
    _, service, _, state = store
    item = service.integration_store.catalog("skills", provider="skills.sh")["items"][0]
    assert not item["can_resolve"] and not item["can_install"]
    with pytest.raises(ValueError):
        service.integration_store.detail(
            item["id"],
            resolve=True,
            source="https://github.com/attacker/repo/blob/main/skills/testing/SKILL.md",
        )
    full = service.integration_store.detail(
        item["id"],
        resolve=True,
        source="https://github.com/example/repo/blob/main/skills/testing/SKILL.md",
    )
    assert full["can_install"] and full["revision"] == SHA
    assert all(r.url.host in {"skills.sh", "api.github.com"} for r in state["calls"])


def test_outage_retains_cached_items_and_invalid_filters_do_not_fetch(store):
    host, service, auth, state = store
    first = service.integration_store.catalog("skills")
    state["offline"] = True
    fallback = service.integration_store.catalog("skills", refresh=True)
    assert fallback["items"] == first["items"] and fallback["stale"] and fallback["error"]
    assert service.integration_store.catalog("skills", "other")["items"] == []
    before = len(state["calls"])
    for query in ("x" * 121, "bad\n"):
        with pytest.raises(ValueError):
            service.integration_store.catalog("skills", query)
    assert (
        _request(host, "GET", "/api/v1/store/integrations?kind=skills&kind=mcps", **auth)[0] == 503
    )
    assert _request(host, "GET", "/api/v1/store/integrations/detail?id=../secret", **auth)[0] == 503
    assert len(state["calls"]) == before


def test_store_writes_keep_admin_and_csrf_checks_at_review_and_submit(store):
    host, service, auth, _ = store
    item = service.integration_store.catalog("mcps")["items"][0]
    draft = {"operation": "mcp-store-add", "id": item["id"], "name": "search"}
    bad = {**auth, "csrf": "invalid"}
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": draft}, **bad)[0] == 403
    review = _review(host, auth, draft)
    host.http.host_lan = True
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": draft}, **auth)[0] == 403
    body = {"review_id": review["review_id"], "request_id": uuid.uuid4().hex, "control_epoch": 0}
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 403
    skill = service.integration_store.catalog("skills")["items"][0]
    assert (
        _request(
            host,
            "POST",
            "/api/v1/library/review",
            body={
                "draft": {"operation": "skill-store-install", "id": skill["id"], "name": "testing"}
            },
            **auth,
        )[0]
        == 403
    )


def test_skill_effect_gate_is_rechecked_inside_import_after_download(store, monkeypatch):
    _, service, _, _ = store
    item = service.integration_store.catalog("skills")["items"][0]
    service.integration_store.detail(item["id"], resolve=True)
    fields, resource, _ = service.integration_store.skill_fields(
        {"operation": "skill-store-install", "id": item["id"], "name": "testing"}
    )
    rid = uuid.uuid4().hex
    receipt = service.journal.admit(
        request_id=rid,
        owner_id="web-admin",
        kind="skill-store-install",
        resource=resource,
        payload=fields,
    )
    service.journal.start(rid, "web-admin", receipt.fence)
    called = []

    def imported(cfg, record, *, overwrite, before_effect, checkpoint):
        called.append(record)
        assert record.revision == SHA and not overwrite
        service.journal.request_cancel(rid, "web-admin")
        before_effect()
        raise AssertionError("Effect gate must reject publication")

    monkeypatch.setattr("klaude_knowledge.skill_management.import_remote_skill", imported)
    with pytest.raises(OperationFenceLost):
        integration_store.install_skill(
            service.cfg, {"request_id": rid, "fence": receipt.fence, **fields}
        )
    assert len(called) == 1


def test_skill_recovery_routes_require_admin_csrf_and_exact_evidence(store):
    host, service, auth, _ = store
    from klaude_application.skill_store_operations import initial

    item = service.integration_store.catalog("skills")["items"][0]
    service.integration_store.detail(item["id"], resolve=True)
    fields, resource, _ = service.integration_store.skill_fields(
        {"operation": "skill-store-install", "id": item["id"], "name": "testing"}
    )
    rid = uuid.uuid4().hex
    receipt = service.journal.admit(request_id=rid, owner_id="web-admin",
                                    kind="skill-store-install", resource=resource, payload=fields)
    service.journal.save_evidence(rid, "web-admin", receipt.fence, initial(fields["record"]))
    service.journal.start(rid, "web-admin", receipt.fence)
    service.journal.mark_unknown(rid, "web-admin", receipt.fence)
    path = "/api/v1/skills/install/inspect"
    body = {"request_id": rid}
    assert _request(host, "POST", path, body=body, **{**auth, "csrf": "bad"})[0] == 403
    status, _, result = _request(host, "POST", path, body=body, **auth)
    assert status == 200 and result["decision"] == "proven_no_effect"
    path = "/api/v1/skills/install/reconcile"
    assert _request(host, "POST", path, body={**body, "fingerprint": "bad"}, **auth)[0] == 409
    assert _request(host, "POST", path, body={**body, "fingerprint": result["fingerprint"]},
                    **auth)[0] == 200
    assert service.status(rid)["state"] == "failed"
    host.http.host_lan = True
    assert _request(host, "POST", path, body=body, **auth)[0] == 403


def test_reviewed_skill_import_preserves_pinned_source_and_never_runs_scripts(store, monkeypatch):
    from klaude_knowledge import skill_management

    _, service, _, _ = store
    item = service.integration_store.catalog("skills")["items"][0]
    service.integration_store.detail(item["id"], resolve=True)
    fields, resource, _ = service.integration_store.skill_fields(
        {
            "operation": "skill-store-install",
            "id": item["id"],
            "name": "testing",
        }
    )
    rid = uuid.uuid4().hex
    receipt = service.journal.admit(
        request_id=rid,
        owner_id="web-admin",
        kind="skill-store-install",
        resource=resource,
        payload=fields,
    )
    service.journal.start(rid, "web-admin", receipt.fence)
    real_import = skill_management.import_remote_skill
    downloaded = []

    def download(record, **_):
        downloaded.append(record)
        return {
            "SKILL.md": b"# Testing\nUse focused tests.",
            "scripts/example.py": b"raise RuntimeError('must never execute')",
        }

    class Knowledge:
        def replace_owner_snapshot_atomic(self, library, owner, documents):
            assert library == "testing" and owner == "skill:testing"
            assert documents
            return len(documents)

    monkeypatch.setattr(skill_management, "download_resolved_skill", download)
    # This focused fixture has an in-memory index, so the separate postcondition
    # inspector is covered by the recovery tests with a real SQLite snapshot.
    monkeypatch.setattr("klaude_application.skill_store_operations.verify_complete",
                        lambda cfg, evidence: True)
    monkeypatch.setattr(
        skill_management,
        "import_remote_skill",
        lambda cfg, record, **kwargs: real_import(cfg, record, knowledge=Knowledge(), **kwargs),
    )
    assert integration_store.install_skill(
        service.cfg,
        {
            "request_id": rid,
            "fence": receipt.fence,
            **fields,
        },
    ) == {"ok": True}
    manifest = json.loads((service.cfg.skills_dir / "testing" / "manifest.json").read_text())
    assert manifest["source_revision"] == SHA
    assert (
        manifest["source"] == f"https://github.com/example/repo/blob/{SHA}/skills/testing/SKILL.md"
    )
    assert len(downloaded) == 1 and downloaded[0].revision == SHA
    assert not list(service.cfg.skills_dir.glob(".remote-*"))
