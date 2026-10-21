"""Managed artifact boundaries, independent stores and real panel consumers."""

import hashlib
import io
import json
import os
import queue
import sqlite3
import struct

import pytest
from klaude_cli.background_worker import execute
from klaude_cli.library_commands import app
from klaude_cli.session_actions import LibraryArtifactChange, SessionActionWriter
from klaude_cli.settings_panel import PanelAction, PanelState, render_body
from klaude_core.library_artifacts import ArtifactStore, execute_artifact_change, image_header
from klaude_core.memory import Memory
from PIL import Image
from prompt_toolkit.utils import get_cwidth
from typer.testing import CliRunner

from .test_library_workspace import accept_latest, library_host


@pytest.fixture
def memory(tmp_path):
    item = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    item.log_turn("saved", "user", "Saved conversation")
    item.log_turn("recent", "user", "Recent conversation")
    yield item
    item.db.close()


@pytest.fixture
def artifact(tmp_path):
    source = tmp_path / "design.md"
    source.write_text("# Widget 設計\n\nOriginal architecture\n" + "Detail\n" * 200)
    store = ArtifactStore(tmp_path / "data" / "library")
    item = store.import_file(source, "document")
    return store, source, item


def act(host, kind, target=""):
    host._apply_panel_action(PanelAction("library-artifact-" + kind, target))


def png():
    # Actual tiny PNG, not just an image-header fixture.
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
    )


@pytest.mark.parametrize("mode,options,chunk", [
    ("RGB", {"lossless": False}, b"VP8 "),
    ("RGBA", {"lossless": True}, b"VP8L"),
    ("RGBA", {"lossless": False}, b"VP8X"),
])
def test_real_webp_dimensions_and_truncated_headers(mode, options, chunk):
    output = io.BytesIO()
    Image.new(mode, (719, 513), (12, 70, 130, 100) if mode == "RGBA" else "teal").save(
        output, "WEBP", **options,
    )
    data = output.getvalue()
    assert data[12:16] == chunk
    assert image_header(data[:65536]) == ("image/webp", 719, 513)
    for size in range(12, 25 if chunk == b"VP8L" else 30):
        assert image_header(data[:size]) == ("image/webp", None, None)
    malformed = bytearray(data)
    if chunk == b"VP8 ":
        malformed[23] ^= 1
    elif chunk == b"VP8L":
        malformed[24] |= 0x20  # Unsupported lossless bitstream version.
    else:
        return
    assert image_header(bytes(malformed)) == ("image/webp", None, None)


@pytest.mark.parametrize("kind", ["media", "document"])
def test_existing_image_dimensions_are_recovered_read_only(tmp_path, monkeypatch, kind):
    output = io.BytesIO()
    Image.new("RGB", (37, 23), "teal").save(output, "WEBP", lossless=True)
    store = ArtifactStore(tmp_path / "library")
    imported = store.import_bytes(output.getvalue(), kind, "existing.webp")
    assert (imported["width"], imported["height"]) == (37, 23)
    with store.database(write=True) as db:
        db.execute("UPDATE artifacts SET width=NULL,height=NULL WHERE id=?", (imported["id"],))
        before = tuple(db.execute("SELECT * FROM artifacts WHERE id=?",
                                  (imported["id"],)).fetchone())
    monkeypatch.setattr(Image, "open", lambda *_a, **_kw: pytest.fail("Browse decoded pixels"))
    for item in (store.get(imported["id"]), store.listing("all")["items"][0]):
        assert (item["width"], item["height"]) == (37, 23)
        assert item["revision"] == imported["revision"]
        assert item["sha256"] == hashlib.sha256(output.getvalue()).hexdigest()
        assert "_image_header" not in item
        assert not any(isinstance(value, bytes) for value in item.values())
    with store.database() as db:
        after = tuple(db.execute("SELECT * FROM artifacts WHERE id=?",
                                 (imported["id"],)).fetchone())
    assert after == before


