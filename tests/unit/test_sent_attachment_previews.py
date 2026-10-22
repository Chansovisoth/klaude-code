"""Saved attachment originals are private, bounded and exact-chat scoped."""

import base64
import http.client
import io
import json
import threading
import zipfile
from urllib.parse import urlencode

import pytest
from klaude_application.chat_attachments import ChatAttachmentInput, prepare_attachment
from klaude_application.coordination import DurableTurns
from klaude_application.library_management import LibraryManagement
from klaude_application.sessions import SessionDirectory
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_core.memory import Memory
from klaude_core.session_runtime import capture
from klaude_tools import Workspace
from klaude_webhost.host import LocalWebHost
from PIL import Image, PngImagePlugin

from .test_webhost import _app, _request


@pytest.fixture
def sent_attachment_host(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    cfg = Config(models={"coder": "fixture"})
    app = _app(cfg.data_dir)
    app.agent.workdir, app.agent.workspace, app.agent.tool_config = (
        tmp_path,
        Workspace(tmp_path),
        cfg,
    )
    library = LibraryManagement(cfg, tmp_path)
    text = b"# Attached source\r\n\tprivate-file-canary\r\n<script>throw 'unsafe'</script>"
    saved = library.artifacts.import_bytes(text, "document", "notes.md")
    image = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "private-image-metadata-canary")
    Image.new("RGB", (600, 300), "purple").save(image, format="PNG", pnginfo=metadata)
    document = io.BytesIO()
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="urn:word">'
            "<w:p><w:r><w:t>Private DOCX preview</w:t></w:r></w:p></w:document>",
        )
    files = (
        prepare_attachment("notes.md", text, artifact_id=saved["id"]),
        prepare_attachment("picture.png", image.getvalue(), preview=True),
        prepare_attachment("report.docx", document.getvalue()),
    )
    attachments = ChatAttachmentInput(files)
    admission = app.turns.admit(
        request_id="sent-originals",
        session_id=app.session_id,
        turn_id="sent-originals-turn",
        worker_id=app.client_id,
        text=attachments.public_text("Inspect the files"),
        scope="standard",
        runtime=capture(app.agent),
        input_key=attachments.identity,
        attachments=attachments,
    )
    app.turns.finish(
        request_id=admission.request_id,
        session_id=app.session_id,
        turn_id=admission.turn_id,
        worker_id=app.client_id,
        fence=admission.fence,
        state="completed",
        assistant="Ready.",
    )
    host = LocalWebHost(app, library=library)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    _, headers, _ = _request(
        host,
        "POST",
        "/api/v1/auth/exchange",
        body={"code": host.bootstrap_url.partition("#")[2]},
        origin=host.origin,
    )
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    message = app.snapshot()["messages"][0]["id"]

    def request(index=0, view="info", *, authenticated=True, **overrides):
        query = {"session": app.session_id, "message": message, "file": str(index), "view": view}
        query.update(overrides)
        conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=10)
        conn.request(
            "GET",
            "/api/v1/chat/attachments/content?" + urlencode(query),
            headers={"Cookie": cookie} if authenticated else {},
        )
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    try:
        yield host, files, message, request, cfg
    finally:
        host.stop()
        thread.join(3)


def test_sent_originals_render_download_and_stay_private(sent_attachment_host):
    host, files, message, request, _ = sent_attachment_host
    app = host.application
    inventory = host.library.listing()
    public = json.dumps(app.snapshot())
    assert "private-file-canary" not in public and "attachment_contents" not in public
    assert base64.b64encode(files[1].data).decode() not in public
    row_id = int(message[7:])
    for index, file in enumerate(files):
        descriptor, original = app.sessions.attachment_content(app.session_id, row_id, index)
        assert original == file.data and descriptor["name"] == file.name
        status, headers, original = request(index, "download")
        assert status == 200 and original == file.data
        assert headers["Content-Type"] == "application/octet-stream"
        assert headers["Content-Disposition"].startswith("attachment;")
        assert headers["Cache-Control"] == "no-store"
    status, headers, body = request()
    assert status == 200 and json.loads(body)["source_text"] == files[0].text
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    status, _, body = request(2)
    assert status == 200 and json.loads(body)["extracted"]
    assert json.loads(body)["source_text"] == "Private DOCX preview"
    status, _, body = request(1, "image")
    assert status == 200 and b"private-image-metadata-canary" not in body
    with Image.open(io.BytesIO(body)) as decoded:
        assert decoded.size == (600, 300) and not decoded.info
    assert host.library.listing() == inventory
    # The saved original remains available independently of the Library source.
    with host.library.artifacts.database(write=True) as db:
        db.execute("DELETE FROM artifacts WHERE id=?", (files[0].artifact_id,))
    assert request(0, "download")[2] == files[0].data


