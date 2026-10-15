"""Feed bounded private subprocess input independently of cancellable output polling."""

from __future__ import annotations

import subprocess
import threading


class PrivateProcessInput:
    def __init__(self, process: subprocess.Popen[bytes], payload: bytes):
        pipe = process.stdin
        if pipe is None:
            raise ValueError("Private worker input pipe is unavailable")
        self.process, self.pipe = process, pipe
        # communicate(None) must not close a pipe still being written. Repeated
        # communicate(None) after a short timeout otherwise stops registering
        # stdin for writing and deadlocks payloads larger than the pipe buffer.
        process.stdin = None

        def write() -> None:
            try:
                with pipe:
                    view = memoryview(payload)
                    offset = 0
                    while offset < len(view):
                        offset += pipe.write(view[offset : offset + 65536])
                    pipe.flush()
            except (BrokenPipeError, OSError):
                pass  # The owned parent reaps failures/cancellation and bounds output.

        self.thread = threading.Thread(
            target=write, name="klaude-private-worker-input", daemon=True
        )
        self.thread.start()

    def close(self) -> None:
        # Call after communicate completion or owned process-group cleanup.
        self.thread.join(timeout=0.5)
        if not self.thread.is_alive():
            self.process.stdin = self.pipe
