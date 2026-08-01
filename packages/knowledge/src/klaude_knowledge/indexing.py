"""Shared atomic indexing service for learned pages, docs sources, and skills."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from klaude_core import Config, Ollama

from .chunker import chunk_markdown
from .store import KnowledgeStore


@dataclass(frozen=True)
class IndexDocument:
    source: str
    text: str
    title: str = ""


@dataclass(frozen=True)
class IndexResult:
    library: str
    owner: str
    operation_id: str
    version_ids: dict[str, str]
    chunk_count: int


def text_checksum(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class KnowledgeIndexer:
    def __init__(self, cfg: Config, store: KnowledgeStore, ollama: Ollama):
        self.cfg = cfg
        self.store = store
        self.ollama = ollama

    def active_source_checksum(self, library: str, owner: str, source: str) -> str | None:
        return self.store.active_source_checksum(library, owner, source)

    def replace_source_atomic(
        self,
        library: str,
        owner: str,
        source: str,
        text: str,
        *,
        title: str = "",
    ) -> IndexResult:
        return self.replace_owner_snapshot_atomic(
            library,
            owner,
            [IndexDocument(source=source, text=text, title=title)],
        )

    def replace_owner_snapshot_atomic(
        self,
        library: str,
        owner: str,
        documents: list[IndexDocument],
        *,
        operation_id: str = "",
    ) -> IndexResult:
        if not documents:
            raise ValueError("cannot index an empty owner snapshot")
        operation_id = operation_id or str(uuid4())
        incoming_checksums = {doc.source: text_checksum(doc.text) for doc in documents}
        if self.store.active_owner_checksums(library, owner) == incoming_checksums:
            return IndexResult(
                library=library,
                owner=owner,
                operation_id=operation_id,
                version_ids={},
                chunk_count=0,
            )
        prepared = []
        all_chunk_texts: list[str] = []
        for doc in documents:
            checksum = incoming_checksums[doc.source]
            chunks = chunk_markdown(doc.text, title=doc.title)
            sections = [chunk.section for chunk in chunks]
            texts = [chunk.text for chunk in chunks]
            if not texts:
                continue
            prepared.append(
                {
                    "source": doc.source,
                    "checksum": checksum,
                    "texts": texts,
                    "sections": sections,
                }
            )
            all_chunk_texts.extend(texts)
        if not prepared:
            raise ValueError("no indexable chunks were produced")

        vectors = self.ollama.embed(self.cfg.models["embed"], all_chunk_texts)
        if len(vectors) != len(all_chunk_texts):
            raise RuntimeError("embedding count mismatch")

        staged: dict[str, str] = {}
        cursor = 0
        for doc in prepared:
            count = len(doc["texts"])
            doc_vectors = vectors[cursor : cursor + count]
            cursor += count
            staged[doc["source"]] = self.store.stage_version(
                library,
                owner,
                doc["source"],
                doc["texts"],
                doc_vectors,
                doc["checksum"],
                sections=doc["sections"],
                operation_id=operation_id,
            )

        self.store.activate_versions(library, owner, staged)
        try:
            self.store.garbage_collect_obsolete_versions(library)
        except Exception:
            pass
        return IndexResult(
            library=library,
            owner=owner,
            operation_id=operation_id,
            version_ids=staged,
            chunk_count=len(all_chunk_texts),
        )

    def recover_incomplete_operations(self) -> int:
        return self.store.recover_incomplete_operations()

    def garbage_collect_obsolete_versions(self, library: str | None = None) -> int:
        return self.store.garbage_collect_obsolete_versions(library)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
