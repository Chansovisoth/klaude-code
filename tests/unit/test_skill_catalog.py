import base64
import hashlib
import json
from dataclasses import replace

import httpx
import pytest
from klaude_core.skill_catalog import (
    MAX_RESPONSE_BYTES,
    CatalogHTTP,
    CatalogStatus,
    SearchRequest,
    SkillRecord,
    clean_text,
    download_resolved_skill,
    merge_resolved,
    resolve_source,
    search,
)


def mp_payload(items=None, *, has_next=False):
    return {"success": True, "data": {"skills": items if items is not None else [{
        "id": "one", "name": "testing", "description": "Long useful description",
        "githubUrl": "https://github.com/example/repo/tree/main/skills/testing",
        "stars": 42, "contentLanguage": "en", "updatedAt": 1778999500,
    }], "pagination": {"hasNext": has_next}}}


def test_search_sends_only_query_filters_without_environment_credentials(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://localhost:1")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-not-sent")
    seen = []

    def handler(request):
        seen.append(request)
        assert "authorization" not in request.headers
        return httpx.Response(200, json=mp_payload(has_next=True))

    result = search(SearchRequest("python", sort="recent", page=2),
                    transport=httpx.MockTransport(handler))
    assert result.status == CatalogStatus.OK and result.has_next
    assert dict(seen[0].url.params) == {"q": "python", "limit": "20", "page": "2",
                                      "sortBy": "recent"}
    record = result.records[0]
    assert record.popularity.metric == "Repository stars"
    assert record.repository == "example/repo"
    assert record.catalog_updated == "2026-05-17 06:31 UTC"
    assert not record.skill_path and not record.revision and not record.license


@pytest.mark.parametrize("updated", [True, "not-a-date", "1778999500000", 0, "x" * 10_000])
def test_unrecognized_catalog_update_remains_unknown(updated):
    payload = mp_payload([{"id": "one", "name": "testing", "updatedAt": updated}])
    result = search(SearchRequest("python"), transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=payload)))
    assert result.status == CatalogStatus.OK
    assert result.records[0].catalog_updated == ""


@pytest.mark.parametrize("updated", ["1778999500", "2026-05-17T06:31:00Z"])
def test_supported_string_catalog_update_is_utc(updated):
    payload = mp_payload([{"id": "one", "name": "testing", "updatedAt": updated}])
    result = search(SearchRequest("python"), transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=payload)))
    assert result.records[0].catalog_updated == "2026-05-17 06:31 UTC"


@pytest.mark.parametrize("code,status", [(401, "auth"), (403, "auth"), (429, "rate_limit"),
                                         (503, "unavailable"), (302, "malformed")])
def test_catalog_http_errors_are_typed_without_raw_messages(code, status):
    result = search(SearchRequest("python"), transport=httpx.MockTransport(
        lambda _: httpx.Response(code, json={"error": "secret provider detail"})))
    assert result.status == status and not result.records
    assert "secret" not in str(result.payload())


@pytest.mark.parametrize("exception,status", [(httpx.ConnectError, "network"),
                                              (httpx.ReadTimeout, "timeout")])
def test_transport_failures(exception, status):
    def fail(request):
        raise exception("private details", request=request)

    assert search(SearchRequest("python"), transport=httpx.MockTransport(fail)).status == status


@pytest.mark.parametrize("payload", [[], {}, {"success": False}, mp_payload([{}])])
def test_unsupported_response(payload):
    assert search(SearchRequest("python"), transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=payload))).status == CatalogStatus.MALFORMED


def test_empty_and_oversized_response():
    assert search(SearchRequest("python"), transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=mp_payload([])))).status == CatalogStatus.EMPTY
    result = search(SearchRequest("python"), transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))))
    assert result.status == CatalogStatus.MALFORMED


def test_unicode_terminal_metadata_sanitized_and_bounded():
    raw = "\x1b[31mtest\x1b[0m\x1b]0;danger\x07\u202e\x00" + "x" * 3000
    payload = mp_payload([{"id": "one", "name": raw, "description": raw}])
    result = search(SearchRequest("python"), transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=payload)))
    assert result.status == CatalogStatus.OK
    assert result.records[0].name == "test" + "x" * 196
    assert len(result.records[0].description) == 2000
    assert clean_text("\x9b31mhello\x9b0m") == "hello"


def test_provider_identity_is_never_truncated_into_a_colliding_row_id():
    prefix = "x" * 512
    payload = mp_payload([{"id": prefix + "a", "name": "first"},
                          {"id": prefix + "b", "name": "second"}])
    response = search(SearchRequest("python"), transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=payload)))
    assert response.status == CatalogStatus.MALFORMED
    assert not response.records


