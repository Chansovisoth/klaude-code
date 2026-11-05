"""Explicit dependency offers resolve fixed public metadata without installing."""

import pytest
from klaude_application import image_dependencies as deps

from .test_image_model_selection import image_browser as image_browser
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request

FLUX = {
    "id": "flux3-klein", "name": "FLUX.3 Image Klein",
    "slots": [
        {"id": "diffusion_model", "required": True, "categories": ["diffusion_models"]},
        {"id": "llm", "required": True, "categories": ["text_encoders"]},
        {"id": "vae", "required": False, "categories": ["vae"]},
        {"id": "tae", "required": False, "categories": ["vae", "vae_approx"]},
    ], "required_any": [["vae", "tae"]],
}


@pytest.fixture
def dependencies(image_browser, monkeypatch):
    host, service, auth, url, state = image_browser
    state["recipes"].append(FLUX)
    state["files"].append({"id": "diffusion_models/flux.gguf", "name": "Flux",
                           "category": "diffusion_models"})
    calls = []

    def metadata(base, key, repo, *, image):
        calls.append(repo)
        record = next(row for row in deps.FLUX3.values() if row[1] == repo)
        return {"revision": "a" * 40, "files": [
            {"filename": record[2], "size": 1234, "sha256": "b" * 64},
        ]}

    monkeypatch.setattr(deps, "hub_gguf_files", metadata)
    yield host, service, auth, url, state, calls


def check(dependencies, **changes):
    host, service, auth, url, state, calls = dependencies
    return _request(host, "POST", "/api/v1/settings/models/image-dependencies", body={
        "endpoint": url, "recipe": "flux3-klein",
        "models": {"diffusion_model": "diffusion_models/flux.gguf"}, **changes,
    }, **auth)


def test_prompt_offers_only_verified_missing_components_without_effects(dependencies):
    host, service, auth, url, state, calls = dependencies
    code, _, data = check(dependencies)
    assert code == 200
    assert {row["slot"] for row in data["components"]} == {"llm", "vae"}
    assert data["total_bytes"] == 2468
    assert all(row["draft"]["category"] in {"vae", "text_encoders"}
               for row in data["components"])
    assert not state["loads"]
    assert not service.operations()["items"]


def test_selected_tae_satisfies_vae_alternative_without_extra_download(dependencies):
    host, service, auth, url, state, calls = dependencies
    state["files"].append({"id": "vae_approx/tae.safetensors", "name": "TAE",
                           "category": "vae_approx"})
    code, _, data = check(dependencies, models={"diffusion_model": "diffusion_models/flux.gguf",
                                             "tae": "vae_approx/tae.safetensors"})
    assert code == 200
    assert [row["slot"] for row in data["components"]] == ["llm"]
    assert calls == [deps.FLUX3["llm"][1]]


def test_existing_download_is_offered_as_use_installed(dependencies):
    host, service, auth, url, state, calls = dependencies
    _, repo, filename, category = deps.FLUX3["llm"]
    file_id = f"{category}/{repo}/{filename}"
    state["files"].append({"id": file_id, "name": filename, "category": category})
    code, _, data = check(dependencies)
    assert code == 200
    assert next(row for row in data["components"] if row["slot"] == "llm")["available"] == file_id
    assert data["total_bytes"] == 1234


def test_unknown_recipe_does_not_guess_sources(dependencies):
    host, service, auth, url, state, calls = dependencies
    code, _, data = check(dependencies, recipe="sd", models={})
    assert code == 200 and data["components"] == []
    assert data["unresolved"] == ["model"]
    assert not calls


def test_dependency_check_requires_csrf_and_valid_component_selection(dependencies):
    host, service, auth, url, state, calls = dependencies
    code, _, _ = _request(host, "POST", "/api/v1/settings/models/image-dependencies", body={
        "endpoint": url, "recipe": "flux3-klein", "models": {},
    }, **{**auth, "csrf": "bad"})
    assert code == 403
    assert check(dependencies, models={"llm": "missing-file"})[0] == 400
    assert not calls