def test_import_keeps_private_exact_copy_and_preview_is_bounded(artifact):
    store, source, item = artifact
    original = source.read_bytes()
    assert item["sha256"] == hashlib.sha256(original).hexdigest()
    assert item["kind"] == "document" and item["id"].startswith("document:")
    assert item["origin"] == str(source) and not item["model"] and not item["session"]
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert store.root.stat().st_mode & 0o777 == 0o700
    source.write_text("Changed outside Klaude")
    destination = source.parent / "copied.md"
    store.export(item["id"], destination)
    assert destination.read_bytes() == original and source.read_text() == "Changed outside Klaude"
    preview = store.preview(item["id"])
    assert preview["truncated"] and len(preview["lines"]) == 100
    assert "設計" in preview["lines"][0]


def test_missing_store_browse_never_initializes(tmp_path):
    root = tmp_path / "missing" / "library"
    assert ArtifactStore(root).listing("all") == {"items": [], "more": False}
    assert not root.exists()


def test_preview_reports_single_line_truncation(artifact):
    store, source, _ = artifact
    source.write_text("x" * 900)
    item = store.import_file(source, "document")
    preview = store.preview(item["id"])
    assert preview["truncated"] and len(preview["lines"][0]) == 500


def test_source_preview_preserves_whitespace_and_legacy_terminal_contract(artifact):
    store, _, _ = artifact
    source = "\tdef greeting():\r\n    return '設計'  \r\n\r\n" + "x" * 900 + "\n"
    item = store.import_bytes(source.encode(), "document", "code.py")
    legacy = store.preview(item["id"])
    preview = store.preview(item["id"], include_source=True)
    assert "source_text" not in legacy
    assert preview["lines"] == legacy["lines"]
    assert legacy["truncated"]  # The terminal still clips individual lines.
    assert preview["source_text"] == source
    assert not preview["source_truncated"] and not preview["source_sanitized"]


def test_empty_source_preview_is_readable(artifact):
    store, _, _ = artifact
    item = store.import_bytes(b"", "document", "empty.txt")
    preview = store.preview(item["id"], include_source=True)
    assert preview["source_text"] == "" and preview["lines"] == []
    assert not preview["source_truncated"] and not preview["source_sanitized"]


@pytest.mark.parametrize("source,expected", [
    (b"x" * 16383 + "設計".encode(), "x" * 16383),
    (b"line\r\n" * 101, "line\r\n" * 100),
    (b"x" * 20000, "x" * 16384),
])
def test_source_preview_bounds_do_not_add_unicode_replacement(artifact, source, expected):
    store, _, _ = artifact
    item = store.import_bytes(source, "document", "bounded.txt")
    preview = store.preview(item["id"], include_source=True)
    assert preview["source_text"] == expected
    assert preview["source_truncated"] and not preview["source_sanitized"]


def test_source_preview_reports_sanitization_without_changing_saved_bytes(artifact):
    store, _, _ = artifact
    original = b"print('hello')\n" * 10 + b"\tinvalid:\xff control:\x1b\n"
    item = store.import_bytes(original, "document", "unsafe.py")
    preview = store.preview(item["id"], include_source=True)
    assert preview["source_sanitized"] and not preview["source_truncated"]
    assert preview["source_text"].endswith("\tinvalid:� control: \n")
    assert store.get(item["id"])["sha256"] == hashlib.sha256(original).hexdigest()
    binary = store.import_bytes(b"binary\0data", "document", "unknown.bin")
    assert "source_text" not in store.preview(binary["id"], include_source=True)


