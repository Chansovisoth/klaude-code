"""Read-only skill catalog adapters. Catalog identity never implies source trust."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import quote, unquote, urlsplit

import httpx

MAX_RESPONSE_BYTES = 1_000_000
MAX_SKILL_FILE_BYTES = 2_000_000
MAX_SKILL_PACKAGE_BYTES = 16_000_000
MAX_SKILL_FILES = 100
PAGE_SIZE = 20
MAX_PAGE = 10
PROVIDERS = ("skillsmp", "skills.sh")


class CatalogStatus(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    NETWORK = "network"
    TIMEOUT = "timeout"
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    UNAVAILABLE = "unavailable"
    MALFORMED = "malformed"
    UNRESOLVED = "unresolved"


STATUS_TEXT = {
    CatalogStatus.EMPTY: "No matches",
    CatalogStatus.NETWORK: "Network unavailable",
    CatalogStatus.TIMEOUT: "Search timed out",
    CatalogStatus.AUTH: "Authentication required or access denied",
    CatalogStatus.RATE_LIMIT: "Rate limited or daily quota exhausted; retry later",
    CatalogStatus.UNAVAILABLE: "Service unavailable",
    CatalogStatus.MALFORMED: "Unsupported or malformed catalog response",
    CatalogStatus.UNRESOLVED: "Source not resolved",
}


def clean_text(value: object, limit: int = 2000) -> str:
    if not isinstance(value, str):
        return ""
    # Remove full terminal sequences, not just ESC (which leaves misleading text).
    value = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", value)
    value = re.sub(r"(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]", "", value)
    value = "".join(c for c in value if unicodedata.category(c) not in {"Cc", "Cf", "Cs"}
                    or c in "\n\t")
    return " ".join(value.split())[:limit].rstrip()


def _exact_field(value: object, limit: int) -> str:
    """Keep provider identities and source claims only when fully representable."""
    return value if isinstance(value, str) and 0 < len(value) <= limit and (
        clean_text(value, limit) == value
    ) else ""


def github_location(value: str) -> tuple[str, str, str] | None:
    """Return repository, candidate ref/path; only verified paths become canonical."""
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.fragment:
        return None
    parts = unquote(parsed.path).strip("/").split("/")
    if len(parts) < 2 or not all(
        re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part not in {".", ".."}
        for part in parts[:2]
    ):
        return None
    repo = "/".join(parts[:2])
    if len(parts) >= 5 and parts[2] in {"tree", "blob"}:
        if any(part in {"", ".", ".."} for part in parts[3:]):
            return None
        return repo, parts[3], "/".join(parts[4:])
    return repo, "", ""


@dataclass(frozen=True)
class Popularity:
    metric: str
    value: int

    def __post_init__(self) -> None:
        if self.metric not in {"Repository stars", "Installs"} or (
            type(self.value) is not int or not 0 <= self.value <= 10**12
        ):
            raise ValueError("Invalid popularity metadata")


@dataclass(frozen=True)
class SkillRecord:
    provider: str
    item_id: str
    name: str
    description: str = ""
    repository: str = ""
    source_url: str = ""
    catalog_url: str = ""
    popularity: Popularity | None = None
    catalog_updated: str = ""
    language: str = ""
    fetched_at: float = 0
    # These are source-resolved fields, never inferred from a catalog slug.
    skill_path: str = ""
    revision: str = ""
    source_activity: str = ""
    license: str = ""
    license_source: str = ""
    compatibility: str = ""
    first_party: str = "Unknown"
    audit: str = "Unknown"

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS or not self.item_id or not self.name:
            raise ValueError("Invalid provider identity")
        for field, value in asdict(self).items():
            if field in {"popularity", "fetched_at"}:
                continue
            if not isinstance(value, str) or len(value) > 2000 or clean_text(value) != value:
                raise ValueError("Unsafe or oversized metadata")
        if self.popularity is not None and not isinstance(self.popularity, Popularity):
            raise ValueError("Invalid popularity metadata")
        if type(self.fetched_at) not in {int, float} or (
            not math.isfinite(self.fetched_at) or not 0 <= self.fetched_at <= 4102444800
        ):
            raise ValueError("Invalid metadata timestamp")
        if self.repository and github_location("https://github.com/" + self.repository) != (
            self.repository, "", ""
        ):
            raise ValueError("Invalid repository")
        if self.source_url and github_location(self.source_url) is None:
            raise ValueError("Invalid source URL")
        location = github_location(self.source_url) if self.source_url else None
        if location and location[0].casefold() != self.repository.casefold():
            raise ValueError("Repository and source URL disagree")
        if self.revision and not re.fullmatch(r"[a-f0-9]{40}", self.revision):
            raise ValueError("Invalid source revision")
        if self.skill_path and (not self.revision or any(
            part in {"", ".", ".."} for part in self.skill_path.split("/")
        )):
            raise ValueError("Invalid resolved skill path")

    @property
    def identity(self) -> str:
        return self.provider + ":" + hashlib.sha256(self.item_id.encode()).hexdigest()

    @property
    def canonical_identity(self) -> tuple[str, str] | None:
        return (self.repository.casefold(), self.skill_path) if (
            self.repository and self.skill_path and self.revision
        ) else None

    def payload(self) -> dict:
        return asdict(self)

    @classmethod
    def from_payload(cls, data: dict) -> SkillRecord:
        data = dict(data)
        popularity = data.get("popularity")
        data["popularity"] = Popularity(**popularity) if popularity else None
        return cls(**data)


@dataclass(frozen=True)
class SearchRequest:
    query: str
    provider: str = "skillsmp"
    sort: str = "stars"
    page: int = 1

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS or not 1 <= self.page <= MAX_PAGE:
            raise ValueError("Unsupported provider or page")
        if not 1 <= len(self.query) <= 120 or clean_text(self.query, 120) != self.query:
            raise ValueError("Use a search query of 1–120 printable characters")
        if self.sort not in ({"stars", "recent"} if self.provider == "skillsmp" else {"relevance"}):
            raise ValueError("Unsupported sort")
        if self.provider == "skills.sh" and self.page != 1:
            raise ValueError("Provisional provider has no supported pagination")

    @property
    def identity(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class SearchResult:
    status: CatalogStatus
    records: tuple[SkillRecord, ...] = ()
    has_next: bool = False
    fetched_at: float = 0

    def payload(self) -> dict:
        return {"status": self.status.value, "records": [r.payload() for r in self.records],
                "has_next": self.has_next, "fetched_at": self.fetched_at}

    @classmethod
    def from_payload(cls, data: dict) -> SearchResult:
        records = tuple(SkillRecord.from_payload(r) for r in data["records"])
        if len(records) > PAGE_SIZE or type(data["has_next"]) is not bool:
            raise ValueError("Invalid worker result")
        stamp = data["fetched_at"]
        if type(stamp) not in {int, float} or (
            not math.isfinite(stamp) or not 0 <= stamp <= 4102444800
        ):
            raise ValueError("Invalid result timestamp")
        return cls(CatalogStatus(data["status"]), records, data["has_next"], data["fetched_at"])


class CatalogFailure(Exception):
    def __init__(self, status: CatalogStatus):
        self.status = status
        super().__init__(status.value)


class CatalogHTTP:
    """Fixed public origins, no redirects/proxies/ambient credentials, bounded JSON."""
    def __init__(self, transport: httpx.BaseTransport | None = None, *,
                 deadline_seconds: int = 12, max_response_bytes: int = MAX_RESPONSE_BYTES):
        if not 1 <= deadline_seconds <= 60 or not 1 <= max_response_bytes <= 4_000_000:
            raise ValueError("Unsupported catalog HTTP budget")
        self.transport = transport
        self.deadline = time.monotonic() + deadline_seconds
        self.max_response_bytes = max_response_bytes

    def get(self, url: str, params: dict | None = None) -> dict:
        value = self.get_json(url, params)
        if not isinstance(value, dict):
            raise CatalogFailure(CatalogStatus.MALFORMED)
        return value

    def get_json(self, url: str, params: dict | None = None) -> object:
        if urlsplit(url).scheme != "https" or urlsplit(url).netloc not in {
            "skillsmp.com", "skills.sh", "api.github.com"
        }:
            raise CatalogFailure(CatalogStatus.MALFORMED)
        if time.monotonic() >= self.deadline:
            raise CatalogFailure(CatalogStatus.TIMEOUT)
        try:
            with httpx.Client(transport=self.transport, trust_env=False, follow_redirects=False,
                              timeout=httpx.Timeout(5, connect=3),
                              headers={"User-Agent": "klaude-code/skill-discovery",
                                       "Accept": "application/json"}) as client:
                with client.stream("GET", url, params=params) as response:
                    status = response.status_code
                    if status == 403 and response.headers.get("x-ratelimit-remaining") == "0":
                        raise CatalogFailure(CatalogStatus.RATE_LIMIT)
                    if status in {401, 403}:
                        raise CatalogFailure(CatalogStatus.AUTH)
                    if status == 429:
                        raise CatalogFailure(CatalogStatus.RATE_LIMIT)
                    if status >= 500:
                        raise CatalogFailure(CatalogStatus.UNAVAILABLE)
                    if status == 404 and urlsplit(url).netloc == "api.github.com":
                        raise CatalogFailure(CatalogStatus.UNRESOLVED)
                    if not 200 <= status < 300:
                        raise CatalogFailure(CatalogStatus.MALFORMED)
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() > self.deadline:
                            raise CatalogFailure(CatalogStatus.TIMEOUT)
                        content.extend(chunk)
                        if len(content) > self.max_response_bytes:
                            raise CatalogFailure(CatalogStatus.MALFORMED)
            return json.loads(content)
        except httpx.TimeoutException as exc:
            raise CatalogFailure(CatalogStatus.TIMEOUT) from exc
        except httpx.HTTPError as exc:
            raise CatalogFailure(CatalogStatus.NETWORK) from exc
        except (ValueError, UnicodeError) as exc:
            raise CatalogFailure(CatalogStatus.MALFORMED) from exc


def _metric(label: str, value: object) -> Popularity | None:
    return Popularity(label, value) if type(value) is int and 0 <= value <= 10**12 else None


def _catalog_time(value: object) -> str:
    """Render supported provider timestamps without showing opaque epoch values."""
    if isinstance(value, str) and len(value) > 40:
        return ""
    if type(value) is int or isinstance(value, str) and re.fullmatch(r"\d{10}", value):
        stamp = int(value)
        if not 946684800 <= stamp <= 4102444800:
            return ""
        date = datetime.fromtimestamp(stamp, UTC)
    elif isinstance(value, str):
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
        if date.tzinfo is None:
            return ""
        date = date.astimezone(UTC)
    else:
        return ""
    return date.strftime("%Y-%m-%d %H:%M UTC")


class SkillsMP:
    def search(self, http: CatalogHTTP, request: SearchRequest) -> SearchResult:
        payload = http.get("https://skillsmp.com/api/v1/skills/search", {
            "q": request.query, "limit": PAGE_SIZE, "page": request.page, "sortBy": request.sort,
        })
        if payload.get("success") is not True or not isinstance(payload.get("data"), dict):
            raise CatalogFailure(CatalogStatus.MALFORMED)
        data = payload["data"]
        items, pagination = data.get("skills"), data.get("pagination")
        if not isinstance(items, list) or not isinstance(pagination, dict) or (
            type(pagination.get("hasNext")) is not bool
        ):
            raise CatalogFailure(CatalogStatus.MALFORMED)
        records = []
        now = time.time()
        for item in items[:PAGE_SIZE]:
            if not isinstance(item, dict) or not _exact_field(item.get("id"), 512) or (
                not clean_text(item.get("name"), 200)
            ):
                raise CatalogFailure(CatalogStatus.MALFORMED)
            source = _exact_field(item.get("githubUrl"), 1000)
            location = github_location(source)
            records.append(SkillRecord(
                "skillsmp", item["id"], clean_text(item["name"], 200),
                clean_text(item.get("description")), location[0] if location else "",
                source if location else "",
                popularity=_metric("Repository stars", item.get("stars")),
                catalog_updated=_catalog_time(item.get("updatedAt")),
                language=clean_text(item.get("contentLanguage"), 32), fetched_at=now,
            ))
        return SearchResult(CatalogStatus.OK if records else CatalogStatus.EMPTY, tuple(records),
                            pagination["hasNext"] and request.page < MAX_PAGE, now)


class SkillsSH:
    """Provisional CLI endpoint: relevance only, no invented pagination or paths."""
    def search(self, http: CatalogHTTP, request: SearchRequest) -> SearchResult:
        payload = http.get("https://skills.sh/api/search", {"q": request.query, "limit": PAGE_SIZE})
        items = payload.get("skills")
        if not isinstance(items, list):
            raise CatalogFailure(CatalogStatus.MALFORMED)
        now = time.time()
        records = []
        for item in items[:PAGE_SIZE]:
            if not isinstance(item, dict) or not _exact_field(item.get("id"), 512) or (
                not clean_text(item.get("name"), 200)
            ):
                raise CatalogFailure(CatalogStatus.MALFORMED)
            source = _exact_field(item.get("source"), 200)
            location = github_location("https://github.com/" + source)
            repo = location[0] if location and source == location[0] else ""
            records.append(SkillRecord(
                "skills.sh", item["id"], clean_text(item["name"], 200),
                clean_text(item.get("description")), repo,
                "https://github.com/" + repo if repo else "",
                popularity=_metric("Installs", item.get("installs")), fetched_at=now,
            ))
        return SearchResult(CatalogStatus.OK if records else CatalogStatus.EMPTY, tuple(records),
                            fetched_at=now)


def search(request: SearchRequest, *, transport: httpx.BaseTransport | None = None) -> SearchResult:
    try:
        adapter = SkillsMP() if request.provider == "skillsmp" else SkillsSH()
        result = adapter.search(CatalogHTTP(transport), request)
        # Deduplicate only provider IDs, never names or unverified source paths.
        return SearchResult(result.status, tuple({r.identity: r for r in result.records}.values()),
                            result.has_next, result.fetched_at)
    except CatalogFailure as exc:
        return SearchResult(exc.status)
    except (ValueError, TypeError, KeyError):
        return SearchResult(CatalogStatus.MALFORMED)


def merge_resolved(records: tuple[SkillRecord, ...]) -> tuple[tuple[SkillRecord, ...], ...]:
    """Group proven same-source paths while retaining all provider records/metrics."""
    groups: dict[object, list[SkillRecord]] = {}
    for record in records:
        key = record.canonical_identity or record.identity
        groups.setdefault(key, []).append(record)
    return tuple(tuple(group) for group in groups.values())


def _frontmatter_scalar(text: str, field: str) -> str:
    if not text.startswith("---\n") or "\n---" not in text[4:]:
        return ""
    header = text[4:].split("\n---", 1)[0][:8000]
    match = re.search(r"^" + field + r":\s*([^\n]+)$", header, re.MULTILINE)
    if not match:
        return ""
    value = match[1].strip()
    if value.startswith('"'):
        try:
            value = json.loads(value)
        except ValueError:
            return ""
    elif value.startswith("'") and value.endswith("'"):
        value = value[1:-1].replace("''", "'")
    elif any(c in value for c in "#{}[]&*!|>"):
        return ""  # Complex YAML remains unknown rather than misparsed.
    return clean_text(value, 1000)


def resolve_source(record: SkillRecord, *, transport: httpx.BaseTransport | None = None) -> dict:
    """Verify the candidate SKILL.md at an exact commit, without importing content."""
    from dataclasses import replace

    location = github_location(record.source_url)
    if not location or not location[1] or not location[2]:
        return {"status": CatalogStatus.UNRESOLVED.value, "record": record.payload()}
    repo, ref, path = location
    path = path if path.endswith("SKILL.md") else path.rstrip("/") + "/SKILL.md"
    try:
        http = CatalogHTTP(transport)
        # A tree URL does not identify where a slash-containing branch ends.
        # Resolve actual branch refs and choose the longest matching boundary.
        # Never promote a slug-derived or guessed path into canonical identity.
        if re.fullmatch(r"[a-f0-9]{40}", ref):
            source_revision = ref
        else:
            refs = http.get_json(
                f"https://api.github.com/repos/{repo}/git/matching-refs/heads/{quote(ref, safe='')}"
            )
            if not isinstance(refs, list) or len(refs) > 1000:
                raise CatalogFailure(CatalogStatus.MALFORMED)
            tail = ref + "/" + location[2]
            candidates = []
            for item in refs:
                if not isinstance(item, dict) or not isinstance(item.get("ref"), str):
                    raise CatalogFailure(CatalogStatus.MALFORMED)
                branch = item["ref"].removeprefix("refs/heads/")
                if item["ref"].startswith("refs/heads/") and tail.startswith(branch + "/"):
                    candidates.append((branch, item.get("object", {}).get("sha", "")))
            if not candidates:
                raise CatalogFailure(CatalogStatus.UNRESOLVED)
            branch, source_revision = max(candidates, key=lambda item: len(item[0]))
            path = tail[len(branch) + 1:]
            path = path if path.endswith("SKILL.md") else path.rstrip("/") + "/SKILL.md"
        if not isinstance(source_revision, str) or not re.fullmatch(
            r"[a-f0-9]{40}", source_revision
        ):
            raise CatalogFailure(CatalogStatus.MALFORMED)
        # Git commit metadata avoids the REST commit endpoint's potentially huge diffs.
        commit = http.get(f"https://api.github.com/repos/{repo}/git/commits/{source_revision}")
        sha = commit.get("sha")
        if not isinstance(sha, str) or sha != source_revision:
            raise CatalogFailure(CatalogStatus.MALFORMED)
        content = http.get(f"https://api.github.com/repos/{repo}/contents/{quote(path, safe='/')}",
                           {"ref": sha})
        if content.get("type") != "file" or content.get("path") != path or (
            content.get("encoding") != "base64" or type(content.get("size")) is not int
            or not 0 <= content["size"] <= 128_000
        ):
            raise CatalogFailure(CatalogStatus.MALFORMED)
        text = base64.b64decode(content["content"]).decode("utf-8")
        if len(text.encode()) > 128_000:
            raise CatalogFailure(CatalogStatus.MALFORMED)
        activity = _catalog_time(commit.get("committer", {}).get("date"))
        exact_url = f"https://github.com/{repo}/blob/{sha}/{quote(path, safe='/')}"
        license_value = _frontmatter_scalar(text, "license")
        resolved = replace(record, skill_path=path, revision=sha,
                           source_activity=activity, license=license_value,
                           license_source=exact_url if license_value else "",
                           compatibility=_frontmatter_scalar(text, "compatibility"))
        return {"status": CatalogStatus.OK.value, "record": resolved.payload()}
    except CatalogFailure as exc:
        return {"status": exc.status.value, "record": record.payload()}
    except (ValueError, KeyError, TypeError, AttributeError):
        return {"status": CatalogStatus.MALFORMED.value, "record": record.payload()}


def check_github_skill_update(
    name: str, source_url: str, current_revision: str,
    *, transport: httpx.BaseTransport | None = None,
) -> dict:
    """Resolve the current default branch and verify the same SKILL.md path."""
    location = github_location(source_url)
    if not location or location[1] != current_revision or not re.fullmatch(
        r"[a-f0-9]{40}", current_revision
    ) or not location[2].endswith("SKILL.md"):
        return {"status": "unsupported"}
    repo, _old_revision, path = location
    try:
        http = CatalogHTTP(transport)
        metadata = http.get(f"https://api.github.com/repos/{repo}")
        branch = metadata.get("default_branch")
        if not isinstance(branch, str) or not 1 <= len(branch) <= 120 or (
            clean_text(branch, 120) != branch
        ):
            raise CatalogFailure(CatalogStatus.MALFORMED)
        refs = http.get_json(
            f"https://api.github.com/repos/{repo}/git/matching-refs/heads/"
            f"{quote(branch, safe='')}"
        )
        if not isinstance(refs, list) or len(refs) > 1000:
            raise CatalogFailure(CatalogStatus.MALFORMED)
        matching = [entry for entry in refs if isinstance(entry, dict) and (
            entry.get("ref") == f"refs/heads/{branch}"
        )]
        if len(matching) != 1 or not isinstance(matching[0].get("object"), dict):
            raise CatalogFailure(CatalogStatus.UNRESOLVED)
        revision = matching[0]["object"].get("sha")
        if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise CatalogFailure(CatalogStatus.MALFORMED)
        if revision == current_revision:
            return {"status": "current", "revision": current_revision}
        candidate = SkillRecord(
            "skillsmp", f"installed:{repo}:{path}", name,
            repository=repo,
            source_url=f"https://github.com/{repo}/blob/{revision}/{quote(path, safe='/')}",
        )
        resolved = resolve_source(candidate, transport=transport)
        if resolved["status"] != CatalogStatus.OK.value:
            return {"status": resolved["status"]}
        return {"status": "available", "record": resolved["record"],
                "current_revision": current_revision}
    except CatalogFailure as exc:
        return {"status": exc.status.value}
    except (KeyError, TypeError, ValueError):
        return {"status": CatalogStatus.MALFORMED.value}


def download_resolved_skill(
    record: SkillRecord, *, transport: httpx.BaseTransport | None = None
) -> dict[str, bytes]:
    """Read one verified skill folder at its pinned Git commit, without executing it."""
    if not record.canonical_identity or not record.skill_path.endswith("SKILL.md"):
        raise ValueError("Resolve the original SKILL.md before installing")
    if github_location(record.source_url) is None:
        raise ValueError("A verified GitHub source is required")
    http = CatalogHTTP(transport, deadline_seconds=60, max_response_bytes=4_000_000)
    base = f"https://api.github.com/repos/{record.repository}/git"
    commit = http.get(f"{base}/commits/{record.revision}")
    tree = commit.get("tree")
    if commit.get("sha") != record.revision or not isinstance(tree, dict) or not re.fullmatch(
        r"[a-f0-9]{40}", str(tree.get("sha", ""))
    ):
        raise ValueError("Pinned source revision is unavailable")

    def entries(tree_sha: str) -> list[dict]:
        payload = http.get(f"{base}/trees/{tree_sha}")
        items = payload.get("tree")
        if payload.get("sha") != tree_sha or payload.get("truncated") is not False or (
            not isinstance(items, list) or len(items) > 1000
        ):
            raise ValueError("Source tree is incomplete or unsupported")
        if not all(isinstance(item, dict) for item in items):
            raise ValueError("Source tree is malformed")
        return items

    def safe_entry(item: dict) -> tuple[str, str, str, str]:
        name, kind, mode, sha = (item.get(key) for key in ("path", "type", "mode", "sha"))
        if not isinstance(name, str) or name in {"", ".", ".."} or any(
            char in name for char in "/\\\x00"
        ) or not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{40}", sha):
            raise ValueError("Unsafe source tree entry")
        if not isinstance(kind, str) or not isinstance(mode, str) or (
            kind, mode
        ) not in {("tree", "040000"), ("blob", "100644"), ("blob", "100755")}:
            raise ValueError("Skill contains a symlink, submodule, or unsupported file")
        return name, kind, mode, sha

    folder = record.skill_path.split("/")[:-1]
    if len(folder) > 12:
        raise ValueError("Skill folder is too deep")
    tree_sha = tree["sha"]
    for segment in folder:
        child = next((item for item in entries(tree_sha) if item.get("path") == segment), None)
        if child is None:
            raise ValueError("Resolved skill folder no longer exists at this revision")
        _name, kind, _mode, tree_sha = safe_entry(child)
        if kind != "tree":
            raise ValueError("Resolved skill path is not a folder")

    files: dict[str, bytes] = {}
    queued = [("", tree_sha, 0)]
    total = 0
    directories = 0
    while queued:
        prefix, current_sha, depth = queued.pop()
        directories += 1
        if directories > MAX_SKILL_FILES:
            raise ValueError("Skill package has too many directories")
        if depth > 12:
            raise ValueError("Skill folder is too deep")
        for item in entries(current_sha):
            name, kind, _mode, sha = safe_entry(item)
            path = f"{prefix}{name}"
            if len(path) > 512 or path in files:
                raise ValueError("Unsafe or duplicate skill path")
            if kind == "tree":
                queued.append((path + "/", sha, depth + 1))
                if len(queued) > MAX_SKILL_FILES:
                    raise ValueError("Skill package has too many directories")
                continue
            size = item.get("size")
            if type(size) is not int or not 0 <= size <= MAX_SKILL_FILE_BYTES:
                raise ValueError("Skill file is too large or has unknown size")
            total += size
            if total > MAX_SKILL_PACKAGE_BYTES or len(files) >= MAX_SKILL_FILES:
                raise ValueError("Skill package exceeds download limits")
            blob = http.get(f"{base}/blobs/{sha}")
            if blob.get("sha") != sha or blob.get("encoding") != "base64" or (
                blob.get("size") != size or not isinstance(blob.get("content"), str)
            ):
                raise ValueError("Pinned skill file changed or is malformed")
            try:
                body = base64.b64decode(blob["content"].replace("\n", ""), validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError("Pinned skill file is malformed") from exc
            object_id = hashlib.sha1(
                f"blob {len(body)}\0".encode() + body, usedforsecurity=False
            ).hexdigest()
            if len(body) != size or object_id != sha:
                raise ValueError("Pinned skill file failed integrity check")
            files[path] = body
    if "SKILL.md" not in files:
        raise ValueError("Pinned folder has no SKILL.md")
    try:
        files["SKILL.md"].decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("SKILL.md is not UTF-8 text") from exc
    return files
