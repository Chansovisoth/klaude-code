"""Hugging Face Hub integration.

This is not a full MCP client. It gives klaude-code first-class Hub lookup
tools for models, datasets, and Spaces while keeping the integration optional.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

import httpx

REPO_TYPES = {
    "model": ("models", ""),
    "models": ("models", ""),
    "dataset": ("datasets", "datasets/"),
    "datasets": ("datasets", "datasets/"),
    "space": ("spaces", "spaces/"),
    "spaces": ("spaces", "spaces/"),
}


def _repo_type(value: str) -> tuple[str, str]:
    try:
        return REPO_TYPES[value.lower()]
    except KeyError:
        raise ValueError("repo_type must be one of: model, dataset, space") from None


def _headers(api_key: str) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _repo_url(base_url: str, repo_type: str, repo_id: str) -> str:
    _, prefix = _repo_type(repo_type)
    return f"{base_url.rstrip('/')}/{prefix}{quote(repo_id, safe='/')}"


def _compact_repo(base_url: str, item: dict[str, Any], repo_type: str) -> dict[str, Any]:
    repo_id = item.get("id") or item.get("modelId") or item.get("name", "")
    tags = item.get("tags") or []
    return {
        "id": repo_id,
        "type": repo_type.rstrip("s"),
        "url": _repo_url(base_url, repo_type, repo_id) if repo_id else "",
        "likes": item.get("likes", 0),
        "downloads": item.get("downloads", 0),
        "downloads_known": "downloads" in item,
        "last_modified": item.get("lastModified") or item.get("last_modified", ""),
        "tags": tags[:12],
        "summary": item.get("description") or item.get("pipeline_tag") or "",
        "pipeline_tag": item.get("pipeline_tag")
        if isinstance(item.get("pipeline_tag"), str)
        else "",
    }


def hub_repo_search(
    base_url: str,
    api_key: str,
    repo_type: str,
    query: str = "",
    limit: int = 10,
    sort: str = "downloads",
    *,
    filter_tag: str = "",
    cursor: str = "",
    with_cursor: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], str]:
    endpoint, _ = _repo_type(repo_type)
    params: dict[str, Any] = {"limit": max(1, min(limit, 50))}
    if query:
        params["search"] = query
    if sort:
        params["sort"] = sort
    if filter_tag:
        if filter_tag not in {"gguf", "text-to-image"} or endpoint != "models":
            raise ValueError("Unsupported model discovery filter")
        params["filter"] = filter_tag
        params["direction"] = -1
        params["expand"] = ["downloads", "lastModified", "pipeline_tag", "tags"]
        if cursor:
            if len(cursor) > 2048 or any(not c.isprintable() for c in cursor):
                raise ValueError("Invalid Hugging Face page cursor")
            params["cursor"] = cursor
        import json

        with httpx.Client(
            timeout=httpx.Timeout(5, connect=3), trust_env=False, follow_redirects=False
        ) as client:
            with client.stream(
                "GET",
                f"{base_url.rstrip('/')}/api/{endpoint}",
                headers=_headers(api_key),
                params=params,
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 1_000_000:
                        raise ValueError("Hugging Face discovery response exceeded its bound")
                data = json.loads(body)
                next_url = response.links.get("next", {}).get("url", "")
                next_cursor = parse_qs(urlsplit(next_url).query).get("cursor", [""])[0]
                if (
                    not isinstance(data, list)
                    or len(data) > 50
                    or any(not isinstance(item, dict) for item in data)
                ):
                    raise ValueError("Invalid Hugging Face model inventory")
                results = [_compact_repo(base_url, item, endpoint) for item in data]
                return (results, next_cursor) if with_cursor else results
    r = httpx.get(
        f"{base_url.rstrip('/')}/api/{endpoint}",
        headers=_headers(api_key),
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return [_compact_repo(base_url, item, endpoint) for item in r.json()]


def hub_repo_details(
    base_url: str,
    api_key: str,
    repo_type: str,
    repo_id: str,
) -> dict[str, Any]:
    endpoint, _ = _repo_type(repo_type)
    r = httpx.get(
        f"{base_url.rstrip('/')}/api/{endpoint}/{quote(repo_id, safe='/')}",
        headers=_headers(api_key),
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    data["url"] = _repo_url(base_url, endpoint, repo_id)
    data["type"] = endpoint.rstrip("s")
    return data


def hub_repo_readme(
    base_url: str,
    api_key: str,
    repo_type: str,
    repo_id: str,
) -> str:
    _, prefix = _repo_type(repo_type)
    revisions = _readme_revisions(base_url, api_key, repo_type, repo_id)
    errors = []
    for revision in revisions:
        url = (
            f"{base_url.rstrip('/')}/{prefix}{quote(repo_id, safe='/')}"
            f"/raw/{quote(revision, safe='')}/README.md"
        )
        try:
            r = httpx.get(
                url,
                headers=_headers(api_key),
                timeout=30,
                follow_redirects=True,
            )
            r.raise_for_status()
            text = r.text.strip()
            if text:
                return text
            errors.append(f"{revision}: empty README")
        except Exception as exc:
            errors.append(f"{revision}: {exc}")
    raise RuntimeError(f"Hugging Face README unavailable for {repo_id}: " + " | ".join(errors))


def _readme_revisions(
    base_url: str,
    api_key: str,
    repo_type: str,
    repo_id: str,
) -> list[str]:
    candidates: list[str] = []

    def add(value: str | None) -> None:
        if value and value not in candidates:
            candidates.append(value)

    try:
        details = hub_repo_details(base_url, api_key, repo_type, repo_id)
    except Exception:
        details = {}
    for key in ("default_branch", "defaultBranch", "sha", "lastCommit"):
        value = details.get(key)
        if isinstance(value, str):
            add(value)
    siblings = details.get("siblings") or []
    for sibling in siblings:
        if not isinstance(sibling, dict):
            continue
        name = sibling.get("rfilename") or sibling.get("path") or sibling.get("name")
        if str(name).lower() == "readme.md":
            add(sibling.get("revision") or sibling.get("branch") or sibling.get("sha"))
    add("main")
    add("master")
    return candidates


def hub_gguf_files(
    base_url: str, api_key: str, repo_id: str, *, image: bool = False,
) -> dict[str, Any]:
    """Bounded metadata for exact top-level GGUF files, never weight downloads."""
    import json
    import re

    part = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}"
    if not re.fullmatch(rf"{part}/{part}", repo_id):
        raise ValueError("Choose an exact Hugging Face repository")
    with httpx.Client(
        timeout=httpx.Timeout(5, connect=3), trust_env=False, follow_redirects=False
    ) as client:
        with client.stream(
            "GET",
            f"{base_url.rstrip('/')}/api/models/{repo_id}",
            params={"blobs": "true"},
            headers=_headers(api_key),
        ) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 2_000_000:
                    raise ValueError("Repository metadata exceeded its bound")
    value = json.loads(body)
    if not isinstance(value, dict) or value.get("id") != repo_id:
        raise ValueError("Repository identity differs from the selected model")
    siblings = value.get("siblings")
    if not isinstance(siblings, list) or len(siblings) > 1000:
        raise ValueError("Repository file inventory exceeds its bound")
    files = []
    for row in siblings:
        if not isinstance(row, dict):
            raise ValueError("Invalid repository file metadata")
        name = row.get("rfilename", "")
        if (
            not isinstance(name, str)
            or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:gguf|safetensors)" if image
                else r"[A-Za-z0-9][A-Za-z0-9_.-]*\.gguf", name, re.I,
            )
            or re.search(r"-\d+-of-\d+\.gguf$", name, re.I)
            or name.lower().startswith("mmproj")
            or len(f"hf.co/{repo_id}:{name}") > 200
        ):
            continue
        lfs = row.get("lfs")
        lfs = lfs if isinstance(lfs, dict) else {}
        size = row.get("size", lfs.get("size"))
        if image and (
            re.search(r"-\d+-of-\d+\.", name)
            or type(size) is not int or not 0 < size <= 64 * 1024**3
            or not re.fullmatch(r"[a-f0-9]{64}", str(lfs.get("sha256", "")))
        ):
            continue
        files.append({
            "filename": name, "size": size if type(size) is int and 0 <= size < 2**63 else None,
            **({"sha256": lfs["sha256"]} if image else {}),
        })
        if len(files) == 64:
            break
    card = value.get("cardData")
    card = card if isinstance(card, dict) else {}
    license_name = card.get("license")
    return {
        "id": repo_id,
        **({"revision": value.get("sha", "")} if image else {}),
        "files": files,
        "pipeline_tag": value.get("pipeline_tag")
        if isinstance(value.get("pipeline_tag"), str)
        else "",
        "license": license_name
        if isinstance(license_name, str) and len(license_name) < 100
        else None,
    }