def test_sent_originals_scope_legacy_corruption_and_fork(sent_attachment_host):
    host, files, message, request, cfg = sent_attachment_host
    app, row_id = host.application, int(message[7:])
    assert request(authenticated=False)[0] == 401
    for overrides in (
        {"session": "other"},
        {"message": "stored:9223372036854775808"},
        {"message": "stored:1;drop table turns"},
        {"file": "4"},
        {"file": "-1"},
        {"view": "html"},
    ):
        assert request(**overrides)[0] == 404
    # Private model input is never needed to preview user attachments.
    import sqlite3

    def deny_private(_action, table, column, *_args):
        return (
            sqlite3.SQLITE_DENY
            if (table, column) == ("turns", "model_content")
            else (sqlite3.SQLITE_OK)
        )

    app.memory.db.set_authorizer(deny_private)
    try:
        assert request()[0] == request(1, "image")[0] == 200
    finally:
        app.memory.db.set_authorizer(None)
    app.memory.fork_session(app.session_id, "attachment-copy")
    copied = app.turns.snapshot("attachment-copy")["messages"][0]
    copied_id = int(copied["id"][7:])
    assert app.sessions.attachment_content("attachment-copy", copied_id, 0)[1] == files[0].data
    reopened = Memory(cfg.data_dir / "memory.md", cfg.data_dir / "sessions.db")
    try:
        assert (
            SessionDirectory(reopened).attachment_content(app.session_id, row_id, 0)[1]
            == files[0].data
        )
        assert "attachment_contents" not in json.dumps(
            DurableTurns(reopened).snapshot(app.session_id)
        )
    finally:
        reopened.db.close()
    app.memory.delete_session("attachment-copy")
    with pytest.raises(ValueError):
        app.sessions.attachment_content("attachment-copy", copied_id, 0)
    with app.memory._db_lock, app.memory.db:
        raw = app.memory.db.execute(
            "SELECT attachment_contents FROM turns WHERE rowid=?", (row_id,)
        ).fetchone()[0]
        broken = json.loads(raw)
        broken[0]["sha256"] = "0" * 64
        app.memory.db.execute(
            "UPDATE turns SET attachment_contents=? WHERE rowid=?", (json.dumps(broken), row_id)
        )
    assert request()[0] == 404
    with app.memory._db_lock, app.memory.db:
        app.memory.db.execute("UPDATE turns SET attachment_contents=NULL WHERE rowid=?", (row_id,))
    # Older Library attachments can still use their immutable saved original.
    assert request()[0] == 200
    assert json.loads(request(1)[2])["thumbnail_only"]
    assert request(1, "download")[0] == 404
    assert request(1, "image")[0] == 200
    assert request(2)[0] == 404


@pytest.mark.parametrize("revocation", ["logout", "deleted-message"])
def test_attachment_pixels_are_not_published_after_revocation(
    sent_attachment_host, monkeypatch, revocation,
):
    from klaude_webhost import host as host_module

    host, _, message, request, _ = sent_attachment_host
    original = host_module.prepare_image

    def revoke(*args, **kwargs):
        result = original(*args, **kwargs)
        if revocation == "logout":
            with host._lock:
                host._sessions.clear()
        else:
            with host.application.memory._db_lock, host.application.memory.db:
                host.application.memory.db.execute(
                    "DELETE FROM turns WHERE rowid=?", (int(message[7:]),),
                )
        return result

    monkeypatch.setattr(host_module, "prepare_image", revoke)
    status, headers, body = request(1, "image")
    assert status == 404 and headers["Content-Type"].startswith("application/json")
    assert not body.startswith(b"\x89PNG")
