import json
import threading
import zipfile

import pytest
from klaude_cli.skill_actions import SkillAction, SkillActionWriter
from klaude_core.skill_catalog import SkillRecord
from klaude_knowledge.skill_management import (
    delete_installed_skill,
    import_remote_skill,
    import_skill_inbox,
    manifest_identity,
    set_installed_skill_enabled,
)
from klaude_knowledge.skills import finalize_skill_package, install_skill_package
from klaude_knowledge.store import KnowledgeStore


class FakeConfig:
    def __init__(self, root):
        self._root = root
        self.snapshot_retention = 1

    @property
    def skills_dir(self):
        path = self._root / "skills"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def knowledge_dir(self):
        path = self._root / "knowledge"
        path.mkdir(parents=True, exist_ok=True)
        return path


def test_delete_skill_rejects_changed_manifest_then_removes_only_its_owner(tmp_path):
    cfg = FakeConfig(tmp_path)
    source = tmp_path / "demo.md"
    source.write_text("# Demo")
    installed = install_skill_package(cfg, source, name="demo", library="shared")
    finalize_skill_package(installed)
    store = KnowledgeStore(cfg.knowledge_dir)
    for library, owner, uri in [
        ("shared", "skill:demo", "skill://demo/demo.md"),
        ("old", "skill:demo", "skill://demo/old.md"),
        ("shared", "skill:other", "skill://other/other.md"),
        ("shared", "learn:https://example.com", "https://example.com"),
    ]:
        version = store.stage_version(library, owner, uri, [owner], [[1.0, 0.0]], "checksum")
        store.activate_versions(library, owner, {uri: version})
    original = installed.manifest_path.read_bytes()
    data = json.loads(original)
    data["checked_at"] = "changed"
    installed.manifest_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="changed"):
        delete_installed_skill(cfg, "demo", manifest_identity(original))
    assert installed.root.exists()
    assert store.active_owner_checksums("shared", "skill:demo")
    identity = manifest_identity(installed.manifest_path.read_bytes())
    delete_installed_skill(cfg, "demo", identity)
    assert not installed.root.exists()
    assert not store.active_owner_checksums("shared", "skill:demo")
    assert not store.active_owner_checksums("old", "skill:demo")
    assert store.active_owner_checksums("shared", "skill:other")
    assert store.active_owner_checksums("shared", "learn:https://example.com")
    assert not store.fts.execute("SELECT 1 FROM chunks_v2 WHERE owner='skill:demo'").fetchone()
    store.fts.close()


def test_skill_activation_persists_and_excludes_only_that_skill_from_retrieval(tmp_path):
    cfg = FakeConfig(tmp_path)
    source = tmp_path / "demo.md"
    source.write_text("# Demo")
    installed = install_skill_package(cfg, source, name="demo", library="shared")
    finalize_skill_package(installed)
    identity = manifest_identity(installed.manifest_path.read_bytes())
    store = KnowledgeStore(cfg.knowledge_dir)
    skill_uri = "skill://demo/demo.md"
    doc_uri = "https://example.com/guide"
    for owner, uri, text in [
        ("skill:demo", skill_uri, "galactic foraging skill"),
        ("learn:guide", doc_uri, "galactic navigation guide"),
    ]:
        version = store.stage_version("shared", owner, uri, [text], [[1.0, 0.0]], "sum")
        store.activate_versions("shared", owner, {uri: version})
    assert store.keyword_search("shared", "foraging", 5)
    assert store.source_exists("shared", skill_uri, "skill:demo")

    set_installed_skill_enabled(cfg, "demo", identity, False)
    reopened = KnowledgeStore(cfg.knowledge_dir)
    assert reopened.keyword_search("shared", "foraging", 5) == []
    assert reopened.vector_search("shared", [1.0, 0.0], 5)
    assert all(hit["source"] != skill_uri for hit in reopened.vector_search(
        "shared", [1.0, 0.0], 5
    ))
    assert not reopened.source_exists("shared", skill_uri)
    assert skill_uri not in reopened.library_sources("shared")
    assert reopened.keyword_search("shared", "navigation", 5)
    with pytest.raises(ValueError, match="changed"):
        set_installed_skill_enabled(cfg, "demo", "stale", True)
    assert reopened.keyword_search("shared", "foraging", 5) == []

    set_installed_skill_enabled(cfg, "demo", identity, True)
    assert reopened.keyword_search("shared", "foraging", 5)
    assert reopened.source_exists("shared", skill_uri)
    reopened.fts.close()
    store.fts.close()


