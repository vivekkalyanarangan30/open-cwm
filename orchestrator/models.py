from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TestConfig:
    """Configuration describing how tests should be executed for a repository."""

    runner: str = "pytest"
    markers_exclude: List[str] = field(default_factory=list)
    timeout_s: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestConfig":
        return cls(
            runner=data.get("runner", "pytest"),
            markers_exclude=list(data.get("markers_exclude", [])),
            timeout_s=data.get("timeout_s"),
        )


@dataclass
class RepoSpec:
    """Repository metadata sourced from the repo catalog."""

    id: str
    url: str
    commit: str
    license: str
    language: str
    tests: TestConfig = field(default_factory=TestConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepoSpec":
        tests = TestConfig.from_dict(data.get("tests", {}))
        return cls(
            id=data["id"],
            url=data["url"],
            commit=data.get("commit", "main"),
            license=data.get("license", ""),
            language=data.get("language", "python"),
            tests=tests,
        )


@dataclass
class StageResult:
    """Summary emitted by a pipeline stage."""

    name: str
    status: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"stage": self.name, "status": self.status, "details": self.details}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StageResult":
        return cls(
            name=data.get("stage", ""),
            status=data.get("status", "unknown"),
            details=data.get("details", {}),
        )
