"""ComfyUI preflight stays read-only and never promotes metadata to readiness."""

import copy
import json
from types import SimpleNamespace

import httpx
import pytest
from klaude_core import comfyui_probe as api
from klaude_core.comfyui_bundle import CONTROL, sd15_workflow

# API-shaped declarations transcribed from v0.43.0 nodes.py; independent of the
# production node contract map so accidental production changes are detected.
SOURCE_INPUTS = {
    "CheckpointLoaderSimple": {"ckpt_name": [[CONTROL.filename]]},
    "EmptyLatentImage": {
        "width": ["INT", {"min": 16, "max": 16384, "step": 8}],
        "height": ["INT", {"min": 16, "max": 16384, "step": 8}],
        "batch_size": ["INT", {"min": 1, "max": 4096}],
    },
    "CLIPTextEncode": {"text": ["STRING", {"multiline": True}], "clip": ["CLIP"]},
    "VAEDecode": {"samples": ["LATENT"], "vae": ["VAE"]},
    "SaveImage": {"images": ["IMAGE"], "filename_prefix": ["STRING"]},
    "KSampler": {
        "model": ["MODEL"],
        "seed": ["INT", {"min": 0, "max": 2**64 - 1}],
        "steps": ["INT", {"min": 1, "max": 10000}],
        "cfg": ["FLOAT", {"min": 0, "max": 100}],
        "sampler_name": [["euler", "euler_ancestral"]],
        "scheduler": [["normal", "simple"]],
        "positive": ["CONDITIONING"],
        "negative": ["CONDITIONING"],
        "latent_image": ["LATENT"],
        "denoise": ["FLOAT", {"min": 0, "max": 1}],
    },
}
SOURCE_OUTPUTS = {
    "CheckpointLoaderSimple": ["MODEL", "CLIP", "VAE"],
    "EmptyLatentImage": ["LATENT"],
    "CLIPTextEncode": ["CONDITIONING"],
    "VAEDecode": ["IMAGE"],
    "SaveImage": ["IMAGE"],
    "KSampler": ["LATENT"],
}


@pytest.fixture
def server(monkeypatch):
    packets = {
        "/system_stats": {
            "system": {
                "os": "linux",
                "ram_total": 16 * 2**30,
                "ram_free": 8 * 2**30,
                "comfyui_version": "0.43.0",
                "python_version": "3.12.12",
                "pytorch_version": "2.9.0+cu126",
                "argv": ["--private=not-for-output"],
            },
            "devices": [
                {
                    "name": "Fixture GPU",
                    "type": "cuda",
                    "vram_total": 4 * 2**30,
                    "vram_free": 3 * 2**30,
                }
            ],
        },
        "/models/checkpoints": [CONTROL.filename],
    }
    for name, fields in SOURCE_INPUTS.items():
        packets["/object_info/" + name] = {
            name: {
                "input": {"required": copy.deepcopy(fields)},
                "output": SOURCE_OUTPUTS[name],
                "output_node": name == "SaveImage",
                "python_module": "nodes",
            }
        }
    calls = []

    def respond(request):
        calls.append(request)
        assert request.method == "GET", "Preflight must never install, queue, cancel or load"
        assert not request.content
        assert "authorization" not in request.headers and "cookie" not in request.headers
        assert request.url.path.startswith("/gateway/")
        value = packets[request.url.path.removeprefix("/gateway")]
        if isinstance(value, httpx.Response):
            return value
        return httpx.Response(200, json=value)

    original = httpx.Client

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
        return original(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(api.httpx, "Client", client)
    return packets, calls


def test_probe_fixed_gets_private_metadata_and_no_false_readiness(server):
    packets, calls = server
    result = api.probe("http://fixture/gateway/")
    assert len(calls) == 8
    assert result["schema_matches"] and result["runtime_version_matches"]
    assert result["system"]["ram_total"] == 16 * 2**30
    assert result["devices"][0]["vram_total"] == 4 * 2**30
    assert "argv" not in result["system"] and "not-for-output" not in json.dumps(result)
    assert not result["checkpoint_name_visible"]
    assert not result["installed_bundle_verified"] and not result["generation_verified"]
    assert not result["bundle"]["install_available"]
    before = result["metadata_revision"]
    packets["/system_stats"]["devices"][0]["vram_free"] = 1
    assert api.probe("http://fixture/gateway")["metadata_revision"] == before
    packets["/models/checkpoints"] = [CONTROL.installed_name]
    observed = api.probe("http://fixture/gateway")
    assert observed["checkpoint_name_visible"] and not observed["installed_bundle_verified"]
    assert observed["metadata_revision"] != before


def test_unknown_version_and_missing_node_are_explicit(server):
    packets, _ = server
    packets["/system_stats"]["system"]["comfyui_version"] = "0.99.0"
    packets["/object_info/KSampler"] = {}
    result = api.probe("http://fixture/gateway")
    assert not result["runtime_version_matches"] and not result["schema_matches"]
    assert result["problems"] == ["Missing built-in node: KSampler"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda node: node.update(python_module="unreviewed.custom_node"),
        lambda node: node.update(output=["IMAGE"]),
        lambda node: node["input"]["required"].update(remote_code=["STRING"]),
        lambda node: node["input"]["required"].update(steps=["INT", {"min": 1, "max": 2}]),
        lambda node: node["input"]["required"].update(sampler_name=[["unsupported"]]),
    ],
)
def test_changed_node_contract_cannot_pass(server, mutation):
    packets, _ = server
    mutation(packets["/object_info/KSampler"]["KSampler"])
    result = api.probe("http://fixture/gateway")
    assert not result["schema_matches"] and result["problems"]