def test_delete_rejects_traversal_and_symlink(tmp_path):
    cfg = FakeConfig(tmp_path)
    with pytest.raises(ValueError, match="Invalid"):
        delete_installed_skill(cfg, "../other", "")
    (cfg.skills_dir / "demo").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="Unsafe"):
        delete_installed_skill(cfg, "demo", "")


def test_inbox_import_archives_success_and_retains_failure_without_overwrite(tmp_path, monkeypatch):
    from klaude_knowledge import skill_management

    cfg = FakeConfig(tmp_path)
    inbox = tmp_path / "skills-inbox"
    inbox.mkdir()
    (inbox / "good.md").write_text("# Good")
    (inbox / "bad.zip").write_bytes(b"invalid zip")
    (inbox / "ignored.png").write_bytes(b"image")
    (inbox / "linked.md").symlink_to(inbox / "good.md")
    calls = []

    def importing(config, source, *, overwrite):
        assert overwrite is False
        calls.append(source.name)
        if source.name == "bad.zip":
            raise ValueError("bad")

    monkeypatch.setattr(skill_management, "import_indexed_skill", importing)
    assert import_skill_inbox(cfg) == (1, 1)
    assert sorted(calls) == ["bad.zip", "good.md"]
    assert (inbox / "imported" / "good.md").read_text() == "# Good"
    assert not (inbox / "good.md").exists()
    assert (inbox / "bad.zip").exists()
    calls.clear()
    assert import_skill_inbox(cfg) == (0, 1)
    assert calls == ["bad.zip"]


def test_skill_zip_limits_and_symlinks(tmp_path):
    cfg = FakeConfig(tmp_path)
    archive = tmp_path / "oversized.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for number in range(2001):
            zf.writestr(f"{number}.md", "x")
    with pytest.raises(ValueError, match="limits"):
        install_skill_package(cfg, archive)
    archive = tmp_path / "link.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        entry = zipfile.ZipInfo("link.md")
        entry.external_attr = 0o120777 << 16
        zf.writestr(entry, "outside")
    with pytest.raises(ValueError, match="symlink"):
        install_skill_package(cfg, archive)


def test_skill_writer_drains_accepted_operations_in_order(tmp_path, monkeypatch):
    from klaude_knowledge import skill_management

    reached = threading.Event()
    release = threading.Event()
    seen = []
    events = []

    def delete(cfg, name, identity):
        seen.append(name)
        if name == "first":
            reached.set()
            assert release.wait(2)

    monkeypatch.setattr(skill_management, "delete_installed_skill", delete)
    writer = SkillActionWriter(FakeConfig(tmp_path), lambda *event: events.append(event))
    assert writer.submit(SkillAction("delete", "first", "id"))
    assert reached.wait(2)
    assert writer.submit(SkillAction("delete", "second", "id"))
    writer.close()
    assert not writer.submit(SkillAction("import"))
    release.set()
    assert writer.close(wait=True)
    assert seen == ["first", "second"]
    assert len(events) == 2 and all(event[1][1] for event in events)


