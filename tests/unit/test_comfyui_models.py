"""Custom checkpoint admission, ownership, shared files and interrupted removal."""

import json
import math
import struct
import uuid
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from klaude_application import comfyui_install as install
from klaude_application import comfyui_models as app
from klaude_application import image_model_store, model_store
from klaude_application.operation_journal import OperationConflict, OperationJournal
from klaude_core import comfyui_managed as managed
from klaude_core.comfyui_bundle import ControlBundle, digest
from klaude_core.comfyui_models import architecture, key
from klaude_core.image_generation import read, save
from klaude_core.settings_store import atomic_write_private, read_settings


def checkpoint(path, family="sd-1.5", edit=None):
    shapes = {
        "model.diffusion_model.input_blocks.0.0.weight": [320, 4, 3, 3],
        "first_stage_model.encoder.conv_in.weight": [128, 3, 3, 3],
        "first_stage_model.decoder.conv_out.weight": [3, 128, 3, 3],
    }
    if family == "sd-1.5":
        shapes.update(
            {
                "model.diffusion_model.input_blocks.1.1.transformer_blocks.0.attn2.to_k.weight": [
                    320,
                    768,
                ],
                "cond_stage_model.transformer.text_model.embeddings.token_embedding.weight": [
                    49408,
                    768,
                ],
            }
        )
    else:
        shapes.update(
            {
                "model.diffusion_model.input_blocks.4.1.transformer_blocks.0.attn2.to_k.weight": [
                    640,
                    2048,
                ],
                "model.diffusion_model.label_emb.0.0.weight": [1280, 2816],
                (
                    "conditioner.embedders.0.transformer.text_model.embeddings."
                    "token_embedding.weight"
                ): [
                    49408,
                    768,
                ],
                "conditioner.embedders.1.model.token_embedding.weight": [49408, 1280],
            }
        )
    header, offset = {}, 0
    for name, shape in shapes.items():
        end = offset + math.prod(shape)
        header[name] = {"dtype": "U8", "shape": shape, "data_offsets": [offset, end]}
        offset = end
    if edit:
        edit(header)
    content = json.dumps(header).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(struct.pack("<Q", len(content)) + content)
        stream.truncate(8 + len(content) + offset)


@pytest.fixture
def context(tmp_path, monkeypatch):
    cfg = SimpleNamespace(data_dir=tmp_path / "data", config_dir=tmp_path / "config")
    cfg.data_dir.mkdir()
    directory = tmp_path / "weights"
    directory.mkdir()
    monkeypatch.setenv("KLAUDE_IMAGE_MODEL_DIR", str(directory))
    path = directory / "checkpoints/demo/model/custom.safetensors"
    checkpoint(path)
    info = directory.stat()
    fields = {
        "endpoint": "image:sdcpp",
        "model": "hf.co/demo/model:custom.safetensors",
        "root": str(directory),
        "root_device": info.st_dev,
        "root_inode": info.st_ino,
        "repo": "demo/model",
        "filename": "custom.safetensors",
        "revision": "a" * 40,
        "sha256": managed.file_hash(path),
        "size": path.stat().st_size,
        "base_url": "https://huggingface.co",
    }
    journal = OperationJournal(cfg.data_dir / "operations.db")
    rid = uuid.uuid4().hex
    receipt = journal.admit(
        request_id=rid,
        owner_id=app.OWNER,
        kind="model-image-download",
        resource=image_model_store.resource(fields),
        payload=fields,
    )
    journal.record_witness(
        rid,
        app.OWNER,
        receipt.fence,
        before=model_store.witness(fields, False),
        after=model_store.witness(fields, True),
    )
    journal.start(rid, app.OWNER, receipt.fence)
    journal.finish(rid, app.OWNER, receipt.fence, state="completed", outcome="ok")
    target = model_store.target_path(cfg, rid)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_private(target, json.dumps(fields))
    return cfg, journal, fields, path


def request(cfg, journal, draft):
    fields, resource, summary = install.prepare(cfg, draft)
    rid = uuid.uuid4().hex
    receipt = journal.admit(
        request_id=rid,
        owner_id=app.OWNER,
        kind=draft["operation"],
        resource=resource,
        payload=fields,
    )
    return {
        "operation": draft["operation"],
        "request_id": rid,
        "fence": receipt.fence,
        **fields,
    }, summary


def publish_model(cfg, recipe, *, source=None, name="Custom model"):
    target = managed.model_path(cfg, recipe)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"managed-copy")
    model = key(recipe)
    record = {
        "bundle_id": model,
        "recipe": asdict(recipe),
        "name": name,
        "source": source or {},
        "request_id": "prior",
        "definition": digest(managed.definition(recipe)),
        "model_signature": managed.signature(target),
    }
    location = managed.record_path(cfg, model)
    location.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_private(location, json.dumps(record))
    return model, record, target


