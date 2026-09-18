"""User-level project registry; it stores paths and enabled state only."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class ProjectRegistry:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser()

    def _read(self) -> list[dict[str, object]]:
        if not self.path.is_file():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []

    def _write(self, entries: list[dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(entries, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def register(self, repo: Path) -> None:
        normalized = str(Path(repo).expanduser().resolve())
        entries = self._read()
        for entry in entries:
            if entry.get("repo") == normalized:
                entry["enabled"] = True
                self._write(entries)
                return
        entries.append({"repo": normalized, "enabled": True})
        self._write(entries)

    def unregister(self, repo: Path) -> None:
        normalized = str(Path(repo).expanduser().resolve())
        entries = [entry for entry in self._read() if entry.get("repo") != normalized]
        self._write(entries)

    def enabled_projects(self) -> tuple[Path, ...]:
        return tuple(Path(entry["repo"]) for entry in self._read() if entry.get("enabled") is True)