def test_tags_search_sort_types_and_archive_do_not_change_bytes(artifact, tmp_path):
    store, source, item = artifact
    image = tmp_path / "screenshot.png"
    image.write_bytes(png())
    picture = store.import_file(image, "media")
    assert (picture["mime"], picture["width"], picture["height"]) == ("image/png", 1, 1)
    tagged = store.change(item["id"], 1, "tags", "architecture, 設計, architecture")
    assert tagged["tags"] == ["architecture", "設計"] and tagged["revision"] == 2
    assert store.listing("document", query="設計")["items"][0]["id"] == item["id"]
    assert store.listing("media", query=str(image))["items"][0]["id"] == picture["id"]
    assert store.listing("all", format="image/")["items"][0]["id"] == picture["id"]
    assert [row["id"] for row in store.listing("all", sort="oldest")["items"]] == [
        item["id"],
        picture["id"],
    ]
    assert store.preview(picture["id"])["fallback"] and not store.preview(picture["id"])["lines"]
    archived = store.change(item["id"], 2, "archive")
    assert not store.listing("document")["items"]
    assert store.listing("all", archived=True)["items"][0]["id"] == item["id"]
    restored = store.change(item["id"], archived["revision"], "restore")
    assert restored["sha256"] == item["sha256"] and restored["tags"] == tagged["tags"]
    store.export(item["id"], tmp_path / "restored.md")
    assert (tmp_path / "restored.md").read_bytes() == source.read_bytes()


def test_stale_mutations_delete_confirmation_and_original_independence(artifact):
    store, source, item = artifact
    archived = store.change(item["id"], 1, "archive")
    other = ArtifactStore(store.root)
    restored = other.change(item["id"], archived["revision"], "restore")
    with pytest.raises(ValueError, match="changed elsewhere"):
        store.change(item["id"], archived["revision"], "delete")
    assert store.get(item["id"])["revision"] == restored["revision"]
    store.change(item["id"], restored["revision"], "delete")
    assert source.exists() and not store.listing("all")["items"]
    assert not store.listing("all", archived=True)["items"]
    with pytest.raises(ValueError, match="no longer exists"):
        store.get(item["id"])


@pytest.mark.parametrize("bad", [",".join(map(str, range(21))), "x" * 41, "escape\x1b", "x" * 1001])
def test_invalid_tags_do_not_mutate_or_advance_revision(artifact, bad):
    store, _, item = artifact
    with pytest.raises(ValueError):
        store.change(item["id"], 1, "tags", bad)
    assert store.get(item["id"])["revision"] == 1


def test_export_protects_existing_paths_jail_symlinks_and_stale_revisions(artifact, tmp_path):
    store, source, item = artifact
    with pytest.raises(FileExistsError):
        store.export(item["id"], source)
    assert source.read_text().startswith("# Widget")
    link = tmp_path / "link.md"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="symbolic"):
        store.export(item["id"], link)
    with pytest.raises(ValueError, match="inside"):
        execute_artifact_change(
            store.root, "export", target=item["id"], value="../outside.md", workspace=tmp_path
        )
    with pytest.raises(ValueError, match="changed elsewhere"):
        store.export(item["id"], tmp_path / "new.md", revision=99)
    with pytest.raises(ValueError, match="printable"):
        execute_artifact_change(
            store.root,
            "export",
            target=item["id"],
            revision=1,
            value="name\x1b.md",
            workspace=tmp_path,
        )
    assert not (tmp_path / "new.md").exists()


def test_export_checksum_failure_removes_partial_copy(artifact, tmp_path):
    store, _, item = artifact
    with store.database(write=True) as db:
        db.execute("UPDATE artifacts SET content=? WHERE id=?", (b"corrupted", item["id"]))
    output = tmp_path / "partial.md"
    with pytest.raises(ValueError, match="checksum"):
        store.export(item["id"], output)
    assert not output.exists()


def test_symlink_fifo_and_oversize_imports_never_create_store(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    path = tmp_path / "source"
    path.write_text("content")
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="symbolic"):
        store.import_file(link, "document")
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular"):
        store.import_file(fifo, "document")
    with path.open("wb") as stream:
        stream.truncate(32 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="32 MiB"):
        store.import_file(path, "document")
    assert not store.root.exists()