@pytest.mark.parametrize(
    "names",
    [
        ["../secret"],
        ["/absolute/path"],
        ["C:\\weights\\model"],
        ["a\\..\\secret"],
        ["a", "a"],
        ["model\nsecret"],
        [123],
        ["file"] * 501,
    ],
)
def test_invalid_checkpoint_inventory_rejected(server, names):
    packets, _ = server
    packets["/models/checkpoints"] = names
    with pytest.raises(ValueError):
        api.probe("http://fixture/gateway")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"location": "http://other-host/private"}),
        httpx.Response(401, text="private server detail"),
        httpx.Response(200, content=b'{"system":{},"system":{}}'),
        httpx.Response(200, content=b'{"system":NaN}'),
        httpx.Response(200, content=b"{"),
        httpx.Response(200, json={"system": []}),
    ],
)
def test_bad_response_no_followup_or_private_error(server, response):
    packets, calls = server
    packets["/system_stats"] = response
    with pytest.raises(ValueError) as error:
        api.probe("http://fixture/gateway")
    assert "private server detail" not in str(error.value)
    assert len(calls) == 1


def test_response_byte_limit_and_total_budget(server, monkeypatch):
    packets, calls = server
    packets["/system_stats"] = httpx.Response(200, content=b" " * 200)
    monkeypatch.setattr(api, "BYTE_LIMIT", 100)
    with pytest.raises(ValueError, match="byte limit"):
        api.probe("http://fixture/gateway")
    assert len(calls) == 1
    monkeypatch.setattr(api, "BYTE_LIMIT", 1000)
    monkeypatch.setattr(api, "TOTAL_LIMIT", 100)
    with pytest.raises(ValueError, match="byte limit"):
        api.probe("http://fixture/gateway")


def test_deadline_stops_next_request(server, monkeypatch):
    _, calls = server
    monkeypatch.setattr(api, "DEADLINE", 0)
    with pytest.raises(ValueError, match="deadline"):
        api.probe("http://fixture/gateway")
    assert not calls


