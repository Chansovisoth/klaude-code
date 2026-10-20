"""Private chat attachments use bounded parsers and the shared fenced worker."""

import asyncio
import base64
import io
import json
import sqlite3
import threading
import time
import zipfile
from types import SimpleNamespace

import pytest
from klaude_application.chat_attachments import ChatAttachmentInput, prepare_attachment
from klaude_application.library_artifacts import ArtifactService
from klaude_application.library_management import LibraryManagement
from klaude_core import config as config_module
from klaude_core.config import Config
from klaude_tools.toolkit import Workspace
from klaude_webhost.host import LocalWebHost
from pypdf import PdfWriter

from .test_vision import vision_lab as vision_lab
from .test_webhost import _app, _request


def test_documents_decode_with_bounds_and_reject_binary_files():
    file = prepare_attachment("notes.md", b"# Private facts\nThe answer is 47.")
    assert "47" in file.text and not file.image
    assert "Private facts" not in repr(file)
    assert prepare_attachment("long.txt", b"x" * 40000).truncated
    with pytest.raises(ValueError):
        prepare_attachment("program.exe", b"MZ\x00binary")
    with pytest.raises(ValueError):
        prepare_attachment("../outside.md", b"text")
    with pytest.raises(ValueError):
        prepare_attachment("empty.txt", b"")
    with pytest.raises(ValueError):
        ChatAttachmentInput((file,) * 5)
    with pytest.raises(ValueError):
        ChatAttachmentInput((prepare_attachment("long.txt", b"x" * 40000),) * 3)


def test_docx_and_pdf_use_actual_extraction():
    document = io.BytesIO()
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="urn:word">'
                         '<w:p><w:r><w:t>Document secret 123</w:t></w:r></w:p></w:document>')
    file = prepare_attachment("report.docx", document.getvalue())
    assert file.text == "Document secret 123"
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    from pypdf.generic import DictionaryObject, NameObject, StreamObject

    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): font,
    })})
    stream = StreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 200 Td (PDF secret 456) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    assert "PDF secret 456" in prepare_attachment("report.pdf", output.getvalue()).text
    renamed = prepare_attachment("renamed.txt", output.getvalue())
    assert renamed.public()["mime"] == "application/pdf"


def test_private_input_reaches_model_without_public_text_leakage(tmp_path):
    app = _app(tmp_path)
    observed = []

    class Runtime:
        def chat(self, _model, messages, **_kwargs):
            observed.extend(messages)
            return {"role": "assistant", "content": "Document read."}

        def close(self):
            pass

    app.agent.runtime = app.agent.ollama = Runtime()
    attachment = ChatAttachmentInput((prepare_attachment("notes.md", b"private-canary-47"),))

    async def exercise():
        turn = app.submit("Summarize this", request_id="attachment-turn", attachments=attachment)
        assert (await turn.result()).state == "completed"
        assert "private-canary-47" in json.dumps(observed)
        assert "notes.md" in app.snapshot()["messages"][0]["content"]
        assert "private-canary-47" not in json.dumps(app.snapshot())
        epoch = app.snapshot()["cursor"].split(":")[0]
        events = app.replay(f"{epoch}:0")
        assert events and "private-canary-47" not in json.dumps(events)
        saved = app.memory.load_session(app.session_id)[0]
        assert "private-canary-47" in saved["model_content"]["content"]
        from klaude_core.chat_images import ChatImages

        context = ChatImages(SimpleNamespace(data_dir=tmp_path / "data"), app.agent)
        context.restore_attempt([saved])
        assert context.resolve_retry("retry") == "retry"
        assert app.submit("Summarize this", request_id="attachment-turn",
                          attachments=attachment) is turn
        changed = ChatAttachmentInput((prepare_attachment("notes.md", b"different bytes"),))
        with pytest.raises(ValueError, match="different input"):
            app.submit("Summarize this", request_id="attachment-turn", attachments=changed)
        await app.close()

    asyncio.run(exercise())


def test_library_file_capture_rechecks_revision_archive_and_checksum(tmp_path):
    service = ArtifactService(tmp_path / "library")
    item = service.store.import_bytes(b"Exact content", "document", "notes.txt")
    name, content = service.attachment(item["id"], item["revision"])
    assert name == "notes.txt" and content == b"Exact content"
    with pytest.raises(ValueError, match="changed"):
        service.attachment(item["id"], item["revision"] + 1)
    service.store.change(item["id"], item["revision"], "archive")
    with pytest.raises(ValueError):
        service.attachment(item["id"], item["revision"])