def test_oversized_source_claim_is_dropped_instead_of_cut_to_a_different_path():
    source = "https://github.com/org/repo/tree/main/skills/" + "x" * 1000
    payload = mp_payload([{"id": "one", "name": "test", "githubUrl": source}])
    response = search(SearchRequest("python"), transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=payload)))
    assert response.status == CatalogStatus.OK
    assert response.records[0].source_url == ""
    assert response.records[0].repository == ""


def test_skills_sh_provisional_shape_and_installs_not_stars():
    def handler(request):
        assert request.url.path == "/api/search"
        assert dict(request.url.params) == {"q": "python", "limit": "20"}
        return httpx.Response(200, json={"skills": [{"id": "org/repo/testing",
                              "name": "testing", "source": "org/repo", "installs": 13}]})

    record = search(SearchRequest("python", "skills.sh", "relevance"),
                    transport=httpx.MockTransport(handler)).records[0]
    assert record.popularity.metric == "Installs"
    assert record.repository == "org/repo" and not record.skill_path


def test_pinned_skill_download_reads_full_folder_and_verifies_git_blobs():
    revision = "a" * 40
    roots = ["b" * 40, "c" * 40, "d" * 40]
    files = {
        "SKILL.md": b"---\nname: example\n---\nUse this skill\n",
        "references/guide.md": b"A supporting guide\n",
    }

    def blob_sha(body):
        return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()

    skill_sha = blob_sha(files["SKILL.md"])
    guide_sha = blob_sha(files["references/guide.md"])
    seen = []

    def handler(request):
        path = request.url.path
        seen.append(path)
        if path.endswith("/commits/" + revision):
            data = {"sha": revision, "tree": {"sha": roots[0]}}
        elif path.endswith("/trees/" + roots[0]):
            data = {"sha": roots[0], "truncated": False, "tree": [
                {"path": "skills", "type": "tree", "mode": "040000", "sha": roots[1]},
            ]}
        elif path.endswith("/trees/" + roots[1]):
            data = {"sha": roots[1], "truncated": False, "tree": [
                {"path": "example", "type": "tree", "mode": "040000", "sha": roots[2]},
            ]}
        elif path.endswith("/trees/" + roots[2]):
            data = {"sha": roots[2], "truncated": False, "tree": [
                {"path": "SKILL.md", "type": "blob", "mode": "100644", "sha": skill_sha,
                 "size": len(files["SKILL.md"])},
                {"path": "references", "type": "tree", "mode": "040000", "sha": "e" * 40},
            ]}
        elif path.endswith("/trees/" + "e" * 40):
            data = {"sha": "e" * 40, "truncated": False, "tree": [
                {"path": "guide.md", "type": "blob", "mode": "100644", "sha": guide_sha,
                 "size": len(files["references/guide.md"])},
            ]}
        elif path.endswith("/blobs/" + skill_sha):
            data = {"sha": skill_sha, "encoding": "base64", "size": len(files["SKILL.md"]),
                    "content": base64.b64encode(files["SKILL.md"]).decode()}
        elif path.endswith("/blobs/" + guide_sha):
            data = {"sha": guide_sha, "encoding": "base64",
                    "size": len(files["references/guide.md"]),
                    "content": base64.b64encode(files["references/guide.md"]).decode()}
        else:
            pytest.fail(f"Unexpected GitHub request: {path}")
        return httpx.Response(200, json=data)

    record = SkillRecord(
        "skillsmp", "one", "example", repository="org/repo",
        source_url="https://github.com/org/repo/tree/main/skills/example",
        skill_path="skills/example/SKILL.md", revision=revision,
    )
    assert download_resolved_skill(record, transport=httpx.MockTransport(handler)) == files
    assert len(seen) == 7
    assert all(path.startswith("/repos/org/repo/git/") for path in seen)


@pytest.mark.parametrize("entry", [
    {"path": "SKILL.md", "type": "blob", "mode": "120000", "sha": "f" * 40, "size": 9},
    {"path": "../outside", "type": "blob", "mode": "100644", "sha": "f" * 40,
     "size": 9},
])
def test_remote_skill_download_rejects_symlinks_and_unsafe_paths(entry):
    revision, root = "a" * 40, "b" * 40
    record = SkillRecord("skillsmp", "one", "example", repository="org/repo",
                         source_url="https://github.com/org/repo/tree/main/example",
                         skill_path="example/SKILL.md", revision=revision)

    def handler(request):
        if request.url.path.endswith("/commits/" + revision):
            return httpx.Response(200, json={"sha": revision, "tree": {"sha": root}})
        if request.url.path.endswith("/trees/" + root):
            return httpx.Response(200, json={"sha": root, "truncated": False, "tree": [
                {"path": "example", "type": "tree", "mode": "040000", "sha": "c" * 40},
            ]})
        if request.url.path.endswith("/trees/" + "c" * 40):
            return httpx.Response(200, json={"sha": "c" * 40, "truncated": False,
                                              "tree": [entry]})
        pytest.fail("Unsafe entry was fetched")

    with pytest.raises(ValueError, match="symlink|Unsafe"):
        download_resolved_skill(record, transport=httpx.MockTransport(handler))


