"""One fenced session lease keeper for embedded and headless chat turns."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


class SessionLeaseKeeper:
    """Renew on a dedicated connection and stop effects when ownership is lost."""

    def __init__(
        self,
        memory: Any,
        session_id: str,
        client_id: str,
        turn_id: str,
        *,
        interval: float = 5.0,
        ttl: float = 60.0,
        outage_grace: float = 12.0,
        on_lost: Callable[[], None] | None = None,
        fence: int | None = None,
    ) -> None:
        self.memory = memory
        self.session_id = session_id
        self.client_id = client_id
        self.turn_id = turn_id
        self.interval = max(0.1, float(interval))
        self.ttl = max(self.interval * 2, float(ttl))
        self.outage_grace = max(self.interval, float(outage_grace))
        self.on_lost = on_lost
        self.fence = fence
        self.lost = threading.Event()
        self._stop = threading.Event()
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="klaude-session-lease"
        )

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self._stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=6.0)

    def _run(self) -> None:
        connection = self.memory
        open_connection = getattr(self.memory, "open_session_io", None)
        if callable(open_connection):
            try:
                connection = open_connection()
            except Exception:
                connection = self.memory
        try:
            last_renewed = time.monotonic()
            while not self._stop.wait(self.interval):
                try:
                    renewed = connection.renew_session_lease(
                        self.session_id,
                        self.client_id,
                        self.turn_id,
                        ttl=self.ttl,
                        **({"fence": self.fence} if self.fence is not None else {}),
                    )
                except Exception:
                    renewed = None
                if renewed:
                    last_renewed = time.monotonic()
                    continue
                if (renewed is None
                        and time.monotonic() - last_renewed < self.outage_grace):
                    continue
                self.lost.set()
                if self.on_lost is not None:
                    try:
                        self.on_lost()
                    except Exception:
                        pass
                return
        finally:
            if connection is not self.memory:
                try:
                    connection.db.close()
                except Exception:
                    pass