def test_image_attachment_delivers_pixels_through_shared_fenced_worker(vision_lab):
    from klaude_application import HeadlessApplication
    from klaude_core.memory import Memory

    from .test_chat_images import agent_for
    from .test_library_artifacts import png

    cfg, _, _, _, calls, *_ = vision_lab
    agent = agent_for(vision_lab)
    agent.tool_config = cfg
    memory = Memory(cfg.data_dir / "memory.md", cfg.data_dir / "sessions.db")
    app = HeadlessApplication(agent, memory, allow_approvals=False)
    attachment = ChatAttachmentInput((prepare_attachment("colors.png", png(), preview=True),))

    async def exercise():
        turn = app.submit("Describe the colors", attachments=attachment)
        result = await turn.result()
        assert result.state == "completed", turn.failure
        sent = next(data for path, data in calls if path == "/api/chat")
        assert base64.b64decode(sent["messages"][-1]["images"][0]) == png()
        assert any(path == "/api/show" for path, _ in calls)
        assert "image_inputs" not in json.dumps(app.snapshot())
        assert base64.b64encode(png()).decode() not in json.dumps(app.snapshot())
        assert memory.load_session(app.session_id)[0]["model_content"]["image_inputs"]
        message = app.snapshot()["messages"][0]
        row_id = int(message["id"].split(":")[1])
        assert message["attachments"] == [attachment.files[0].public()]
        # Thumbnail reads and public projections must work with private input unreadable.
        def deny_private(_action, table, column, *_args):
            return sqlite3.SQLITE_DENY if (table, column) == ("turns", "model_content") else (
                sqlite3.SQLITE_OK
            )

        memory.db.set_authorizer(deny_private)
        try:
            assert app.snapshot()["messages"][0] == message
            assert app.sessions.public_message(app.session_id, row_id).attachments
            preview = app.sessions.attachment_preview(app.session_id, row_id, 0)
            assert preview == attachment.files[0].thumbnail
            assert "attachment_previews" not in json.dumps(app.snapshot())
        finally:
            memory.db.set_authorizer(None)
        memory.fork_session(app.session_id, "image-branch")
        branch = app.turns.snapshot("image-branch")["messages"][0]
        branch_id = int(branch["id"].split(":")[1])
        assert branch["attachments"] == message["attachments"]
        assert app.sessions.attachment_preview("image-branch", branch_id, 0) == preview
        memory.delete_session("image-branch")
        with pytest.raises(ValueError, match="unavailable"):
            app.sessions.attachment_preview("image-branch", branch_id, 0)
        await app.close()
        from klaude_application.coordination import DurableTurns
        from klaude_application.sessions import SessionDirectory

        reopened = Memory(cfg.data_dir / "memory.md", cfg.data_dir / "sessions.db")
        try:
            assert DurableTurns(reopened).snapshot(app.session_id)["messages"][0] == message
            directory = SessionDirectory(reopened)
            assert directory.attachment_preview(app.session_id, row_id, 0) == preview
        finally:
            reopened.db.close()

    try:
        asyncio.run(exercise())
    finally:
        agent.runtime.close()