def test_slow_stream_obeys_overall_deadline(server, monkeypatch):
    packets, calls = server
    clock = [0.0]

    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"{"
            clock[0] = 21.0
            yield b'"system":'
            pytest.fail("Probe continued reading after its deadline")

    monkeypatch.setattr(api, "time", SimpleNamespace(monotonic=lambda: clock[0], time=lambda: 1))
    packets["/system_stats"] = httpx.Response(200, stream=SlowStream())
    with pytest.raises(ValueError, match="deadline"):
        api.probe("http://fixture/gateway")
    assert len(calls) == 1


def test_compressed_response_is_not_decompressed(server):
    packets, calls = server
    packets["/system_stats"] = httpx.Response(
        200, content=b"", headers={"content-encoding": "gzip"}
    )
    with pytest.raises(ValueError, match="compressed"):
        api.probe("http://fixture/gateway")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/file",
        "http://user:secret@fixture",
        "http://fixture/?token=secret",
        "http://fixture/#secret",
        "http://fixture/\nprivate",
        "http://fixture/%0asecret",
    ],
)
def test_invalid_endpoint_rejected_before_contact(server, url):
    _, calls = server
    with pytest.raises(ValueError):
        api.probe(url)
    assert not calls


def test_fixed_workflow_has_exact_control_bundle_and_one_output():
    prompt = 'A cat; $(do-not-run) {"class_type":"arbitrary"}'
    graph = sd15_workflow("a" * 32, prompt, negative_prompt="blur", seed=42)
    assert graph["4"]["inputs"] == {"ckpt_name": CONTROL.installed_name}
    assert graph["6"]["inputs"]["text"] == prompt
    assert graph["7"]["inputs"]["text"] == "blur"
    assert graph["3"]["inputs"]["seed"] == 42
    assert graph["3"]["inputs"]["model"] == ["4", 0]
    assert graph["8"]["inputs"]["vae"] == ["4", 2]
    assert graph["9"]["inputs"]["images"] == ["8", 0]
    assert graph["5"]["inputs"]["batch_size"] == 1
    assert sum(node["class_type"] == "SaveImage" for node in graph.values()) == 1
    graph["4"]["inputs"]["ckpt_name"] = "different.safetensors"
    assert sd15_workflow("a" * 32, "cat")["4"]["inputs"]["ckpt_name"] == CONTROL.installed_name


@pytest.mark.parametrize(
    "values",
    [
        {"width": True},
        {"height": 100000},
        {"width": 300},
        {"seed": -1},
        {"seed": 2**32},
        {"steps": 0},
        {"steps": True},
        {"negative_prompt": "\x00"},
    ],
)
def test_graph_rejects_unreviewed_control_values(values):
    with pytest.raises(ValueError):
        sd15_workflow("a" * 32, "cat", **values)


def test_application_worker_probe_is_read_only_and_fixed(server, tmp_path):
    from klaude_application.image_generation import ImageGenerationCommand

    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    command = ImageGenerationCommand.for_client(
        cfg, "comfy_probe", endpoint="http://fixture/gateway"
    )
    result = ImageGenerationCommand.from_worker(command.worker_request()).execute()
    assert result["probe"]["schema_matches"]
    assert not list(tmp_path.iterdir())  # No settings, download receipts or model weights.
    for values in (
        {},
        {"endpoint": 1},
        {"endpoint": "http://fixture", "spec": {}},
        {"endpoint": "http://fixture", "provider": "comfyui"},
    ):
        with pytest.raises(ValueError, match="Invalid image generation"):
            ImageGenerationCommand.for_client(cfg, "comfy_probe", **values)


def test_application_probe_sanitizes_network_failure(server, tmp_path):
    from klaude_application.image_generation import ImageGenerationCommand

    packets, calls = server
    packets["/system_stats"] = httpx.Response(500, text="private traceback")
    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    result = ImageGenerationCommand.for_client(
        cfg, "comfy_probe", endpoint="http://fixture/gateway"
    ).execute()
    assert result == {"status": "error", "message": "ComfyUI metadata returned HTTP 500"}
    assert len(calls) == 1