def test_shared_import_indexes_then_finalizes_without_executing_skill(tmp_path):
    from klaude_knowledge.skill_management import import_indexed_skill

    cfg = FakeConfig(tmp_path)
    source = tmp_path / "demo.zip"
    with zipfile.ZipFile(source, "w") as zf:
        zf.writestr("SKILL.md", "# Demo\nUse examples")
        zf.writestr("run.py", "raise RuntimeError('must never execute')")

    class FakeKnowledge:
        def replace_owner_snapshot_atomic(self, library, owner, documents):
            assert library == "shared"
            assert owner == "skill:demo"
            assert {doc.source for doc in documents} == {
                "skill://demo/SKILL.md",
                "skill://demo/run.py",
            }
            assert not (cfg.skills_dir / "demo" / "manifest.json").exists()
            return 2

    installed, count = import_indexed_skill(
        cfg, source, name="demo", library="shared", knowledge=FakeKnowledge()
    )
    assert count == 2
    assert json.loads(installed.manifest_path.read_text())["state"] == "active"
    with pytest.raises(FileExistsError):
        import_indexed_skill(cfg, source, name="demo", overwrite=False, knowledge=FakeKnowledge())


def test_remote_skill_uses_pinned_download_and_existing_index_lane(tmp_path, monkeypatch):
    from klaude_knowledge import skill_management

    cfg = FakeConfig(tmp_path)
    revision = "a" * 40
    record = SkillRecord(
        "skillsmp", "one", "demo", repository="org/repo",
        source_url="https://github.com/org/repo/tree/main/skills/demo",
        skill_path="skills/demo/SKILL.md", revision=revision,
    )
    monkeypatch.setattr(skill_management, "download_resolved_skill", lambda selected,
                        **_: {"SKILL.md": b"# Demo", "references/guide.md": b"Guide"}
                        if selected == record else pytest.fail("Wrong selection"))

    class Knowledge:
        def replace_owner_snapshot_atomic(self, library, owner, documents):
            assert library == "demo" and owner == "skill:demo"
            assert {doc.source for doc in documents} == {
                "skill://demo/SKILL.md", "skill://demo/references/guide.md",
            }
            return 2

    installed, count = import_remote_skill(cfg, record, knowledge=Knowledge())
    assert count == 2
    assert installed.manifest_path.exists()
    manifest = json.loads(installed.manifest_path.read_text())
    assert manifest["source"] == (
        f"https://github.com/org/repo/blob/{revision}/skills/demo/SKILL.md"
    )
    assert manifest["source_revision"] == revision
    assert (installed.current_dir / "references/guide.md").read_text() == "Guide"
    assert not list(cfg.skills_dir.glob(".remote-*"))
    with pytest.raises(FileExistsError):
        import_remote_skill(cfg, record, knowledge=Knowledge())


def test_remote_skill_update_requires_exact_installed_manifest(tmp_path, monkeypatch):
    from dataclasses import replace

    from klaude_knowledge import skill_management

    cfg = FakeConfig(tmp_path)
    old = SkillRecord(
        "skillsmp", "one", "demo", repository="org/repo",
        source_url="https://github.com/org/repo/blob/" + "a" * 40 + "/demo/SKILL.md",
        skill_path="demo/SKILL.md", revision="a" * 40,
    )
    new = replace(old, revision="b" * 40, source_url=(
        "https://github.com/org/repo/blob/" + "b" * 40 + "/demo/SKILL.md"
    ))
    monkeypatch.setattr(skill_management, "download_resolved_skill", lambda record, **_: {
        "SKILL.md": ("# " + record.revision).encode(),
    })

    class Knowledge:
        def replace_owner_snapshot_atomic(self, *_):
            return 1

    installed, _ = import_remote_skill(cfg, old, knowledge=Knowledge())
    identity = manifest_identity(installed.manifest_path.read_bytes())
    with pytest.raises(ValueError, match="Skill changed"):
        import_remote_skill(cfg, new, knowledge=Knowledge(), overwrite=True,
                            expected_identity="c" * 64)
    assert json.loads(installed.manifest_path.read_text())["source_revision"] == old.revision
    updated, _ = import_remote_skill(cfg, new, knowledge=Knowledge(), overwrite=True,
                                     expected_identity=identity)
    assert json.loads(updated.manifest_path.read_text())["source_revision"] == new.revision


