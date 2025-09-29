from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from .models import RepoSpec


class CatalogError(RuntimeError):
    """Raised when the repository catalog cannot be parsed."""


@dataclass
class RepoCatalog:
    """Lightweight loader for the repository catalog file."""

    path: Path
    _cache: Optional[Dict[str, RepoSpec]] = None

    @classmethod
    def from_file(cls, path: str | Path) -> "RepoCatalog":
        return cls(path=Path(path))

    def _load(self) -> Dict[str, RepoSpec]:
        if self._cache is not None:
            return self._cache

        raw_text = self.path.read_text()
        try:
            raw_data = json.loads(raw_text)
        except json.JSONDecodeError:
            try:
                import yaml  # type: ignore
            except ImportError as exc:  # pragma: no cover - fallback path
                raise CatalogError("PyYAML is required to parse non-JSON YAML catalogs") from exc
            raw_data = yaml.safe_load(raw_text)  # type: ignore[assignment]

        if not isinstance(raw_data, dict) or "repos" not in raw_data:
            raise CatalogError("Catalog must contain a top-level 'repos' list")

        repo_specs = {
            entry["id"]: RepoSpec.from_dict(entry)
            for entry in raw_data.get("repos", [])
        }
        self._cache = repo_specs
        return repo_specs

    def iter_repos(self) -> Iterable[RepoSpec]:
        return self._load().values()

    def get(self, repo_id: str) -> RepoSpec:
        try:
            return self._load()[repo_id]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise CatalogError(f"Unknown repo id: {repo_id}") from exc

    def __len__(self) -> int:
        return len(self._load())

    def __contains__(self, repo_id: str) -> bool:
        return repo_id in self._load()
