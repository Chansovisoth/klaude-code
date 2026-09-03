"""Local-first entity names, conservative typo correction, and optional Wikimedia lookup."""

from __future__ import annotations

import math
import re
import sqlite3
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
TRUSTED_ENTITY_SOURCES = {
    "conversation_entity",
    "official_site",
    "structured_vocabulary",
    "verified_search",
    "wikidata",
    "wikipedia",
}
QUERY_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "does",
    "for",
    "in",
    "is",
    "it",
    "its",
    "me",
    "of",
    "on",
    "or",
    "the",
    "their",
    "them",
    "they",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
}
RELATIONSHIP_WORDS = {
    "chair",
    "chairman",
    "chairperson",
    "chairwoman",
    "dean",
    "director",
    "established",
    "founded",
    "head",
    "leadership",
    "president",
    "principal",
    "rector",
}
TOKEN_RE = re.compile(r"[@#]?[A-Za-z0-9][A-Za-z0-9_.+#@-]*")


@dataclass(frozen=True)
class StructuredEntity:
    canonical_name: str
    entity_type: str
    aliases: tuple[str, ...] = ()
    country: str | None = None
    description: str | None = None
    domain: str | None = None
    confidence: float = 0.96


@dataclass(frozen=True)
class EntityRecord:
    canonical_name: str
    entity_type: str | None = None
    aliases: tuple[str, ...] = ()
    source: str = "local_entity_cache"
    source_id: str | None = None
    country: str | None = None
    language: str | None = None
    description: str | None = None
    domain: str | None = None
    confidence: float = 0.8
    successful_resolution_count: int = 0
    last_seen_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class NameCandidate:
    entity: EntityRecord
    matched_alias: str
    string_score: float
    final_score: float
    source: str


@dataclass(frozen=True)
class QueryCorrection:
    original: str
    corrected: str
    kind: str
    confidence: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "corrected": self.corrected,
            "kind": self.kind,
            "confidence": round(self.confidence, 4),
            "source": self.source,
        }


@dataclass(frozen=True)
class QueryNormalization:
    original_text: str
    normalized_text: str
    corrections: tuple[QueryCorrection, ...] = ()
    resolved_entities: tuple[EntityRecord, ...] = ()


@dataclass(frozen=True)
class _AliasEntry:
    alias: str
    normalized_alias: str
    entity: EntityRecord
    source: str
    confidence: float


def normalize_name(text: str) -> str:
    """Normalize a name for lookup without erasing its original display form."""
    folded = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return " ".join(re.findall(r"[\w+#@.-]+", folded, flags=re.UNICODE))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _structured_entity(
    canonical_name: str,
    entity_type: str,
    *aliases: str,
    country: str | None = None,
    description: str | None = None,
    domain: str | None = None,
) -> StructuredEntity:
    return StructuredEntity(
        canonical_name=canonical_name,
        entity_type=entity_type,
        aliases=tuple(aliases),
        country=country,
        description=description,
        domain=domain,
    )


