"""Bounded storage metadata inspection, without reading file contents or following links."""

import os
import shutil
import stat
import time


def storage_usage() -> str:
    """Inspect fixed OS categories and the current account's home, never other homes."""
    total, used, free = shutil.disk_usage("/")
    lines = [f"Root filesystem: total={total} used={used} free={free} bytes"]
    home = os.path.expanduser("~")
    device = os.stat("/").st_dev
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    for path in ("/usr", "/var", "/opt", "/snap", "/tmp", home):
        # Give each category a budget so a large /usr cannot starve home or /var.
        deadline = time.monotonic() + 0.5
        remaining = 8_000
        allocated = 0
        skipped = 0
        stack: list[int] = []
        seen: set[tuple[int, int]] = set()
        try:
            stack.append(os.open(path, flags))
            while stack and remaining > 0 and time.monotonic() < deadline:
                fd = stack.pop()
                try:
                    if os.fstat(fd).st_dev != device:
                        skipped += 1
                        continue
                    with os.scandir(fd) as entries:
                        for entry in entries:
                            if remaining <= 0 or time.monotonic() >= deadline:
                                skipped += 1
                                break
                            remaining -= 1
                            try:
                                info = entry.stat(follow_symlinks=False)
                                key = (info.st_dev, info.st_ino)
                                if info.st_dev != device or key in seen:
                                    continue
                                seen.add(key)
                                allocated += info.st_blocks * 512
                                if stat.S_ISDIR(info.st_mode):
                                    # Bound open directory descriptors as well as traversal work.
                                    if len(stack) < 128:
                                        stack.append(os.open(entry.name, flags, dir_fd=fd))
                                    else:
                                        skipped += 1
                            except OSError:
                                skipped += 1
                finally:
                    os.close(fd)
        except OSError:
            skipped += 1
        finally:
            skipped += len(stack)
            for fd in stack:
                os.close(fd)
        partial = skipped > 0 or remaining <= 0 or time.monotonic() >= deadline
        label = "current account home" if path == home else path
        lines.append(
            f"{label}: {allocated} allocated bytes; "
            f"{'partial lower bound' if partial else 'scanned'}"
        )
    lines.append(
        "Metadata only; no file contents. Other users' homes, symlinks and other "
        "filesystems excluded. Totals may overlap (for example a home under /tmp). "
        "Unscanned data is unknown, not zero. No cleanup performed."
    )
    return "\n".join(lines)