@pytest.mark.parametrize("family", ["sd-1.5", "sdxl"])
def test_bounded_architecture_detection(tmp_path, family):
    path = tmp_path / "model.safetensors"
    checkpoint(path, family)
    assert architecture(path) == family


@pytest.mark.parametrize(
    "edit",
    [
        lambda h: h.pop("first_stage_model.encoder.conv_in.weight"),
        lambda h: h["model.diffusion_model.input_blocks.0.0.weight"].update(shape=[320, 9, 3, 3]),
        lambda h: h["first_stage_model.decoder.conv_out.weight"].update(data_offsets=[0, 1]),
        lambda h: h["first_stage_model.encoder.conv_in.weight"].update(dtype=[]),
    ],
)
def test_incomplete_or_malformed_checkpoint_rejected(tmp_path, edit):
    path = tmp_path / "model.safetensors"
    checkpoint(path, edit=edit)
    with pytest.raises(ValueError):
        architecture(path)


def test_import_review_uses_witnessed_source_without_loading(context):
    cfg, journal, fields, path = context
    spec, summary = request(cfg, journal, {"operation": "comfy-import", "model": fields["model"]})
    assert spec["recipe"]["architecture"] == "sd-1.5"
    assert spec["source_signature"] == managed.signature(path)
    assert "Does not load weights" in summary
    assert not managed.root(cfg).exists()
    assert not cfg.config_dir.exists()
    with pytest.raises(ValueError):
        app.prepare(cfg, {"operation": "comfy-import", "model": str(path)})


def test_changed_source_rejected_before_runtime_install(context, monkeypatch):
    cfg, journal, fields, path = context
    spec, _ = request(cfg, journal, {"operation": "comfy-import", "model": fields["model"]})
    path.touch()
    monkeypatch.setattr(managed, "install", lambda *a, **k: pytest.fail("Unexpected install"))
    assert app.run(cfg, spec, None) == {"rejected": True}


def test_import_publishes_exact_recipe_and_reuses_runtime(context, monkeypatch):
    cfg, journal, fields, path = context
    spec, _ = request(cfg, journal, {"operation": "comfy-import", "model": fields["model"]})
    calls = []
    monkeypatch.delenv("KLAUDE_IMAGE_MODEL_DIR")

    def materialize(cfg, rid, source, fetch, check, progress, publish, *, bundle, repair_runtime):
        assert not repair_runtime and source == str(path)
        calls.append(bundle)
        model, record, target = publish_model(cfg, bundle)
        publish(record)
        atomic_write_private(managed.record_path(cfg, model), json.dumps(record))

    monkeypatch.setattr(managed, "install", materialize)
    assert app.run(cfg, spec, None)["ok"]
    record = read_settings(managed.record_path(cfg, spec["model"]))
    assert record["recipe"] == spec["recipe"] and record["source"] == fields
    assert calls[0].sha256 == fields["sha256"]
    assert path.exists() and not cfg.config_dir.exists()


def test_remove_rejects_selected_default_and_preserves_shared_file(context, monkeypatch):
    cfg, journal, fields, original = context
    recipe = ControlBundle(id="checkpoint-" + "b" * 64, sha256="b" * 64)
    model, record, target = publish_model(cfg, recipe)
    monkeypatch.setattr(managed, "installed", lambda cfg, **kw: record)
    save(cfg, {"enabled": False, "endpoint": "managed", "provider": "comfyui", "model": model}, "")
    with pytest.raises(ValueError, match="another image default"):
        app.prepare(cfg, {"operation": "comfy-remove", "model": model})
    save(cfg, {"enabled": False, "endpoint": "", "model": ""}, read(cfg)["revision"])
    # A second exact bundle references the same controlled checkpoint.
    atomic_write_private(managed.record_path(cfg), json.dumps({"request_id": "shared"}))
    monkeypatch.setattr(managed, "bundle_for", lambda cfg, selected: recipe)
    monkeypatch.setattr(managed, "require_idle", lambda cfg: None)
    monkeypatch.setattr(managed, "stop", lambda cfg: None)
    spec, summary = request(cfg, journal, {"operation": "comfy-remove", "model": model})
    assert spec["shared"] and "will be retained" in summary
    assert app.run(cfg, spec, None)["ok"]
    assert target.exists() and original.exists()
    assert read_settings(managed.record_path(cfg, model))["removed_by"] == spec["request_id"]


