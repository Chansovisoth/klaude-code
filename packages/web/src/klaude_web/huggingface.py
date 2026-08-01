"""Hugging Face Hub integration.

This is not a full MCP client. It gives klaude-code first-class Hub lookup
tools for models, datasets, and Spaces while keeping the integration optional.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

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
        "last_modified": item.get("lastModified") or item.get("last_modified", ""),
        "tags": tags[:12],
        "summary": item.get("description") or item.get("pipeline_tag") or "",
    }


def hub_repo_search(
    base_url: str,
    api_key: str,
    repo_type: str,
    query: str = "",
    limit: int = 10,
    sort: str = "downloads",
) -> list[dict[str, Any]]:
    endpoint, _ = _repo_type(repo_type)
    params: dict[str, Any] = {"limit": max(1, min(limit, 50))}
    if query:
        params["search"] = query
    if sort:
        params["sort"] = sort
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
