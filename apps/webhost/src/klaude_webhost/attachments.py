"""Private per-client attachment selection; accepted turns own immutable bytes."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from klaude_application.chat_attachments import ChatAttachment, ChatAttachmentInput


@dataclass(frozen=True)
class Selection:
    owner: str
    client: str
    session: str
    expires: float
    attachment: ChatAttachment = field(repr=False)


class ChatAttachments:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, Selection] = {}
        self.preparing = threading.BoundedSemaphore(2)

    def add(
        self, owner: str, client: str, session: str, attachment: ChatAttachment,
    ) -> dict[str, Any]:
        with self._lock:
            self._items = {key: item for key, item in self._items.items()
                           if item.expires > time.monotonic()}
            if (len(self._items) >= 32 or sum(len(item.attachment.data)
                    for item in self._items.values()) + len(attachment.data) > 64 * 1024 * 1024):
                raise ValueError("Attachment storage is full; remove an attachment and retry")
            identity = secrets.token_hex(16)
            self._items[identity] = Selection(owner, client, session, time.monotonic() + 1800,
                                               attachment)
            return {"id": identity, **attachment.public()}

    def capture(self, owner: str, client: str, session: str, ids: object) -> ChatAttachmentInput:
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 4
                or any(not isinstance(identity, str) for identity in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError("Choose up to four distinct attachments")
        with self._lock:
            files = []
            for identity in ids:
                item = self._items.get(identity)
                if (item is None or (item.owner, item.client, item.session) !=
                        (owner, client, session) or item.expires <= time.monotonic()):
                    raise ValueError(
                        "Attachment expired or belongs to another chat; choose it again"
                    )
                files.append(item.attachment)
            return ChatAttachmentInput(tuple(files))

    def discard(self, owner: str, client: str, identity: str) -> None:
        with self._lock:
            item = self._items.get(identity)
            if item and (item.owner, item.client) == (owner, client):
                self._items.pop(identity)

    def revoke(self, owner: str | None = None) -> None:
        with self._lock:
            self._items = {key: item for key, item in self._items.items()
                           if owner is not None and item.owner != owner}