def test_interrupted_remove_recovers_only_reviewed_managed_copy(context, monkeypatch):
    cfg, journal, _, original = context
    recipe = ControlBundle(id="checkpoint-" + "c" * 64, sha256="c" * 64)
    model, _, target = publish_model(cfg, recipe)
    monkeypatch.setattr(managed, "require_idle", lambda cfg: None)
    monkeypatch.setattr(managed, "stop", lambda cfg: None)
    spec, _ = request(cfg, journal, {"operation": "comfy-remove", "model": model})
    cleanup = app._cleanup
    monkeypatch.setattr(app, "_cleanup", lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        app.run(cfg, spec, None)
    assert target.exists() and managed.records(cfg) == []
    evidence = journal.evidence(spec["request_id"], app.OWNER)
    monkeypatch.setattr(app, "_cleanup", cleanup)
    with managed.install_lock(cfg):
        assert app.recover(cfg, spec["request_id"], evidence) == "completed"
    assert not target.exists() and original.exists()


def test_removal_recovery_refuses_changed_file(context, monkeypatch):
    cfg, journal, _, _ = context
    recipe = ControlBundle(id="checkpoint-" + "d" * 64, sha256="d" * 64)
    model, record, target = publish_model(cfg, recipe)
    fields, _, _ = app.prepare(cfg, {"operation": "comfy-remove", "model": model})
    atomic_write_private(
        managed.record_path(cfg, model), json.dumps({**record, "removed_by": "test"})
    )
    target.write_bytes(b"changed copy")
    with pytest.raises(OperationConflict, match="changed"):
        app.recover(cfg, "test", {"operation": "comfy-remove", **fields})


def test_remote_review_reads_only_bounded_pinned_header(context, monkeypatch):
    import httpx
    from klaude_web import huggingface

    cfg, journal, fields, path = context
    cfg.huggingface_base_url = "https://huggingface.co"
    monkeypatch.setattr(
        huggingface,
        "hub_gguf_files",
        lambda *a, **kw: {
            "revision": fields["revision"],
            "files": [
                {"filename": fields["filename"], "size": fields["size"], "sha256": fields["sha256"]}
            ],
        },
    )
    calls = []

    def respond(request):
        start, end = map(int, request.headers["range"].removeprefix("bytes=").split("-"))
        calls.append((start, end))
        with path.open("rb") as stream:
            stream.seek(start)
            data = stream.read(end - start + 1)
        return httpx.Response(
            206, content=data, headers={"content-range": f"bytes {start}-{end}/{fields['size']}"}
        )

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original(**kw, transport=httpx.MockTransport(respond))
    )
    spec, summary = request(
        cfg, journal, {"operation": "comfy-store-install", "model": fields["model"]}
    )
    assert spec["recipe"]["architecture"] == "sd-1.5" and spec["source_signature"] == []
    assert len(calls) == 2 and calls[0] == (0, 7) and sum(b - a + 1 for a, b in calls) < 10000
    assert "runtime" in summary and not managed.root(cfg).exists()


def test_remote_source_rejects_full_file_response(context, monkeypatch):
    import httpx
    from klaude_web import huggingface

    cfg, _, fields, _ = context
    cfg.huggingface_base_url = "https://huggingface.co"
    monkeypatch.setattr(
        huggingface,
        "hub_gguf_files",
        lambda *a, **kw: {
            "revision": fields["revision"],
            "files": [
                {"filename": fields["filename"], "size": fields["size"], "sha256": fields["sha256"]}
            ],
        },
    )
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(
            **kw,
            transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"not a range")),
        ),
    )
    with pytest.raises(ValueError, match="bounded checkpoint metadata"):
        app.prepare(cfg, {"operation": "comfy-store-install", "model": fields["model"]})
    assert not managed.root(cfg).exists()


def test_model_materialization_uses_existing_runtime_and_verifies_family(context, monkeypatch):
    import shutil

    cfg, _, fields, source = context
    recipe = ControlBundle(
        id="checkpoint-" + fields["sha256"], sha256=fields["sha256"], size=fields["size"]
    )
    base = managed.root(cfg)
    (base / "source").mkdir(parents=True)
    (base / "source/main.py").write_text("fixture")
    (base / "venv/bin").mkdir(parents=True)
    (base / "venv/bin/python").write_text("fixture")
    (base / "runtime.lock").write_bytes(managed.LOCK.read_bytes())
    atomic_write_private(
        base / "runtime.json", json.dumps({"definition": digest(managed.definition()["runtime"])})
    )
    monkeypatch.setattr(managed, "require_idle", lambda cfg: None)
    monkeypatch.setattr(managed, "_run", lambda *a: pytest.fail("Runtime was reinstalled"))
    monkeypatch.setattr(managed, "stop", lambda cfg: pytest.fail("Working engine was stopped"))
    monkeypatch.setattr(managed, "start", lambda *a: "http://127.0.0.1:8188")
    monkeypatch.setattr(
        managed,
        "probe",
        lambda url: {
            "schema_matches": True,
            "runtime_version_matches": True,
            "checkpoints": [recipe.installed_name],
        },
    )

    def fetch(directory, temporary, progress, check):
        shutil.copyfile(source, directory / temporary)

    record = managed.install(
        cfg, "test", "", fetch, lambda: None, lambda _: None, bundle=recipe, repair_runtime=False
    )
    assert managed.installed(cfg, model=key(recipe), full=True) == record
    assert not managed.record_path(cfg).exists()  # No unwanted starter-model install.
    assert source.exists()