# This intentionally stays compact. It covers stable, high-value names and lets the
# local database plus on-demand Wikimedia fill the long tail over time.
STRUCTURED_ENTITIES: tuple[StructuredEntity, ...] = (
    _structured_entity(
        "Cambodia", "country", "Cambodian", "Khmer", "Kampuchea", country="Cambodia"
    ),
    _structured_entity("Thailand", "country", "Thai", country="Thailand"),
    _structured_entity("Singapore", "country", "Singaporean", country="Singapore"),
    _structured_entity("Vietnam", "country", "Vietnamese", country="Vietnam"),
    _structured_entity("Laos", "country", "Lao", "Laotian", country="Laos"),
    _structured_entity("Malaysia", "country", "Malaysian", country="Malaysia"),
    _structured_entity("Indonesia", "country", "Indonesian", country="Indonesia"),
    _structured_entity("Philippines", "country", "Filipino", country="Philippines"),
    _structured_entity("Myanmar", "country", "Burmese", "Burma", country="Myanmar"),
    _structured_entity("Brunei", "country", "Bruneian", country="Brunei"),
    _structured_entity(
        "United States", "country", "USA", "US", "American", country="United States"
    ),
    _structured_entity("United Kingdom", "country", "UK", "British", country="United Kingdom"),
    _structured_entity("Australia", "country", "Australian", country="Australia"),
    _structured_entity("Canada", "country", "Canadian", country="Canada"),
    _structured_entity("India", "country", "Indian", country="India"),
    _structured_entity("China", "country", "Chinese", country="China"),
    _structured_entity("Japan", "country", "Japanese", country="Japan"),
    _structured_entity(
        "South Korea", "country", "Korean", "Republic of Korea", country="South Korea"
    ),
    _structured_entity("Germany", "country", "German", country="Germany"),
    _structured_entity("France", "country", "French", country="France"),
    _structured_entity("Brazil", "country", "Brazilian", country="Brazil"),
    _structured_entity("Mexico", "country", "Mexican", country="Mexico"),
    _structured_entity("Python", "programming_language"),
    _structured_entity("JavaScript", "programming_language", "JS"),
    _structured_entity("TypeScript", "programming_language", "TS"),
    _structured_entity("Go", "programming_language", "Golang"),
    _structured_entity("Rust", "programming_language"),
    _structured_entity("C", "programming_language"),
    _structured_entity("C++", "programming_language", "CPP"),
    _structured_entity("C#", "programming_language", "CSharp"),
    _structured_entity("R", "programming_language"),
    _structured_entity("React", "software_library", domain="react.dev"),
    _structured_entity("Next.js", "software_framework", "NextJS", domain="nextjs.org"),
    _structured_entity("Django", "software_framework", domain="djangoproject.com"),
    _structured_entity("FastAPI", "software_framework", domain="fastapi.tiangolo.com"),
    _structured_entity("NumPy", "software_library", "numpy", domain="numpy.org"),
    _structured_entity("PyTorch", "software_library", "pytorch", domain="pytorch.org"),
    _structured_entity("RapidFuzz", "software_library", "rapidfuzz"),
    _structured_entity("Hyprland", "software", domain="hypr.land"),
    _structured_entity("EndeavourOS", "operating_system", domain="endeavouros.com"),
    _structured_entity("Linux", "operating_system"),
    _structured_entity("Ubuntu", "operating_system", domain="ubuntu.com"),
    _structured_entity("OpenAI", "organization", domain="openai.com"),
    _structured_entity("DeepSeek", "organization", domain="deepseek.com"),
    _structured_entity("Qwen", "ai_model", domain="qwen.ai"),
    _structured_entity("Ollama", "software", domain="ollama.com"),
    _structured_entity("Klaude", "software"),
    _structured_entity("Bonghos", "software"),
    _structured_entity(
        "American Intercon School",
        "school",
        "AIS",
        country="Cambodia",
        description="a Cambodian school",
        domain="ais.edu.kh",
    ),
    _structured_entity(
        "Paragon International University",
        "university",
        "PIU",
        "Paragon",
        country="Cambodia",
        domain="paragoniu.edu.kh",
    ),
    _structured_entity(
        "Automatic Identification System",
        "maritime_system",
        "AIS",
        description="a maritime vessel identification and tracking system",
    ),
    _structured_entity(
        "Advanced Info Service",
        "telecommunications_company",
        "AIS",
        country="Thailand",
        domain="ais.th",
    ),
    _structured_entity("Artificial immune system", "computing_technique", "AIS"),
)