def test_private_store_symlink_and_hardlink_are_rejected(artifact, tmp_path):
    store, _, _ = artifact
    link = tmp_path / "linked"
    link.symlink_to(store.root)
    with pytest.raises(ValueError, match="symbolic"):
        ArtifactStore(link).listing("all")
    os.link(store.path, tmp_path / "hardlink.db")
    with pytest.raises(ValueError, match="regular private"):
        store.listing("all")


def test_terminal_controls_are_removed_from_preview_and_provenance(tmp_path):
    source = tmp_path / "name\x1b.md"
    source.write_text("safe\x1b[31m\nline\x00\x9btitle\n")
    store = ArtifactStore(tmp_path / "library")
    item = store.import_file(source, "document")
    # Binary fallback for NUL; metadata never contains terminal controls.
    assert "\x1b" not in json.dumps(store.get(item["id"]), ensure_ascii=False)
    assert store.preview(item["id"])["fallback"]
    source.write_text("safe\x1b[31m\nline\n")
    item = store.import_file(source, "document")
    assert "\x1b" not in "".join(store.preview(item["id"])["lines"])


def test_media_rejection_dimensions_and_research_storage(tmp_path):
    store = ArtifactStore(tmp_path / "library")
    source = tmp_path / "pretend.png"
    source.write_text("not an image")
    with pytest.raises(ValueError, match="Media accepts"):
        store.import_file(source, "media")
    assert not store.root.exists()
    assert image_header(b"GIF89a" + struct.pack("<HH", 10, 20)) == ("image/gif", 10, 20)
    assert image_header(b"\xff\xd8\xff\xc0\x00\x07\x08\x00\x14\x00\x0a") == ("image/jpeg", 10, 20)
    report = store.store_report(
        "report.md", "# Evidence\nVerified report", job="job-1", session="session-1"
    )
    assert report["kind"] == "research" and report["job"] == "job-1" and not report["model"]
    assert store.preview(report["id"])["lines"][0] == "# Evidence"


def test_headless_open_is_truthful_and_does_not_materialize_copy(artifact, monkeypatch):
    store, _, item = artifact
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr("klaude_core.library_artifacts.sys.platform", "linux")
    with pytest.raises(ValueError, match="No desktop"):
        store.open_external(item["id"], 1)
    assert not (store.root / "opened").exists()


def test_desktop_open_uses_fixed_opener_safe_extension_and_bounded_copies(artifact, monkeypatch):
    from types import SimpleNamespace

    store, _, item = artifact
    monkeypatch.setenv("DISPLAY", ":test")
    monkeypatch.setattr(
        "klaude_core.library_artifacts.shutil.which", lambda _name: "/usr/bin/xdg-open"
    )
    calls = []
    monkeypatch.setattr(
        "klaude_core.library_artifacts.subprocess.run",
        lambda command, **kwargs: calls.append((command, kwargs)) or SimpleNamespace(returncode=0),
    )
    path = store.open_external(item["id"], 1)
    assert path.suffix == ".txt" and path.stat().st_mode & 0o777 == 0o600
    assert calls[0][0] == ["/usr/bin/xdg-open", str(path)]
    assert "shell" not in calls[0][1] and calls[0][1]["timeout"] == 5
    for index in range(7):
        (path.parent / f"retained-{index}").write_text("already opened")
    with pytest.raises(ValueError, match="cache is full"):
        store.open_external(item["id"], 1)
    assert len(calls) == 1


