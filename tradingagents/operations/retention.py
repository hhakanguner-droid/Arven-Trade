"""Bounded file-retention utilities for ARVEN Trade runtime artifacts."""

from __future__ import annotations

import time
from pathlib import Path


def prune_files(
    root: str | Path,
    *,
    retention_days: int = 0,
    max_files: int = 0,
    now: float | None = None,
) -> list[Path]:
    """Delete old/excess regular files beneath root and return deleted paths.

    A non-positive retention_days or max_files disables that respective rule.
    Symlinks are never followed or deleted.
    """
    base = Path(root).expanduser()
    if not base.exists():
        return []
    resolved_base = base.resolve()
    current = time.time() if now is None else float(now)
    candidates: list[tuple[float, Path]] = []
    for path in base.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(resolved_base):
                continue
            mtime = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, path))

    to_delete: set[Path] = set()
    if retention_days > 0:
        cutoff = current - int(retention_days) * 86400
        to_delete.update(path for mtime, path in candidates if mtime < cutoff)

    survivors = [(mtime, path) for mtime, path in candidates if path not in to_delete]
    if max_files > 0 and len(survivors) > int(max_files):
        survivors.sort(key=lambda item: item[0], reverse=True)
        to_delete.update(path for _mtime, path in survivors[int(max_files) :])

    deleted: list[Path] = []
    for path in sorted(to_delete, key=str):
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        deleted.append(path)
    return deleted
