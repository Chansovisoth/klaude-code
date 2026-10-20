"""Bounded private image derivatives for the authenticated Library surface."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from klaude_core.image_preparation import prepare_image
from klaude_core.library_artifacts import ArtifactStore


class ImageBusy(RuntimeError):
    pass


class LibraryImages:
    """Cache decoded pixels only, by exact artifact revision/hash and output size.

    No URL accepts a path. Originals stay in SQLite, bounded blob reads verify
    their checksums, and all decoding uses the existing limited
    subprocess. At most two decoders, 128 entries and 32 MiB of cached output.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._workers = threading.BoundedSemaphore(2)
        self._cache: OrderedDict[tuple, tuple[float, str, bytes]] = OrderedDict()
        self._bytes = 0

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._bytes = 0

    def _cached(self, key: tuple) -> tuple[str, bytes] | None:
        with self._lock:
            for expired in [k for k, value in self._cache.items()
                            if value[0] <= time.monotonic()]:
                self._bytes -= len(self._cache.pop(expired)[2])
            value = self._cache.get(key)
            if value:
                self._cache.move_to_end(key)
                return value[1], value[2]
        return None

    def read(
        self, store: ArtifactStore, identity: str, revision: int, size: str,
        *, cancelled: Callable[[], bool],
    ) -> tuple[str, bytes]:
        if size not in {"thumbnail", "preview"} or type(revision) is not int or revision < 1:
            raise ValueError("Invalid image request")
        item = store.get(identity)
        if (item["revision"] != revision
                or item["mime"] not in {"image/png", "image/jpeg", "image/webp", "image/gif"}
                or item["size"] > 32 * 1024 * 1024):
            raise ValueError("Image changed or cannot be previewed")
        key = (str(store.root), identity, revision, item["sha256"], size)
        if cancelled():
            raise ValueError("Image request ended")
        cached = self._cached(key)
        if cached:
            return cached
        if not self._workers.acquire(timeout=2):
            raise ImageBusy("Image previews busy; try again")
        try:
            cached = self._cached(key)
            if cached:
                return cached
            with store.database() as db:
                db.execute("BEGIN")
                row = db.execute(
                    "SELECT rowid,revision,size,sha256 FROM artifacts WHERE id=?", (identity,),
                ).fetchone()
                if row is None or row["revision"] != revision:
                    raise ValueError("Image changed; reload")
                with db.blobopen("artifacts", "content", row["rowid"], readonly=True) as blob:
                    if len(blob) != row["size"] or len(blob) > 32 * 1024 * 1024:
                        raise ValueError("Image exceeds its source limit")
                    data = blob.read(32 * 1024 * 1024 + 1)
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    raise ValueError("Stored content checksum failed")
            metadata, output = prepare_image(
                data, thumbnail=size == "thumbnail", thumbnail_size=320,
                detail="detailed", frame=0, cancelled=cancelled,
            )
            # A concurrent tag/archive/delete or logout cannot publish an obsolete result.
            current = store.get(identity)
            if (cancelled() or current["revision"] != revision
                    or current["sha256"] != item["sha256"]):
                raise ValueError("Image changed; reload")
            with self._lock:
                prior = self._cache.pop(key, None)
                self._bytes -= len(prior[2]) if prior else 0
                self._cache[key] = (time.monotonic() + 900, metadata["mime"], output)
                self._bytes += len(output)
                while len(self._cache) > 128 or self._bytes > 32 * 1024 * 1024:
                    self._bytes -= len(self._cache.popitem(last=False)[1][2])
            return metadata["mime"], output
        finally:
            self._workers.release()
