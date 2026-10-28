"""Bounded Store discovery over existing MCP and Skills catalog adapters.

Only metadata is fetched while browsing. Exact private item records, never browser
URLs or registry payloads, select the existing reviewed installation effects.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime

from klaude_core.mcp_catalog import (
    MCPCatalogClient,
    MCPCatalogServer,
    github_repository_identity,
    github_repository_stars,
    install_plans,
)
from klaude_core.settings_store import atomic_write_private
from klaude_core.skill_catalog import (
    STATUS_TEXT,
    CatalogStatus,
    SearchRequest,
    SkillRecord,
    clean_text,
    resolve_source,
    search,
)

from .model_store import read_record

DEFAULT_QUERY = {"mcps": "search", "skills": "coding"}
TTL = 3600


def _updated(value):
    if not isinstance(value, str) or not value or len(value) > 80:
        return ""
    try:
        date = datetime.fromisoformat(value.replace(" UTC", "+00:00").replace("Z", "+00:00"))
        if date.tzinfo is None or not 2000 <= date.year <= 2100:
            return ""
        return date.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError):
        return ""


class IntegrationStore:
    def __init__(self, cfg, *, transport=None):
        self.cfg = cfg
        self.transport = transport
        self.root = cfg.data_dir / "integration-store"
        self._lock = threading.RLock()
        self._stars_lock = threading.RLock()

    def _save(self, identity, value):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_private(self.root / f"{identity}.json", json.dumps(value))
        files = list(self.root.glob("*.json"))
        for old in sorted(files, key=lambda p: p.stat().st_mtime)[:-128]:
            if not old.is_symlink():
                old.unlink(missing_ok=True)

    def _item(self, kind, payload):
        source = payload["name"] if kind == "mcps" else payload["provider"] + payload["item_id"]
        identity = hashlib.sha256((kind + ":" + source).encode()).hexdigest()
        previous = read_record(self.root / f"{identity}.json")
        # Retain a verified source when a metadata refresh returns the same item.
        if (
            kind == "skills"
            and previous.get("payload", {}).get("source_url") == payload["source_url"]
        ):
            old = previous.get("resolved")
        else:
            old = None
        self._save(
            identity,
            {
                "kind": kind,
                "payload": payload,
                "checked_at": time.time(),
                **({"resolved": old} if old else {}),
            },
        )
        return identity

    def _read(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise ValueError("Choose an exact Store item")
        data = read_record(self.root / f"{identity}.json")
        if (
            not data
            or data.get("kind") not in DEFAULT_QUERY
            or not isinstance(data.get("payload"), dict)
            or not 0 <= time.time() - data.get("checked_at", 0) <= 7 * 86400
        ):
            raise ValueError("Store details expired; search again")
        return data

    @staticmethod
    def _remote(server):
        return next(
            (
                plan
                for plan in install_plans(server)
                if plan.transport == "http" and not plan.inputs and not plan.header_templates
            ),
            None,
        )

    def _public(self, identity, value):
        payload, kind = value["payload"], value["kind"]
        if kind == "mcps":
            server = MCPCatalogServer(**payload)
            plan = self._remote(server)
            return {
                "id": identity,
                "kind": kind,
                "name": server.title,
                "publisher": server.name.rsplit("/", 1)[0],
                "description": server.description,
                "version": server.version,
                "source": "Official MCP Registry",
                "source_url": server.repository_url or server.website_url,
                "github_repository": github_repository_identity(server.repository_url) or "",
                "updated_at": _updated(server.updated_at),
                "can_install": plan is not None,
                "install_label": "Add server",
                "notice": (
                    "Adds this server disabled. Enable it in Integrations to review its tools."
                    if plan
                    else "Use terminal setup for this server's package, credentials or transport."
                ),
                "endpoint": plan.url if plan else "",
            }
        record = SkillRecord.from_payload(value.get("resolved") or payload)
        return {
            "id": identity,
            "kind": kind,
            "name": record.name,
            "publisher": record.repository or record.provider,
            "description": record.description,
            "source": record.provider,
            "source_url": record.source_url,
            "github_repository": record.repository,
            "updated_at": _updated(record.catalog_updated),
            "can_install": bool(record.canonical_identity),
            "can_resolve": bool(
                record.source_url and "/tree/" in record.source_url or "/blob/" in record.source_url
            ),
            "install_label": "Install skill",
            "revision": record.revision,
            "skill_path": record.skill_path,
            "license": record.license,
            "notice": (
                "Downloads the pinned folder and indexes text with your embedding model. "
                "No scripts run."
                if record.canonical_identity
                else "Verify the original SKILL.md before installing. "
                "Repository listings need an exact source URL."
            ),
            "metric": asdict(record.popularity) if record.popularity else None,
        }

    def catalog(self, kind, query="", *, provider="skillsmp", page=1, refresh=False, sort="stars"):
        if (
            kind not in DEFAULT_QUERY
            or not isinstance(query, str)
            or len(query) > 120
            or clean_text(query, 120) != query
            or type(page) is not int
            or not 1 <= page <= 10
            or provider not in {"skillsmp", "skills.sh"}
            or type(refresh) is not bool
            or sort not in {"stars", "recent"}
            or kind == "skills" and provider == "skills.sh" and sort == "recent"
        ):
            raise ValueError("Choose a bounded integration search")
        query = query.strip() or DEFAULT_QUERY[kind]
        cache_key = f"list:{kind}:{provider}:{query}:{page}"
        if sort == "recent":
            cache_key += ":recent"
        key = hashlib.sha256(cache_key.encode()).hexdigest()
        with self._lock:
            previous = read_record(self.root / f"{key}.json")
            if (not refresh and previous and 0 <= time.time() - previous.get("checked_at", 0) < TTL
                    and (kind != "mcps" or previous["result"].get("page_size") == 40)):
                return {**self._cached_catalog(previous["result"]), "sort": sort}
            try:
                if kind == "mcps":
                    if page != 1:
                        raise ValueError("MCP Registry search returns a bounded first page")
                    client = MCPCatalogClient(
                        self.root / "mcp-registry.json", transport=self.transport
                    )
                    records, cached = client.search(query, limit=40, refresh=refresh)
                    values = [asdict(row) for row in records]
                    stale = cached and (client.last_cache_age_seconds or 0) >= TTL
                    more = False
                else:
                    result = search(
                        SearchRequest(
                            query,
                            provider=provider,
                            sort=sort if provider == "skillsmp" else "relevance",
                            page=page,
                        ),
                        transport=self.transport,
                    )
                    if result.status not in {CatalogStatus.OK, CatalogStatus.EMPTY}:
                        raise ValueError(STATUS_TEXT.get(result.status, "Catalog unavailable"))
                    values, stale, more = (
                        [row.payload() for row in result.records],
                        False,
                        result.has_next,
                    )
                items = []
                for payload in values:
                    identity = self._item(kind, payload)
                    items.append(self._public(identity, self._read(identity)))
                if kind == "mcps" and sort == "recent":
                    items.sort(key=lambda item: item["updated_at"], reverse=True)
                result = {
                    "items": items,
                    "query": query,
                    "sort": sort,
                    "page": page,
                    "page_size": 40 if kind == "mcps" else 20,
                    "more": more,
                    "checked_at": time.time(),
                    "stale": stale,
                    "notice": "Cached results" if stale else "",
                }
                self._save(key, {"checked_at": time.time(), "result": result})
                return result
            except (ValueError, RuntimeError, OSError):
                fallback = self._cached_catalog(previous.get("result", {}))
                if previous and time.time() - previous.get("checked_at", 0) > 7 * 86400:
                    fallback = {}
                return {
                    **fallback,
                    "items": fallback.get("items", []),
                    "stale": True,
                    "query": query,
                    "sort": sort,
                    "more": False,
                    "error": ("Catalog unavailable. Retry or choose another source."),
                    "page": page,
                }

    def _cached_catalog(self, result):
        items = []
        for item in result.get("items", []):
            if "github_repository" not in item or "updated_at" not in item:
                try:
                    item = self._public(item["id"], self._read(item["id"]))
                except (ValueError, OSError):
                    pass
            items.append(item)
        return {**result, "items": items}

    def detail(self, identity, *, source="", resolve=False):
        with self._lock:
            value = self._read(identity)
            if resolve:
                if value["kind"] != "skills":
                    raise ValueError("Choose a Skill source")
                payload = value["payload"]
                if source:
                    # SkillRecord validates HTTPS GitHub identity and exact repository agreement.
                    payload = {**payload, "source_url": source}
                record = SkillRecord.from_payload(payload)
                result = resolve_source(record, transport=self.transport)
                if result["status"] != "ok":
                    raise ValueError(
                        "Source could not be verified. Enter the exact SKILL.md GitHub URL."
                    )
                value["resolved"] = result["record"]
                self._save(identity, value)
            return self._public(identity, value)

    def repository_stars(self, identity):
        """Enrich a saved item from its declared repository, separately from browsing."""
        item = self._public(identity, self._read(identity))
        repository = item["github_repository"]
        result = {"id": identity, "repository": repository, "stars": None, "stale": False}
        if not repository:
            return result
        # Share a bounded cache across catalogs and clients. A failed read keeps a
        # recent known value and cools down instead of repeatedly hitting GitHub.
        with self._stars_lock:
            path = self.root / "repository-stars.json"
            records = read_record(path)
            key, now = repository.casefold(), time.time()
            old = records.get(key, {})
            failed = old.get("unavailable", False)
            if 0 <= now - old.get("attempted_at", 0) < (300 if failed else TTL):
                return {**result, "stars": old.get("stars"), "stale": failed,
                        "checked_at": old.get("checked_at")}
            try:
                count = github_repository_stars(
                    "https://github.com/" + repository, transport=self.transport
                )
                value = {"stars": count, "checked_at": now, "attempted_at": now}
            except (ValueError, RuntimeError, OSError):
                age = now - (old.get("checked_at") or 0)
                known = old.get("stars") if 0 <= age <= 7 * 86400 else None
                value = {"stars": known, "checked_at": old.get("checked_at"),
                         "attempted_at": now, "unavailable": True}
            records[key] = value
            records = dict(sorted(records.items(), key=lambda row: row[1]["attempted_at"])[-64:])
            atomic_write_private(path, json.dumps(records))
            return {**result, "stars": value["stars"], "stale": value.get("unavailable", False),
                    "checked_at": value["checked_at"]}

    def mcp_draft(self, draft):
        if set(draft) != {"operation", "id", "name"}:
            raise ValueError("Choose an exact MCP Store item and local name")
        value = self._read(draft["id"])
        if value["kind"] != "mcps":
            raise ValueError("Choose an MCP Store item")
        # Refresh this exact registry identity before creating the immutable review.
        old = MCPCatalogServer(**value["payload"])
        server = MCPCatalogClient(self.root / "mcp-registry.json", transport=self.transport).get(
            old.name, refresh=True
        )
        plan = self._remote(server)
        if not plan or server.version != old.version or plan != self._remote(old):
            raise ValueError("Registry plan changed; refresh the Store item before reviewing")
        return {"operation": "mcp-add", "name": draft["name"], "url": plan.url}

    def skill_fields(self, draft):
        if (
            set(draft) != {"operation", "id", "name"}
            or not isinstance(draft["name"], str)
            or len(draft["name"]) > 80
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", draft["name"])
        ):
            raise ValueError("Use a Skill name with lowercase letters, numbers and dashes")
        value = self._read(draft["id"])
        if value["kind"] != "skills" or not value.get("resolved"):
            raise ValueError("Verify the original Skill source before reviewing")
        record = SkillRecord.from_payload(value["resolved"])
        if not record.canonical_identity:
            raise ValueError("Verify an exact Skill revision")
        if (self.cfg.skills_dir / draft["name"]).exists():
            raise ValueError("Skill already installed; choose another local name")
        return (
            {"record": {**record.payload(), "name": draft["name"]}},
            f"skill:{draft['name']}",
            (
                f"Install {draft['name']} from {record.repository}/{record.skill_path} at commit "
                f"{record.revision}. Downloads the bounded skill folder and indexes text with the "
                "configured embedding model. No scripts run; existing Skills are never overwritten."
            ),
        )


def install_skill(cfg, request):
    from .skill_store_operations import install

    return install(cfg, request)