def test_browser_attachment_sources_are_owner_tab_and_session_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    app = _app(tmp_path)
    app.agent.workdir = tmp_path
    app.agent.workspace = Workspace(tmp_path)
    library = LibraryManagement(Config(), tmp_path)
    host = LocalWebHost(app, library=library, staging_dir=tmp_path / "staging")
    serving = threading.Thread(target=host.serve_forever, daemon=True)
    serving.start()
    try:
        _, headers, login = _request(host, "POST", "/api/v1/auth/exchange",
                                     body={"code": host.bootstrap_url.partition("#")[2]},
                                     origin=host.origin)
        auth = {"cookie": headers["Set-Cookie"].split(";", 1)[0], "csrf": login["csrf"],
                "origin": host.origin}
        client = _request(host, "POST", "/api/v1/clients", body={}, **auth)[2]["client_id"]
        second = _request(host, "POST", "/api/v1/clients", body={}, **auth)[2]["client_id"]
        auth["client_id"] = client
        item = library.artifacts.import_bytes(b"Library secret 123", "document", "private.md")
        body = {"artifact_id": item["id"], "revision": item["revision"]}
        assert _request(host, "POST", "/api/v1/chat/attachments", body=body)[0] == 403
        assert _request(host, "POST", "/api/v1/chat/attachments", body=body,
                        **{**auth, "csrf": "wrong"})[0] == 403
        status, _, selected = _request(host, "POST", "/api/v1/chat/attachments", body=body, **auth)
        assert status == 201 and selected["name"] == "private.md"
        turn = {"request_id": "browser-attachment", "text": "Summarize",
                "attachments": [selected["id"]]}
        assert _request(host, "POST", "/api/v1/turns", body=turn,
                        **{**auth, "client_id": second})[0] == 400
        with pytest.raises(ValueError):
            host.attachments.capture(next(iter(host._sessions)), client, "another",
                                     [selected["id"]])
        assert _request(host, "POST", "/api/v1/turns", body=turn, **auth)[0] == 202
        deadline = time.monotonic() + 3
        while app.active_turn_count() and time.monotonic() < deadline:
            time.sleep(.01)
        snapshot = _request(host, "GET", "/api/v1/session", **auth)[2]
        assert "Library secret 123" not in json.dumps(snapshot)
        assert snapshot["messages"][0]["attachments"][0]["name"] == "private.md"
        assert _request(host, "POST", "/api/v1/turns", body=turn, **auth)[0] == 202
        owner = next(iter(host._sessions))
        staged = host.transfers.upload(owner, io.BytesIO(b"Device bytes"), 12, "upload.txt")
        selected = _request(host, "POST", "/api/v1/chat/attachments",
                            body={"upload_id": staged.id}, **auth)[2]
        assert selected["name"] == "upload.txt"
        with pytest.raises(FileNotFoundError):
            host.transfers.open_download(owner, staged.id)
        rejected = host.transfers.upload(owner, io.BytesIO(b"\x00bad"), 4, "bad.exe")
        assert _request(host, "POST", "/api/v1/chat/attachments",
                        body={"upload_id": rejected.id}, **auth)[0] == 400
        with pytest.raises(FileNotFoundError):
            host.transfers.open_download(owner, rejected.id)
        assert _request(host, "POST", "/api/v1/chat/attachments/discard",
                        body={"id": selected["id"]}, **auth)[0] == 200
        with pytest.raises(ValueError):
            host.attachments.capture(owner, client, app.session_id, [selected["id"]])
        # Image previews use authenticated same-origin requests and exact owner/tab/chat scope.
        from http.client import HTTPConnection
        from urllib.parse import urlencode

        from .test_library_artifacts import png

        image = library.artifacts.import_bytes(png(), "media", "colors.png")
        selected = _request(host, "POST", "/api/v1/chat/attachments",
                            body={"artifact_id": image["id"], "revision": image["revision"]},
                            **auth)[2]
        assert selected["image"] and selected["preview"] and selected["mime"] == "image/png"

        def preview_request(**overrides):
            query = {"session": app.session_id, "selection": selected["id"], "client": client}
            query.update(overrides)
            conn = HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
            conn.request("GET", "/api/v1/chat/attachments/preview?" + urlencode(query),
                         headers={"Cookie": auth["cookie"]})
            response = conn.getresponse()
            result = response.status, dict(response.getheaders()), response.read()
            conn.close()
            return result

        status, headers, pixels = preview_request()
        assert status == 200 and headers["Content-Type"] == "image/png"
        assert headers["Cache-Control"] == "no-store"
        assert pixels.startswith(b"\x89PNG") and len(pixels) <= 65536
        assert preview_request(client=second)[0] == 404
        assert preview_request(session="other")[0] == 404
        assert preview_request(selection="unknown")[0] == 404
        url = "/api/v1/chat/attachments/preview?" + urlencode({
            "session": app.session_id, "selection": selected["id"], "client": client,
        })
        assert _request(host, "GET", url)[0] == 401
        _request(host, "POST", "/api/v1/chat/attachments/discard",
                 body={"id": selected["id"]}, **auth)
        assert preview_request()[0] == 404
    finally:
        host.stop()
        serving.join(3)


def test_image_thumbnail_is_small_oriented_and_has_no_source_metadata():
    from PIL import Image, PngImagePlugin

    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private", "image-metadata-canary")
    Image.new("RGB", (600, 300), "#7655aa").save(output, format="PNG", pnginfo=metadata)
    source = output.getvalue()
    attachment = prepare_attachment("picture.png", source, preview=True)
    assert attachment.data == source
    assert b"image-metadata-canary" not in attachment.thumbnail
    assert 0 < len(attachment.thumbnail) <= 65536
    with Image.open(io.BytesIO(attachment.thumbnail)) as image:
        assert image.size == (128, 64)
        assert not image.info
    assert attachment.public()["preview"] is True