def test_remote_install_is_an_ordered_explicit_skill_action(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from klaude_knowledge import skill_management

    record = SkillRecord("skillsmp", "one", "demo", repository="org/repo",
                         source_url="https://github.com/org/repo/tree/main/demo",
                         skill_path="demo/SKILL.md", revision="a" * 40)
    seen, events = [], []
    monkeypatch.setattr(skill_management, "import_remote_skill", lambda _cfg, selected: (
        seen.append(selected) or SimpleNamespace(name="demo"), 1
    ))
    writer = SkillActionWriter(FakeConfig(tmp_path), lambda *event: events.append(event))
    assert not writer.submit(SkillAction("install-remote", record=record, identity="wrong"))
    assert writer.submit(SkillAction("install-remote", record.name, record.identity, record))
    assert writer.close(wait=True)
    assert seen == [record]
    assert events[0][1][1:] == (True, "Installed demo")


def test_failed_indexing_never_publishes_active_manifest(tmp_path):
    from klaude_knowledge.skill_management import import_indexed_skill

    cfg = FakeConfig(tmp_path)
    source = tmp_path / "demo.md"
    source.write_text("# Demo")

    class FailingKnowledge:
        def replace_owner_snapshot_atomic(self, *_args):
            raise RuntimeError("embed unavailable")

    with pytest.raises(RuntimeError, match="embed unavailable"):
        import_indexed_skill(cfg, source, name="demo", knowledge=FailingKnowledge())
    assert not (cfg.skills_dir / "demo" / "manifest.json").exists()
    assert source.exists()


def test_preparing_inbox_does_not_initialize_index_or_import(tmp_path):
    from klaude_knowledge.skill_management import prepare_skill_inbox

    cfg = FakeConfig(tmp_path)
    assert prepare_skill_inbox(cfg) == tmp_path / "skills-inbox"
    assert (tmp_path / "skills-inbox").is_dir()
    assert not (tmp_path / "knowledge").exists()
    assert not list(cfg.skills_dir.glob("*/manifest.json"))


def test_completed_import_with_known_skips_is_not_unconfirmed(tmp_path, monkeypatch):
    from klaude_knowledge import skill_management

    events = []
    monkeypatch.setattr(skill_management, "import_skill_inbox", lambda cfg: (1, 1))
    writer = SkillActionWriter(FakeConfig(tmp_path), lambda *event: events.append(event))
    assert writer.submit(SkillAction("import"))
    assert writer.close(wait=True)
    assert events[0][1][1] is True
    assert "1 skipped/failed" in events[0][1][2]


def test_dropped_zip_import_uses_snapshot_and_archives_without_execution(tmp_path, monkeypatch):
    from klaude_core.skill_drop import file_signature
    from klaude_knowledge import skill_management

    cfg = FakeConfig(tmp_path)
    source = cfg.skills_dir / "demo.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("SKILL.md", "# Demo")
        archive.writestr("run.py", "raise RuntimeError('never execute')")
    original_import = skill_management.import_indexed_skill
    seen = []

    class Knowledge:
        def replace_owner_snapshot_atomic(self, library, owner, documents):
            seen.extend(doc.source for doc in documents)
            return len(documents)

    def importing(config, snapshot, *, overwrite):
        assert snapshot != source and snapshot.name == source.name
        return original_import(config, snapshot, overwrite=overwrite, knowledge=Knowledge())

    monkeypatch.setattr(skill_management, "import_indexed_skill", importing)
    skill_management.import_dropped_skill(cfg, source, file_signature(source.stat()))
    assert not source.exists()
    assert len(list((cfg.skills_dir / ".imports").iterdir())) == 1
    assert json.loads((cfg.skills_dir / "demo" / "manifest.json").read_text())["state"] == "active"
    assert set(seen) == {"skill://demo/SKILL.md", "skill://demo/run.py"}


def test_drop_import_rejects_stale_or_symlink_file(tmp_path):
    from klaude_core.skill_drop import file_signature
    from klaude_knowledge.skill_management import import_dropped_skill

    cfg = FakeConfig(tmp_path)
    source = cfg.skills_dir / "demo.md"
    source.write_text("old")
    signature = file_signature(source.stat())
    source.write_text("new content")
    with pytest.raises(ValueError, match="changed"):
        import_dropped_skill(cfg, source, signature)
    assert source.read_text() == "new content"
    source.unlink()
    source.symlink_to(tmp_path / "outside")
    with pytest.raises(OSError):
        import_dropped_skill(cfg, source, signature)


def test_watcher_only_detects_and_import_requires_explicit_action(tmp_path, monkeypatch):
    from klaude_knowledge import skill_management

    cfg = FakeConfig(tmp_path)
    source = cfg.skills_dir / "demo.md"
    source.write_text("new")
    detected = threading.Event()
    imported = threading.Event()
    calls = []
    events = []

    def emit(kind, payload):
        events.append((kind, payload))
        if kind == "skill_drop_inventory":
            detected.set()

    def importing(config):
        calls.append("import")
        imported.set()
        return 1, 0

    monkeypatch.setattr(skill_management, "import_skill_inbox", importing)
    writer = SkillActionWriter(cfg, emit)
    writer._detector.settle_seconds = 0
    writer.watch()
    assert detected.wait(3)
    assert events[0] == ("skill_drop_inventory", ("demo.md",))
    assert calls == []
    assert source.exists()
    assert writer.submit(SkillAction("import"))
    assert imported.wait(3)
    assert writer.close(wait=True)
    assert calls == ["import"]
    assert events[-1][0] == "skill_action_done"


@pytest.mark.parametrize("outcome,tone", [
    ("empty", "neutral"), ("success", "success"), ("partial", "warning"),
    ("duplicate", "warning"), ("unconfirmed", "warning"), ("network", "error"),
])
def test_skill_writer_reports_feedback_tone_from_operation(tmp_path, monkeypatch, outcome, tone):
    from klaude_core.skill_catalog import CatalogFailure, CatalogStatus
    from klaude_knowledge import skill_management

    def importing(_config):
        if outcome == "duplicate":
            raise FileExistsError("Already installed")
        if outcome == "unconfirmed":
            raise OSError("Write outcome unknown")
        if outcome == "network":
            raise CatalogFailure(CatalogStatus.NETWORK)
        return {"empty": (0, 0), "success": (1, 0), "partial": (1, 1)}[outcome]

    monkeypatch.setattr(skill_management, "import_skill_inbox", importing)
    done = threading.Event()
    events = []

    def emit(kind, payload):
        if kind == "skill_action_done":
            events.append(payload)
            done.set()

    writer = SkillActionWriter(FakeConfig(tmp_path), emit)
    action = SkillAction("import")
    assert writer.submit(action)
    assert done.wait(3)
    writer.close(wait=True)
    assert len(events) == 1
    assert events[0][0] == action and events[0][3] == tone
    assert events[0][1] is (outcome in {"empty", "success", "partial"})


def test_import_without_files_reports_no_new_skill_file(tmp_path, monkeypatch):
    from klaude_knowledge import skill_management

    cfg = FakeConfig(tmp_path)
    events = []
    monkeypatch.setattr(skill_management, "import_skill_inbox", lambda cfg: (0, 0))
    writer = SkillActionWriter(cfg, lambda *event: events.append(event))
    assert writer.submit(SkillAction("import"))
    assert writer.close(wait=True)
    assert events[0][1][2] == "No new skill file."