class EntityStore:
    """Small, failure-tolerant SQLite store for learned canonical names and aliases."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.available = False
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 2000")
        return connection

    def _initialize(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as db:
                db.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS entities (
                        id INTEGER PRIMARY KEY,
                        canonical_name TEXT NOT NULL,
                        normalized_name TEXT NOT NULL UNIQUE,
                        entity_type TEXT,
                        source TEXT NOT NULL,
                        source_id TEXT,
                        country TEXT,
                        language TEXT,
                        description TEXT,
                        domain TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        successful_resolution_count INTEGER NOT NULL DEFAULT 0,
                        metadata_expires_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS aliases (
                        entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                        alias TEXT NOT NULL,
                        normalized_alias TEXT NOT NULL,
                        source TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(entity_id, normalized_alias)
                    );
                    CREATE INDEX IF NOT EXISTS aliases_normalized_idx
                        ON aliases(normalized_alias);
                    CREATE INDEX IF NOT EXISTS entities_last_seen_idx
                        ON entities(last_seen_at DESC);
                    """
                )
            self.available = True
        except (OSError, sqlite3.Error):
            self.available = False

    def upsert(self, entity: EntityRecord, *, metadata_ttl_days: int = 90) -> bool:
        if not self.available or entity.source not in TRUSTED_ENTITY_SOURCES:
            return False
        canonical = entity.canonical_name.strip()
        normalized = normalize_name(canonical)
        if not canonical or not normalized or entity.confidence < 0.72:
            return False
        now = _utc_now()
        expires = (datetime.now(UTC) + timedelta(days=metadata_ttl_days)).isoformat()
        aliases = _dedupe_names([canonical, *entity.aliases])
        try:
            with self._connect() as db:
                existing = db.execute(
                    "SELECT id, confidence, successful_resolution_count FROM entities "
                    "WHERE normalized_name = ?",
                    (normalized,),
                ).fetchone()
                if existing:
                    entity_id = int(existing["id"])
                    confidence = max(float(existing["confidence"]), entity.confidence)
                    db.execute(
                        """
                        UPDATE entities SET canonical_name=?, entity_type=COALESCE(?, entity_type),
                            source=?, source_id=COALESCE(?, source_id),
                            country=COALESCE(?, country), language=COALESCE(?, language),
                            description=COALESCE(?, description), domain=COALESCE(?, domain),
                            updated_at=?, last_seen_at=?, confidence=?, metadata_expires_at=?
                        WHERE id=?
                        """,
                        (
                            canonical,
                            entity.entity_type,
                            entity.source,
                            entity.source_id,
                            entity.country,
                            entity.language,
                            entity.description,
                            entity.domain,
                            now,
                            now,
                            confidence,
                            expires,
                            entity_id,
                        ),
                    )
                else:
                    cursor = db.execute(
                        """
                        INSERT INTO entities (
                            canonical_name, normalized_name, entity_type, source, source_id,
                            country, language, description, domain, created_at, updated_at,
                            last_seen_at, confidence, successful_resolution_count,
                            metadata_expires_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            canonical,
                            normalized,
                            entity.entity_type,
                            entity.source,
                            entity.source_id,
                            entity.country,
                            entity.language,
                            entity.description,
                            entity.domain,
                            now,
                            now,
                            now,
                            entity.confidence,
                            entity.successful_resolution_count,
                            expires,
                        ),
                    )
                    entity_id = int(cursor.lastrowid)
                for alias in aliases:
                    db.execute(
                        """
                        INSERT INTO aliases (
                            entity_id, alias, normalized_alias, source, confidence, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(entity_id, normalized_alias) DO UPDATE SET
                            alias=excluded.alias,
                            confidence=MAX(aliases.confidence, excluded.confidence)
                        """,
                        (
                            entity_id,
                            alias,
                            normalize_name(alias),
                            entity.source,
                            entity.confidence,
                            now,
                        ),
                    )
            return True
        except (OSError, sqlite3.Error):
            return False

    def entries(self) -> list[_AliasEntry]:
        if not self.available:
            return []
        try:
            with self._connect() as db:
                rows = db.execute(
                    """
                    SELECT e.*, a.alias, a.normalized_alias,
                           a.source AS alias_source, a.confidence AS alias_confidence
                    FROM aliases a JOIN entities e ON e.id = a.entity_id
                    """
                ).fetchall()
        except (OSError, sqlite3.Error):
            return []
        return [
            _AliasEntry(
                alias=str(row["alias"]),
                normalized_alias=str(row["normalized_alias"]),
                entity=_record_from_row(row),
                source="local_entity_cache",
                confidence=float(row["alias_confidence"]),
            )
            for row in rows
        ]

    def record_success(self, canonical_name: str) -> None:
        if not self.available:
            return
        try:
            with self._connect() as db:
                db.execute(
                    """
                    UPDATE entities SET successful_resolution_count =
                        successful_resolution_count + 1, last_seen_at=?, updated_at=?
                    WHERE normalized_name=?
                    """,
                    (_utc_now(), _utc_now(), normalize_name(canonical_name)),
                )
        except (OSError, sqlite3.Error):
            return

    def get(self, canonical_name: str) -> EntityRecord | None:
        if not self.available:
            return None
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT * FROM entities WHERE normalized_name=?",
                    (normalize_name(canonical_name),),
                ).fetchone()
                if row is None:
                    return None
                aliases = db.execute(
                    "SELECT alias FROM aliases WHERE entity_id=? ORDER BY alias",
                    (int(row["id"]),),
                ).fetchall()
        except (OSError, sqlite3.Error):
            return None
        return _record_from_row(row, tuple(str(item["alias"]) for item in aliases))

    def metadata_stale(self, canonical_name: str) -> bool:
        if not self.available:
            return False
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT metadata_expires_at FROM entities WHERE normalized_name=?",
                    (normalize_name(canonical_name),),
                ).fetchone()
        except (OSError, sqlite3.Error):
            return False
        if row is None or not row["metadata_expires_at"]:
            return False
        try:
            return datetime.fromisoformat(str(row["metadata_expires_at"])) <= datetime.now(UTC)
        except ValueError:
            return True


class WikimediaEntityClient:
    """Bounded, keyless Wikidata name lookup. All failures degrade to no result."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 3.0,
        max_results: int = 5,
        http_get: Callable[..., httpx.Response] | None = None,
    ):
        self.user_agent = user_agent
        self.timeout_seconds = max(0.5, float(timeout_seconds))
        self.max_results = max(1, min(10, int(max_results)))
        self.http_get = http_get or httpx.get

    def lookup(self, phrase: str) -> EntityRecord | None:
        minimal_phrase = " ".join(str(phrase or "").split())[:160]
        if not minimal_phrase:
            return None
        try:
            response = self.http_get(
                WIKIDATA_API_URL,
                params={
                    "action": "wbsearchentities",
                    "search": minimal_phrase,
                    "language": "en",
                    "uselang": "en",
                    "type": "item",
                    "limit": self.max_results,
                    "format": "json",
                    "origin": "*",
                },
                headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, OSError, TypeError, ValueError):
            return None
        results = payload.get("search") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return None
        ranked: list[tuple[float, dict[str, Any], str]] = []
        for item in results[: self.max_results]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            values = [label, str((item.get("match") or {}).get("text") or "")]
            values.extend(str(alias) for alias in item.get("aliases") or [])
            score = max(_string_similarity(minimal_phrase, value) for value in values if value)
            ranked.append((score, item, label))
        ranked.sort(key=lambda value: value[0], reverse=True)
        if not ranked or ranked[0][0] < 84.0:
            return None
        if (
            len(ranked) > 1
            and ranked[0][0] < 99.9
            and ranked[0][0] - ranked[1][0] < 5.0
            and normalize_name(ranked[0][2]) != normalize_name(ranked[1][2])
        ):
            return None
        score, item, label = ranked[0]
        description = str(item.get("description") or "").strip() or None
        aliases = tuple(
            alias
            for alias in _dedupe_names(
                [
                    str(alias)
                    for alias in item.get("aliases") or []
                    if str(alias).strip()
                ]
            )
            if normalize_name(alias) != normalize_name(minimal_phrase)
        )
        entity_type, country = _metadata_from_description(description or "")
        return EntityRecord(
            canonical_name=label,
            entity_type=entity_type,
            aliases=aliases,
            source="wikidata",
            source_id=str(item.get("id") or "") or None,
            country=country,
            description=description,
            confidence=min(0.98, max(0.84, score / 100.0)),
        )


class EntityResolver:
    """Central RapidFuzz resolver over stable vocabulary and learned local names."""

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        wikimedia_client: WikimediaEntityClient | None = None,
        structured_entities: Iterable[StructuredEntity] = STRUCTURED_ENTITIES,
        metadata_ttl_days: int = 90,
    ):
        self.store = EntityStore(db_path) if db_path is not None else None
        self.wikimedia_client = wikimedia_client
        self.metadata_ttl_days = max(1, int(metadata_ttl_days))
        self._structured = tuple(structured_entities)
        self._local_entries: list[_AliasEntry] | None = None
        self._structured_entries = self._build_structured_entries()

    def _build_structured_entries(self) -> list[_AliasEntry]:
        entries: list[_AliasEntry] = []
        for item in self._structured:
            record = EntityRecord(
                canonical_name=item.canonical_name,
                entity_type=item.entity_type,
                aliases=item.aliases,
                source="structured_vocabulary",
                country=item.country,
                description=item.description,
                domain=item.domain,
                confidence=item.confidence,
            )
            for alias in _dedupe_names([item.canonical_name, *item.aliases]):
                entries.append(
                    _AliasEntry(
                        alias=alias,
                        normalized_alias=normalize_name(alias),
                        entity=record,
                        source="structured_vocabulary",
                        confidence=item.confidence,
                    )
                )
        return entries

    def _entries(self) -> list[_AliasEntry]:
        if self._local_entries is None:
            self._local_entries = self.store.entries() if self.store else []
        return [*self._structured_entries, *self._local_entries]

    def find_name_candidates(
        self,
        text: str,
        *,
        entity_type: str | None = None,
        country: str | None = None,
        limit: int = 5,
    ) -> list[NameCandidate]:
        normalized = normalize_name(text)
        if not normalized:
            return []
        candidates: list[NameCandidate] = []
        for entry in self._entries():
            similarity = _string_similarity(normalized, entry.normalized_alias)
            if similarity < 55.0:
                continue
            context_boost = 0.0
            if entity_type and entry.entity.entity_type == entity_type:
                context_boost += 3.0
            if country and entry.entity.country and normalize_name(country) == normalize_name(
                entry.entity.country
            ):
                context_boost += 4.0
            history_boost = min(
                4.0,
                math.log1p(max(0, entry.entity.successful_resolution_count)) * 1.4,
            )
            source_confidence = max(0.0, entry.confidence - 0.7) * 8.0
            final_score = min(100.0, similarity + context_boost + history_boost + source_confidence)
            candidates.append(
                NameCandidate(
                    entity=entry.entity,
                    matched_alias=entry.alias,
                    string_score=similarity,
                    final_score=final_score,
                    source=entry.source,
                )
            )
        best_by_entity: dict[str, NameCandidate] = {}
        for candidate in candidates:
            key = normalize_name(candidate.entity.canonical_name)
            current = best_by_entity.get(key)
            if current is None or candidate.final_score > current.final_score:
                best_by_entity[key] = candidate
        return sorted(
            best_by_entity.values(), key=lambda item: item.final_score, reverse=True
        )[: max(1, limit)]

    def resolve_name(
        self,
        text: str,
        *,
        entity_type: str | None = None,
        country: str | None = None,
        allow_wikimedia: bool = False,
    ) -> NameCandidate | None:
        normalized = normalize_name(text)
        if not normalized:
            return None
        local = self.find_name_candidates(
            text, entity_type=entity_type, country=country, limit=3
        )
        accepted = _accepted_candidate(text, local)
        if accepted is not None:
            if accepted.source == "local_entity_cache" and self.store:
                self.store.record_success(accepted.entity.canonical_name)
                if (
                    allow_wikimedia
                    and self.wikimedia_client is not None
                    and self.store.metadata_stale(accepted.entity.canonical_name)
                ):
                    refreshed = self.wikimedia_client.lookup(
                        accepted.entity.canonical_name
                    )
                    if refreshed is not None:
                        self.store.upsert(
                            refreshed,
                            metadata_ttl_days=self.metadata_ttl_days,
                        )
                self._local_entries = None
            return accepted
        if not allow_wikimedia or self.wikimedia_client is None or _is_short_name(text):
            return None
        learned = self.wikimedia_client.lookup(text)
        if learned is None:
            return None
        if self.store and self.store.upsert(
            learned,
            metadata_ttl_days=self.metadata_ttl_days,
        ):
            self._local_entries = None
        return NameCandidate(
            entity=learned,
            matched_alias=learned.canonical_name,
            string_score=learned.confidence * 100.0,
            final_score=learned.confidence * 100.0,
            source="wikidata",
        )

    def normalize_query(
        self,
        text: str,
        *,
        entity_type: str | None = None,
        country: str | None = None,
        allow_wikimedia: bool = False,
    ) -> QueryNormalization:
        original = str(text or "")
        replacements: list[tuple[int, int, NameCandidate]] = []
        tokens = list(TOKEN_RE.finditer(original))

        # Resolve the longest plausible proper-name phrases first.
        for width in range(min(4, len(tokens)), 1, -1):
            for index in range(0, len(tokens) - width + 1):
                group = tokens[index : index + width]
                if any(_overlaps(item.start(), item.end(), replacements) for item in group):
                    continue
                phrase = original[group[0].start() : group[-1].end()]
                if not _plausible_name_phrase(phrase):
                    continue
                candidate = self.resolve_name(
                    phrase, entity_type=entity_type, country=country
                )
                if (
                    candidate
                    and candidate.string_score < 99.9
                    and normalize_name(phrase)
                    != normalize_name(candidate.entity.canonical_name)
                ):
                    replacements.append((group[0].start(), group[-1].end(), candidate))

        for token in tokens:
            if _overlaps(token.start(), token.end(), replacements):
                continue
            value = token.group(0)
            if value.casefold() in QUERY_WORDS | RELATIONSHIP_WORDS or value.isdigit():
                continue
            candidate = self.resolve_name(
                value, entity_type=entity_type, country=country
            )
            if (
                candidate
                and candidate.string_score < 99.9
                and normalize_name(value) != normalize_name(candidate.entity.canonical_name)
            ):
                replacements.append((token.start(), token.end(), candidate))

        normalized = original
        corrections: list[QueryCorrection] = []
        resolved: list[EntityRecord] = []
        for start, end, candidate in sorted(replacements, key=lambda item: item[0], reverse=True):
            raw = original[start:end]
            canonical = candidate.entity.canonical_name
            normalized = f"{normalized[:start]}{canonical}{normalized[end:]}"
            corrections.append(
                QueryCorrection(
                    original=raw,
                    corrected=canonical,
                    kind=candidate.entity.entity_type or "entity",
                    confidence=candidate.final_score / 100.0,
                    source=candidate.source,
                )
            )
            resolved.append(candidate.entity)

        if allow_wikimedia and not corrections:
            for phrase, start, end in _wikimedia_lookup_phrases(original):
                candidate = self.resolve_name(
                    phrase,
                    entity_type=entity_type,
                    country=country,
                    allow_wikimedia=True,
                )
                if candidate is None:
                    continue
                resolved.append(candidate.entity)
                if normalize_name(phrase) != normalize_name(candidate.entity.canonical_name):
                    normalized = (
                        f"{normalized[:start]}{candidate.entity.canonical_name}{normalized[end:]}"
                    )
                    corrections.append(
                        QueryCorrection(
                            original=phrase,
                            corrected=candidate.entity.canonical_name,
                            kind=candidate.entity.entity_type or "entity",
                            confidence=candidate.final_score / 100.0,
                            source="wikidata",
                        )
                    )
                break

        return QueryNormalization(
            original_text=original,
            normalized_text=normalized,
            corrections=tuple(reversed(corrections)),
            resolved_entities=tuple(_dedupe_entities(resolved)),
        )

    def learn_entity(self, entity: EntityRecord) -> bool:
        if not self.store or entity.source not in TRUSTED_ENTITY_SOURCES:
            return False
        learned = self.store.upsert(
            entity,
            metadata_ttl_days=self.metadata_ttl_days,
        )
        if learned:
            self._local_entries = None
        return learned

    def learn_from_search_metadata(self, metadata: dict[str, Any]) -> EntityRecord | None:
        ambiguity = metadata.get("ambiguity")
        if isinstance(ambiguity, dict) and ambiguity.get("is_ambiguous"):
            return None
        raw_candidates = metadata.get("entity_candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            return None
        ranked = [item for item in raw_candidates if isinstance(item, dict)]
        ranked.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        if not ranked:
            return None
        top_score = float(ranked[0].get("score") or 0.0)
        runner_up = float(ranked[1].get("score") or 0.0) if len(ranked) > 1 else 0.0
        if top_score < 0.68 or (top_score < 0.88 and top_score - runner_up < 0.08):
            return None
        item = ranked[0]
        canonical = str(item.get("canonical_name") or "").strip()
        if not canonical:
            return None
        domains = [str(value).strip() for value in item.get("domains") or [] if str(value).strip()]
        entity = EntityRecord(
            canonical_name=canonical,
            entity_type=str(item.get("entity_type") or "") or None,
            aliases=tuple(
                str(value).strip()
                for value in item.get("aliases") or []
                if str(value).strip()
            ),
            source="verified_search",
            country=str(item.get("country") or "") or None,
            description=str(item.get("description") or "") or None,
            domain=domains[0] if domains else None,
            confidence=min(0.96, top_score),
        )
        return entity if self.learn_entity(entity) else None


def structured_entity_profile(text: str, domain: str = "") -> dict[str, Any] | None:
    """Return a known structured profile found in trusted result text/domain."""
    lowered = normalize_name(text)
    normalized_domain = str(domain or "").lower().removeprefix("www.")
    matches: list[StructuredEntity] = []
    for item in STRUCTURED_ENTITIES:
        names = [item.canonical_name, *item.aliases]
        canonical = normalize_name(item.canonical_name)
        canonical_present = bool(canonical) and f" {canonical} " in f" {lowered} "
        domain_present = bool(item.domain) and (
            normalized_domain == item.domain
            or normalized_domain.endswith(f".{item.domain}")
        )
        if canonical_present or domain_present:
            matches.append(item)
        elif any(
            len(normalize_name(alias)) > 4
            and f" {normalize_name(alias)} " in f" {lowered} "
            for alias in names
        ):
            matches.append(item)
    if not matches:
        return None
    item = max(matches, key=lambda value: len(normalize_name(value.canonical_name)))
    return {
        "canonical_name": item.canonical_name,
        "aliases": list(_dedupe_names([item.canonical_name, *item.aliases])),
        "entity_type": item.entity_type,
        "description": item.description,
        "country": item.country,
        "region": None,
        "expansions": [item.canonical_name] if item.aliases else [],
    }


def structured_domains_for_text(text: str) -> tuple[str, ...]:
    normalized = normalize_name(text)
    domains: list[str] = []
    for item in STRUCTURED_ENTITIES:
        if not item.domain:
            continue
        names = [item.canonical_name]
        if any(
            f" {normalize_name(name)} " in f" {normalized} "
            for name in names
            if normalize_name(name)
        ) and item.domain not in domains:
            domains.append(item.domain)
    return tuple(domains)


def _record_from_row(row: sqlite3.Row, aliases: tuple[str, ...] = ()) -> EntityRecord:
    return EntityRecord(
        canonical_name=str(row["canonical_name"]),
        entity_type=str(row["entity_type"]) if row["entity_type"] else None,
        aliases=aliases,
        source=str(row["source"]),
        source_id=str(row["source_id"]) if row["source_id"] else None,
        country=str(row["country"]) if row["country"] else None,
        language=str(row["language"]) if row["language"] else None,
        description=str(row["description"]) if row["description"] else None,
        domain=str(row["domain"]) if row["domain"] else None,
        confidence=float(row["confidence"]),
        successful_resolution_count=int(row["successful_resolution_count"]),
        last_seen_at=str(row["last_seen_at"]),
        updated_at=str(row["updated_at"]),
    )


def _string_similarity(left: str, right: str) -> float:
    left_normalized = normalize_name(left)
    right_normalized = normalize_name(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 100.0
    scorer = fuzz.WRatio if " " in left_normalized or " " in right_normalized else fuzz.ratio
    return float(scorer(left_normalized, right_normalized))


def _accepted_candidate(text: str, candidates: list[NameCandidate]) -> NameCandidate | None:
    if not candidates:
        return None
    best = candidates[0]
    normalized = normalize_name(text)
    alias_normalized = normalize_name(best.matched_alias)
    if normalized == alias_normalized:
        exact_entities = {
            normalize_name(candidate.entity.canonical_name)
            for candidate in candidates
            if normalize_name(candidate.matched_alias) == normalized
        }
        if len(exact_entities) > 1:
            return None
        return best
    compact = normalized.replace(" ", "")
    if len(compact) <= 4 or compact.isupper():
        return None
    if len(normalized.split()) != len(alias_normalized.split()):
        return None
    edit_distance = Levenshtein.distance(normalized, alias_normalized)
    entity_type = best.entity.entity_type or ""
    threshold = 82.0 if entity_type == "country" else 87.0
    if len(compact) <= 5:
        threshold = max(threshold, 91.0)
    camel_or_handle = (
        text.startswith("@")
        or bool(re.search(r"[a-z][A-Z]", text))
        or "_" in text
    )
    trusted_single_edit = (
        edit_distance == 1
        and best.string_score >= 84.0
        and best.entity.confidence >= 0.85
    )
    if trusted_single_edit:
        threshold = min(threshold, 84.0)
    if camel_or_handle and not (
        trusted_single_edit or (best.string_score >= 90.0 and edit_distance <= 1)
    ):
        return None
    if best.string_score < threshold:
        return None
    if len(candidates) > 1:
        margin = best.final_score - candidates[1].final_score
        if margin < (3.0 if entity_type == "country" else 5.0):
            return None
    max_distance = max(1, round(len(normalized) * 0.28))
    if edit_distance > max_distance:
        return None
    return best


def _is_short_name(text: str) -> bool:
    compact = normalize_name(text).replace(" ", "")
    return len(compact) <= 4


def _plausible_name_phrase(text: str) -> bool:
    words = TOKEN_RE.findall(text)
    useful = [word for word in words if word.casefold() not in QUERY_WORDS]
    if len(useful) < 2:
        return False
    return any(
        word.isupper()
        or word[:1].isupper()
        or bool(re.search(r"[a-z][A-Z]", word))
        for word in useful
    )


def _wikimedia_lookup_phrases(text: str) -> list[tuple[str, int, int]]:
    tokens = list(TOKEN_RE.finditer(text))
    phrases: list[tuple[str, int, int]] = []
    current: list[re.Match[str]] = []

    def flush() -> None:
        if not current:
            return
        phrase = text[current[0].start() : current[-1].end()]
        compact = normalize_name(phrase).replace(" ", "")
        if len(compact) >= 5 and _plausible_name_phrase(phrase):
            phrases.append((phrase, current[0].start(), current[-1].end()))
        current.clear()

    for token in tokens:
        value = token.group(0)
        if value.casefold() in QUERY_WORDS | RELATIONSHIP_WORDS:
            flush()
            continue
        looks_named = (
            value.isupper()
            or value[:1].isupper()
            or value.startswith("@")
            or bool(re.search(r"[a-z][A-Z]", value))
        )
        if looks_named:
            current.append(token)
        else:
            flush()
    flush()
    return sorted(phrases, key=lambda item: (-(item[2] - item[1]), item[1]))[:2]


def _metadata_from_description(description: str) -> tuple[str | None, str | None]:
    lowered = description.lower()
    type_patterns = (
        ("university", r"\buniversity\b"),
        ("school", r"\bschool\b|educational institution"),
        ("software_library", r"software library|programming library"),
        ("programming_language", r"programming language"),
        ("operating_system", r"operating system|linux distribution"),
        ("ai_model", r"artificial intelligence model|language model|ai model"),
        ("video_game", r"video game"),
        ("software", r"\bsoftware\b|window manager|desktop environment"),
        ("organization", r"company|organization|organisation|business"),
        ("person", r"human|person|researcher|politician|actor|singer"),
        ("place", r"city|country|province|region|district|commune"),
    )
    entity_type = next(
        (label for label, pattern in type_patterns if re.search(pattern, lowered)), None
    )
    country = None
    for item in STRUCTURED_ENTITIES:
        if item.entity_type != "country":
            continue
        if any(
            re.search(rf"\b{re.escape(normalize_name(name))}\b", normalize_name(description))
            for name in [item.canonical_name, *item.aliases]
        ):
            country = item.canonical_name
            break
    return entity_type, country


def _overlaps(start: int, end: int, replacements: list[tuple[int, int, NameCandidate]]) -> bool:
    return any(
        start < existing_end and end > existing_start
        for existing_start, existing_end, _ in replacements
    )


def _dedupe_names(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").split())
        normalized = normalize_name(cleaned)
        if not cleaned or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(cleaned)
    return result


def _dedupe_entities(values: Iterable[EntityRecord]) -> list[EntityRecord]:
    seen: set[str] = set()
    result: list[EntityRecord] = []
    for value in values:
        key = normalize_name(value.canonical_name)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
