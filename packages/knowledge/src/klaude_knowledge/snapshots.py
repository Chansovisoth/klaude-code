"""Snapshot helpers for replaceable user-data trees."""

from __future__ import annotations

import shutil
import time
from pathlib import Path


def utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())


def snapshot_current(root: Path, current_dir: Path) -> str:
    if not current_dir.exists():
        return ""
    snapshots_dir = root / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_timestamp()
    target = snapshots_dir / stamp
    suffix = 2
    while target.exists():
        target = snapshots_dir / f"{stamp}-{suffix}"
        suffix += 1
    shutil.move(str(current_dir), target)
    return target.name


def prune_snapshots(root: Path, keep: int) -> list[str]:
    snapshots_dir = root / "snapshots"
    if keep < 0 or not snapshots_dir.exists():
        return []
    snapshots = sorted(p for p in snapshots_dir.iterdir() if p.is_dir())
    removed = []
    for snapshot in snapshots[:-keep] if keep else snapshots:
        shutil.rmtree(snapshot)
        removed.append(snapshot.name)
    return removed