def test_failed_desktop_open_removes_materialized_copy(artifact, monkeypatch):
    from types import SimpleNamespace

    store, _, item = artifact
    monkeypatch.setenv("DISPLAY", ":test")
    monkeypatch.setattr(
        "klaude_core.library_artifacts.shutil.which", lambda _name: "/usr/bin/xdg-open"
    )
    monkeypatch.setattr(
        "klaude_core.library_artifacts.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    with pytest.raises(ValueError, match="opener failed"):
        store.open_external(item["id"], 1)
    assert not list((store.root / "opened").iterdir())


def test_failed_commit_rolls_back_content_and_metadata_together(artifact, monkeypatch):
    import contextlib

    store, source, item = artifact
    original = store.database

    @contextlib.contextmanager
    def failed_database(*, write=False):
        with original(write=write) as db:
            yield db
            if write:
                raise sqlite3.OperationalError("simulated storage failure")

    monkeypatch.setattr(store, "database", failed_database)
    with pytest.raises(sqlite3.OperationalError):
        store.import_file(source, "document")
    with pytest.raises(sqlite3.OperationalError):
        store.change(item["id"], 1, "archive")
    assert store.listing("document")["items"][0]["revision"] == 1
    assert len(store.listing("document")["items"]) == 1 and source.exists()


def test_metadata_paging_remains_bounded_and_disjoint(artifact):
    store, _, item = artifact
    with store.database(write=True) as db:
        for index in range(105):
            db.execute(
                "INSERT INTO artifacts SELECT 'document:' || ?, kind, name, filename, mime, "
                "size, sha256, created + ?, origin, session, job, model, width, height, tags, "
                "archived, revision, content FROM artifacts WHERE id=?",
                (f"{index:032x}", index + 1, item["id"]),
            )
    page = store.listing("document")
    following = store.listing("document", offset=100)
    assert len(page["items"]) == 100 and page["more"]
    assert len(following["items"]) == 6 and not following["more"]
    assert not {item["id"] for item in page["items"]} & {item["id"] for item in following["items"]}


def test_action_lane_applies_ordered_independent_artifact_changes(memory, tmp_path):
    events = queue.Queue()
    source = tmp_path / "document.md"
    source.write_text("Explicitly stored")
    root = str(memory.sessions_db.parent / "library")
    writer = SessionActionWriter(memory, lambda *event: events.put(event))
    change = LibraryArtifactChange(
        "caller", "import", root, "import", value=str(source), workspace=str(tmp_path)
    )
    assert writer.submit(change)
    assert writer.close(wait=True)
    kind, (returned, item, error) = events.get_nowait()
    assert kind == "library_artifact_saved" and returned == change and not error
    assert item["session"] == "caller" and memory.session_counts()["sessions"] == 2
    assert not (memory.sessions_db.parent / "knowledge.lance").exists()


def test_worker_bounded_reads_and_ui_no_content_in_chat(memory, tmp_path):
    host, calls = library_host(memory)
    store = ArtifactStore(memory.sessions_db.parent / "library")
    source = tmp_path / "design.md"
    source.write_text("private document text")
    item = store.import_file(source, "document")
    messages = list(host.agent.messages)
    host._library.open("documents")
    accept_latest(host, calls)
    act(host, "record", item["id"])
    assert host._panel.page.id.startswith("library:artifact-detail")
    assert not host._panel_feedback
    act(host, "preview")
    accept_latest(host, calls)
    assert "private document text" in str(host._panel.page)
    assert render_body(host._panel, 120).selected_line < 4
    assert host.agent.messages == messages
    act(host, "back", "artifact-detail")
    act(host, "tags")
    assert host._settings_input_is_single_line()
    host._answer_settings_input(None)
    assert host._library.view == "artifact-detail" and not host.input.text


def test_artifact_ui_search_back_focus_and_confirmation(memory, tmp_path):
    store = ArtifactStore(memory.sessions_db.parent / "library")
    source = tmp_path / "Widget architecture.md"
    source.write_text("Architecture")
    item = store.import_file(source, "document")
    host, calls = library_host(memory)
    host._library.open("documents")
    accept_latest(host, calls)
    host._panel.filter("Widget")
    act(host, "record", item["id"])
    act(host, "back", "documents")
    assert host._panel.picker.query == "widget"
    assert host._panel.picker.selected_id == "artifact:" + item["id"]
    host._panel.filter("Search metadata")
    act(host, "search")
    host._answer_settings_input("Widget")
    accept_latest(host, calls)
    assert host._panel.picker.query == ""
    assert any(row.id == "artifact:" + item["id"] for row in host._panel.picker.visible)
    item = store.change(item["id"], 1, "archive")
    act(host, "archive-list")
    accept_latest(host, calls)
    act(host, "record", item["id"])
    act(host, "confirm")
    assert host._panel.picker.selected_id == "back"
    host._cancel_choice()
    assert host._library.view == "artifact-detail"


@pytest.mark.parametrize("width", [40, 70, 120])
def test_artifact_controls_above_tables_and_width_bounded(memory, tmp_path, width):
    host, calls = library_host(memory)
    source = tmp_path / ("Unicode 設計 " + "long-name-" * 12 + ".md")
    source.write_text("Long title")
    ArtifactStore(memory.sessions_db.parent / "library").import_file(source, "document")
    host._library.open("documents")
    accept_latest(host, calls)
    rows = list(host._panel.page.rows)
    assert next(i for i, row in enumerate(rows) if row.id == "filter") < next(
        i for i, row in enumerate(rows) if row.id == "columns"
    )
    body = render_body(PanelState(host._panel.page), width)
    assert all(get_cwidth("".join(text for _, text in line)) <= width for line in body.lines)
    assert not host._panel_feedback


def test_artifact_ack_preserves_later_navigation_and_failed_feedback(memory):
    host, _ = library_host(memory)
    controller = host._library.artifacts
    change = LibraryArtifactChange(
        host.session_id,
        "one",
        str(memory.sessions_db.parent / "library"),
        "tags",
        target="document:x",
    )
    controller.changes["one"] = change
    host._library.open("research")
    controller.saved(change, None, "Artifact change unconfirmed; reload before retrying")
    assert host._library.view == "research"
    assert "unconfirmed" in str(host._panel_feedback)
    assert not controller.changes


def test_cli_real_commands_exit_codes_no_overwrite_and_confirmed_delete(
    artifact, tmp_path, monkeypatch
):
    store, source, item = artifact
    monkeypatch.setattr("klaude_cli.library_commands.store", lambda: store)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app, ["list", "--type", "document"]).exit_code == 0
    assert runner.invoke(app, ["info", item["id"]]).exit_code == 0
    exported = runner.invoke(app, ["export", item["id"], "exported.md"])
    assert exported.exit_code == 0, exported.output
    assert (tmp_path / "exported.md").read_bytes() == source.read_bytes()
    assert runner.invoke(app, ["export", item["id"], "exported.md"]).exit_code == 1
    assert runner.invoke(app, ["tags", item["id"], "qa, docs"]).exit_code == 0
    assert runner.invoke(app, ["delete", item["id"]]).exit_code == 1
    assert runner.invoke(app, ["archive", item["id"]]).exit_code == 0
    assert runner.invoke(app, ["delete", item["id"]], input="n\n").exit_code == 0
    assert store.get(item["id"])["archived"]
    assert runner.invoke(app, ["delete", item["id"]], input="y\n").exit_code == 0
    assert not store.listing("all", archived=True)["items"] and source.exists()


def test_artifact_subcommands_in_canonical_registry():
    from klaude_cli.main import CLI_COMMANDS

    registered = {"library " + command.name for command in app.registered_commands}
    described = {
        spec.usage.split(" ", 2)[0] + " " + spec.usage.split(" ", 2)[1]
        for spec in CLI_COMMANDS
        if spec.usage.startswith("library ")
    }
    assert registered == described


def test_worker_unsupported_operation_never_creates_storage(tmp_path):
    with pytest.raises(ValueError, match="Unknown artifact"):
        execute(
            {
                "kind": "library",
                "operation": "artifact-write",
                "database": str(tmp_path / "sessions.db"),
            }
        )
    assert not (tmp_path / "library").exists()