def test_remote_skill_download_rejects_blob_content_that_disagrees_with_git_identity():
    revision, root, folder = "a" * 40, "b" * 40, "c" * 40
    expected = b"# Verified skill\n"
    blob_sha = hashlib.sha1(f"blob {len(expected)}\0".encode() + expected).hexdigest()
    record = SkillRecord("skillsmp", "one", "example", repository="org/repo",
                         source_url="https://github.com/org/repo/tree/main/example",
                         skill_path="example/SKILL.md", revision=revision)

    def handler(request):
        path = request.url.path
        if path.endswith("/commits/" + revision):
            data = {"sha": revision, "tree": {"sha": root}}
        elif path.endswith("/trees/" + root):
            data = {"sha": root, "truncated": False, "tree": [
                {"path": "example", "type": "tree", "mode": "040000", "sha": folder},
            ]}
        elif path.endswith("/trees/" + folder):
            data = {"sha": folder, "truncated": False, "tree": [
                {"path": "SKILL.md", "type": "blob", "mode": "100644", "sha": blob_sha,
                 "size": len(expected)},
            ]}
        elif path.endswith("/blobs/" + blob_sha):
            tampered = b"# Modified skill\n"
            assert len(tampered) == len(expected)
            data = {"sha": blob_sha, "encoding": "base64", "size": len(expected),
                    "content": base64.b64encode(tampered).decode()}
        else:
            pytest.fail(f"Unexpected request: {path}")
        return httpx.Response(200, json=data)

    with pytest.raises(ValueError, match="integrity check"):
        download_resolved_skill(record, transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("kwargs", [{"query": ""}, {"query": "x\x00"}, {"query": "x" * 121},
                                     {"query": "x", "page": 11},
                                     {"query": "x", "provider": "unknown"},
                                     {"query": "x", "provider": "skills.sh", "sort": "stars"}])
def test_request_bounds(kwargs):
    with pytest.raises(ValueError):
        SearchRequest(**kwargs)


def test_identity_does_not_merge_duplicate_names_or_unresolved_paths():
    records = (SkillRecord("skillsmp", "one", "test", repository="org/one"),
               SkillRecord("skillsmp", "two", "test", repository="org/two"),
               SkillRecord("skills.sh", "one", "test", repository="org/one"))
    assert len({r.identity for r in records}) == 3
    assert len(merge_resolved(records)) == 3
    resolved = tuple(replace(r, repository="org/one", skill_path="skills/test/SKILL.md",
                             revision="a" * 40) for r in records)
    groups = merge_resolved(resolved)
    assert len(groups) == 1 and len(groups[0]) == 3
    other_path = replace(resolved[1], skill_path="other/SKILL.md")
    assert len(merge_resolved((resolved[0], other_path))) == 2


def test_source_resolution_uses_pinned_commit_and_individual_frontmatter():
    sha = "a" * 40
    body = '---\nname: test\nlicense: MIT\ncompatibility: "Requires Node 20"\n---\nInstructions'
    seen = []

    def handler(request):
        seen.append(request)
        if "/git/matching-refs/" in request.url.path:
            return httpx.Response(200, json=[{"ref": "refs/heads/main", "object": {"sha": sha}}])
        if "/commits/" in request.url.path:
            assert "/git/commits/" in request.url.path
            return httpx.Response(200, json={"sha": sha, "committer": {
                "date": "2026-10-03T00:00:00Z"}})
        assert request.url.params["ref"] == sha
        return httpx.Response(200, json={"type": "file", "path": "skills/test/SKILL.md",
                                        "size": len(body), "encoding": "base64",
                                        "content": base64.b64encode(body.encode()).decode()})

    record = SkillRecord("skillsmp", "one", "test", repository="org/repo",
                         source_url="https://github.com/org/repo/tree/main/skills/test")
    resolved = resolve_source(record, transport=httpx.MockTransport(handler))
    assert resolved["status"] == "ok"
    item = SkillRecord.from_payload(resolved["record"])
    assert item.revision == sha and item.skill_path == "skills/test/SKILL.md"
    assert item.license == "MIT" and sha in item.license_source
    assert item.compatibility == "Requires Node 20"
    assert item.source_activity == "2026-10-03 00:00 UTC"
    assert len(seen) == 3 and all(r.url.host == "api.github.com" for r in seen)


def test_installed_skill_update_checks_same_path_at_verified_default_branch():
    from klaude_core.skill_catalog import check_github_skill_update

    old, new = "a" * 40, "b" * 40
    body = "---\nname: test\nlicense: MIT\n---\nUpdated instructions"
    seen = []

    def handler(request):
        seen.append(str(request.url))
        path = request.url.path
        if path == "/repos/org/repo":
            return httpx.Response(200, json={"default_branch": "main"})
        if "/git/matching-refs/heads/main" in path:
            return httpx.Response(200, json=[{
                "ref": "refs/heads/main", "object": {"sha": new},
            }])
        if path.endswith("/git/commits/" + new):
            return httpx.Response(200, json={"sha": new, "committer": {
                "date": "2026-10-03T00:00:00Z"}})
        assert path.endswith("/contents/skills/test/SKILL.md")
        assert request.url.params["ref"] == new
        return httpx.Response(200, json={
            "type": "file", "path": "skills/test/SKILL.md", "size": len(body),
            "encoding": "base64", "content": base64.b64encode(body.encode()).decode(),
        })

    source = f"https://github.com/org/repo/blob/{old}/skills/test/SKILL.md"
    result = check_github_skill_update("test", source, old,
                                       transport=httpx.MockTransport(handler))
    assert result["status"] == "available"
    record = SkillRecord.from_payload(result["record"])
    assert record.revision == new and record.skill_path == "skills/test/SKILL.md"
    assert record.license == "MIT"
    assert len(seen) == 4
    assert check_github_skill_update("test", source, "c" * 40,
                                     transport=httpx.MockTransport(handler)) == {
        "status": "unsupported"
    }


def test_missing_source_path_or_license_never_becomes_permissive():
    record = SkillRecord("skills.sh", "one", "test", repository="org/repo",
                         source_url="https://github.com/org/repo")
    def fail(_):
        pytest.fail("No network without a resolvable path")
    response = resolve_source(record, transport=httpx.MockTransport(fail))
    assert response["status"] == "unresolved" and not response["record"]["license"]


def test_http_total_deadline_and_origin_boundary():
    from klaude_core.skill_catalog import CatalogFailure

    client = CatalogHTTP(httpx.MockTransport(lambda _: pytest.fail("network")))
    client.deadline = 0
    with pytest.raises(CatalogFailure) as error:
        client.get("https://skillsmp.com/api/v1/skills/search")
    assert error.value.status == "timeout"
    with pytest.raises(CatalogFailure):
        client.get("https://localhost/private")


def test_worker_record_rejects_unsafe_metadata_and_invalid_timestamp():
    payload = SkillRecord("skillsmp", "one", "test").payload()
    for field, value in (("name", "\x1b[31msecret"), ("description", "x" * 2001),
                         ("fetched_at", float("nan")), ("source_url", "https://localhost/private")):
        with pytest.raises(ValueError):
            SkillRecord.from_payload({**payload, field: value})
    json.dumps(payload)


def test_branch_names_with_slashes_resolve_actual_path_not_first_slash_guess():
    sha = "b" * 40
    original = SkillRecord("skillsmp", "one", "test", repository="org/repo",
                           source_url="https://github.com/org/repo/tree/release/v1/skills/test")

    def handler(request):
        if "/git/matching-refs/" in request.url.path:
            return httpx.Response(200, json=[
                {"ref": "refs/heads/release", "object": {"sha": "a" * 40}},
                {"ref": "refs/heads/release/v1", "object": {"sha": sha}},
            ])
        if "/commits/" in request.url.path:
            assert request.url.path.endswith(sha)
            return httpx.Response(200, json={"sha": sha})
        assert request.url.path.endswith("/contents/skills/test/SKILL.md")
        assert request.url.params["ref"] == sha
        body = "---\nname: test\n---\nNo license field"
        return httpx.Response(200, json={"path": "skills/test/SKILL.md", "type": "file",
                                        "size": len(body), "encoding": "base64",
                                        "content": base64.b64encode(body.encode()).decode()})

    response = resolve_source(original, transport=httpx.MockTransport(handler))
    assert response["status"] == "ok"
    assert response["record"]["skill_path"] == "skills/test/SKILL.md"
    assert response["record"]["revision"] == sha
    assert not response["record"]["license"]


def test_github_missing_ref_remains_unresolved_and_rate_limit_honest():
    record = SkillRecord("skillsmp", "one", "test", repository="org/repo",
                         source_url="https://github.com/org/repo/tree/main/test")
    missing = resolve_source(record, transport=httpx.MockTransport(
        lambda _: httpx.Response(404, json={})))
    assert missing["status"] == "unresolved" and not missing["record"]["revision"]
    limited = resolve_source(record, transport=httpx.MockTransport(
        lambda _: httpx.Response(403, headers={"X-RateLimit-Remaining": "0"})))
    assert limited["status"] == "rate_limit"
