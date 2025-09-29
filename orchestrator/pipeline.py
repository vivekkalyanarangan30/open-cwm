from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

import datetime as _dt

from .models import RepoSpec, StageResult
from .utils import dump_json, ensure_directory, run_command


class Stage(Enum):
    DISCOVER = auto()
    PLAN = auto()
    BUILD = auto()
    TEST = auto()
    PACKAGE = auto()
    PUBLISH = auto()

    @classmethod
    def ordered(cls) -> Iterable["Stage"]:
        return (
            cls.DISCOVER,
            cls.PLAN,
            cls.BUILD,
            cls.TEST,
            cls.PACKAGE,
            cls.PUBLISH,
        )


@dataclass
class PipelineContext:
    repo: RepoSpec
    workspace: Path

    def __post_init__(self) -> None:
        self.workspace = Path(self.workspace)
        ensure_directory(self.workspace)

    @property
    def repo_checkout_path(self) -> Path:
        return ensure_directory(self.workspace / "repos") / self.repo.id

    @property
    def state_dir(self) -> Path:
        return ensure_directory(self.workspace / "state" / self.repo.id)

    @property
    def artifacts_dir(self) -> Path:
        return ensure_directory(self.workspace / "artifacts" / self.repo.id)

    @property
    def logs_dir(self) -> Path:
        return ensure_directory(self.workspace / "logs" / self.repo.id)

    def stage_output(self, stage: Stage) -> Path:
        return self.state_dir / f"{stage.name.lower()}.json"

    def artifact_path(self, relative: str) -> Path:
        return self.artifacts_dir / relative

    def ensure_checkout(self) -> bool:
        repo_dir = self.repo_checkout_path
        if (repo_dir / ".git").exists():
            return False
        ensure_directory(repo_dir.parent)
        run_command([
            "git",
            "clone",
            self.repo.url,
            str(repo_dir),
        ])
        if self.repo.commit:
            run_command(["git", "checkout", self.repo.commit], cwd=repo_dir)
        return True


StageHandler = Callable[[PipelineContext], StageResult]


def _detect_toolchain(repo_dir: Path) -> Mapping[str, object]:
    pyproject_path = repo_dir / "pyproject.toml"
    poetry = False
    hatch = False
    build_backend: Optional[str] = None
    if pyproject_path.exists():
        try:
            data = pyproject_path.read_text(encoding="utf-8")
            pyproject = tomllib.loads(data)  # type: ignore[name-defined]
        except Exception:  # pragma: no cover - permissive fallback
            pyproject = {}
        build_backend = (
            pyproject.get("build-system", {}).get("build-backend")
            if isinstance(pyproject, dict)
            else None
        )
        tool_section = pyproject.get("tool", {}) if isinstance(pyproject, dict) else {}
        poetry = isinstance(tool_section, dict) and "poetry" in tool_section
        hatch = isinstance(tool_section, dict) and "hatch" in tool_section

    requirements = (repo_dir / "requirements.txt").exists()
    environment = (repo_dir / "environment.yml").exists()
    workflows_dir = repo_dir / ".github" / "workflows"
    workflows: List[str] = []
    if workflows_dir.exists():
        workflows = sorted(str(p.relative_to(repo_dir)) for p in workflows_dir.glob("*.yml"))
        workflows += sorted(str(p.relative_to(repo_dir)) for p in workflows_dir.glob("*.yaml"))

    return {
        "pyproject": pyproject_path.exists(),
        "poetry": poetry,
        "hatch": hatch,
        "build_backend": build_backend,
        "requirements": requirements,
        "environment_yml": environment,
        "ci_workflows": workflows,
    }


try:  # pragma: no cover - tomllib is stdlib from 3.11 onwards
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for 3.10
    import tomli as tomllib  # type: ignore


def _load_pyproject(repo_dir: Path) -> Mapping[str, object]:
    pyproject_path = repo_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return {}
    try:
        return tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover - permissive fallback for malformed files
        return {}


def _infer_project_extras(repo_dir: Path) -> List[str]:
    data = _load_pyproject(repo_dir)
    extras: List[str] = []

    optional = data.get("project", {}).get("optional-dependencies", {})
    if isinstance(optional, dict):
        for candidate in ("dev", "test", "tests", "ci"):
            if candidate in optional:
                extras.append(candidate)

    tool_section = data.get("tool", {})
    if isinstance(tool_section, dict):
        poetry_group = tool_section.get("poetry", {}).get("group", {}) if isinstance(tool_section.get("poetry"), dict) else {}
        if isinstance(poetry_group, dict):
            for candidate in ("dev", "test", "tests", "ci"):
                group_cfg = poetry_group.get(candidate)
                if isinstance(group_cfg, dict) and group_cfg.get("dependencies"):
                    extras.append(candidate)

    return sorted(set(extras))


def _build_install_commands(repo_dir: Path) -> List[List[str]]:
    commands: List[List[str]] = []

    requirement_files = [
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-test.txt",
        "requirements/tests.txt",
        "requirements/dev.txt",
        "requirements/test.txt",
        "requirements/ci.txt",
    ]
    for rel_path in requirement_files:
        if (repo_dir / rel_path).exists():
            commands.append(["python", "-m", "pip", "install", "-r", rel_path])

    editable_target = "."
    extras = _infer_project_extras(repo_dir)
    if extras:
        editable_target = f".[{','.join(extras)}]"

    if (repo_dir / "setup.py").exists() or (repo_dir / "setup.cfg").exists() or (repo_dir / "pyproject.toml").exists():
        commands.append(["python", "-m", "pip", "install", "-e", editable_target])

    commands.append(["python", "-m", "pip", "install", "pytest", "coverage"])
    return commands


def _build_marker_expression(markers: Sequence[str]) -> str:
    clauses = [f"not {marker}" for marker in markers if marker]
    return " and ".join(clauses)


def _parse_pytest_summary(output: str) -> Dict[str, int]:
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "rerun": 0,
        "deselected": 0,
        "warnings": 0,
    }

    summary_line: Optional[str] = None
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("===") and " in " in stripped:
            summary_line = stripped.strip("= ").strip()
            break
        if re.match(r"^\d+ [A-Za-z_-]+(?:, \d+ [A-Za-z_-]+)* in .+$", stripped):
            summary_line = stripped
            break

    if not summary_line:
        return counts

    stats_part = summary_line.split(" in ", 1)[0]
    for chunk in stats_part.split(","):
        chunk = chunk.strip()
        match = re.match(r"(?P<count>\d+) (?P<label>[A-Za-z_-]+)", chunk)
        if not match:
            continue
        value = int(match.group("count"))
        label = match.group("label").lower()
        if label in counts:
            counts[label] += value
        elif label in {"error", "errors"}:
            counts["errors"] += value
        elif label in {"failures"}:
            counts["failed"] += value
        elif label in {"passes"}:
            counts["passed"] += value
        elif label in {"warning", "warnings"}:
            counts["warnings"] += value
        elif label in {"rerun", "reruns"}:
            counts["rerun"] += value

    return counts


def _stage_discover(context: PipelineContext) -> StageResult:
    checkout_created = context.ensure_checkout()
    repo_dir = context.repo_checkout_path
    detection = _detect_toolchain(repo_dir)
    details = {
        "repo_path": str(repo_dir),
        "checkout_created": checkout_created,
        "toolchain": detection,
    }
    return StageResult("discover", "completed", details)


def _choose_strategy(toolchain: Mapping[str, object]) -> str:
    if toolchain.get("ci_workflows"):
        return "activ"
    if toolchain.get("poetry"):
        return "poetry"
    if toolchain.get("environment_yml"):
        return "conda"
    if toolchain.get("requirements"):
        return "pip"
    return "custom"


def _stage_plan(context: PipelineContext) -> StageResult:
    discover_path = context.stage_output(Stage.DISCOVER)
    if not discover_path.exists():
        raise RuntimeError("Discover stage must be executed before planning.")
    discover_data = json.loads(discover_path.read_text())
    toolchain = discover_data["details"]["toolchain"]
    strategy = _choose_strategy(toolchain)
    plan = {
        "strategy": strategy,
        "python_version": "3.11",
        "builder_inputs": {
            "requires_network": bool(toolchain.get("ci_workflows")),
            "lockfile_sources": [
                name
                for name, present in (
                    ("pyproject.toml", toolchain.get("pyproject")),
                    ("requirements.txt", toolchain.get("requirements")),
                    ("environment.yml", toolchain.get("environment_yml")),
                )
                if present
            ],
        },
        "tests": {
            "runner": context.repo.tests.runner,
            "markers_exclude": context.repo.tests.markers_exclude,
            "timeout_s": context.repo.tests.timeout_s,
        },
    }
    return StageResult("plan", "completed", plan)


def _stage_build(context: PipelineContext) -> StageResult:
    plan_path = context.stage_output(Stage.PLAN)
    if not plan_path.exists():
        raise RuntimeError("Plan stage must be executed before build.")
    plan_data = json.loads(plan_path.read_text())["details"]
    repo_dir = context.repo_checkout_path

    install_commands = _build_install_commands(repo_dir)
    build_start = time.perf_counter()
    install_logs: List[Mapping[str, object]] = []
    for command in install_commands:
        result = run_command(command, cwd=repo_dir, check=False)
        install_logs.append(
            {
                "command": list(command),
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        if result.returncode != 0:
            return StageResult(
                "build",
                "failed",
                {
                    "strategy": plan_data["strategy"],
                    "commands": install_logs,
                    "message": "Dependency installation failed.",
                },
            )

    freeze = run_command(["python", "-m", "pip", "freeze"], cwd=repo_dir, check=False)
    pip_freeze = [line.strip() for line in freeze.stdout.splitlines() if line.strip()]

    env_manifest = {
        "python_version": sys.version.split()[0],
        "pip_freeze": pip_freeze,
        "apt_packages": [],
        "env": {
            "PYTHONHASHSEED": "0",
        },
        "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
    }
    env_manifest_path = context.artifact_path("env_manifest.json")
    dump_json(env_manifest_path, env_manifest)

    dockerfile_hash = hashlib.sha256(json.dumps(plan_data, sort_keys=True).encode("utf-8")).hexdigest()

    build_duration = time.perf_counter() - build_start
    build_details: Dict[str, object] = {
        "strategy": plan_data["strategy"],
        "base_image": "python:3.11-slim",
        "dockerfile_hash": dockerfile_hash,
        "lockfiles": plan_data["builder_inputs"]["lockfile_sources"],
        "env_manifest": str(env_manifest_path),
        "exit_code": 0,
        "duration_s": round(build_duration, 3),
        "commands": install_logs,
    }
    return StageResult("build", "completed", build_details)


def _stage_test(context: PipelineContext) -> StageResult:
    plan_path = context.stage_output(Stage.PLAN)
    if not plan_path.exists():
        raise RuntimeError("Plan stage must be executed before testing.")
    plan_data = json.loads(plan_path.read_text())["details"]
    repo_dir = context.repo_checkout_path

    markers_exclude: Sequence[str] = plan_data.get("tests", {}).get("markers_exclude", [])
    marker_expression = _build_marker_expression(markers_exclude)

    test_index_path = context.artifact_path("test_index.json")
    coverage_path = context.artifact_path("coverage.xml")
    log_path = context.logs_dir / "test.log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    collect_command = ["python", "-m", "pytest", "--collect-only", "-q"]
    if marker_expression:
        collect_command.extend(["-m", marker_expression])
    collect_result = run_command(collect_command, cwd=repo_dir, check=False)
    discovered_nodes = [line.strip() for line in collect_result.stdout.splitlines() if line.strip()]

    tests_index = {
        "repo_id": context.repo.id,
        "tests": [{"nodeid": node, "markers": []} for node in discovered_nodes],
    }
    dump_json(test_index_path, tests_index)

    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(["coverage", "erase"], cwd=repo_dir, check=False)
    pytest_command = ["coverage", "run", "-m", "pytest", "-q", "--maxfail", "1", "--durations", "30"]
    if marker_expression:
        pytest_command.extend(["-m", marker_expression])
    test_result = run_command(pytest_command, cwd=repo_dir, check=False)

    coverage_cmd = ["coverage", "xml", "-o", str(coverage_path)]
    coverage_result = run_command(coverage_cmd, cwd=repo_dir, check=False)

    coverage_pct = 0.0
    if coverage_result.returncode == 0 and coverage_path.exists():
        try:
            tree = ET.parse(coverage_path)
            root = tree.getroot()
            if root is not None and root.get("line-rate") is not None:
                coverage_pct = float(root.get("line-rate", "0")) * 100
        except ET.ParseError:
            coverage_pct = 0.0

    summary_counts = _parse_pytest_summary(test_result.stdout + "\n" + test_result.stderr)
    selected = sum(
        summary_counts[key]
        for key in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed", "rerun")
    )
    failed = summary_counts["failed"] + summary_counts["errors"]

    log_entries = [
        {
            "event": "collect",
            "command": collect_command,
            "returncode": collect_result.returncode,
            "stdout": collect_result.stdout,
            "stderr": collect_result.stderr,
        },
        {
            "event": "run",
            "command": pytest_command,
            "returncode": test_result.returncode,
            "stdout": test_result.stdout,
            "stderr": test_result.stderr,
        },
    ]
    log_path.write_text("\n".join(json.dumps(entry) for entry in log_entries) + "\n")

    status = "completed" if test_result.returncode == 0 else "failed"
    test_details = {
        "runner": context.repo.tests.runner,
        "discovered": len(discovered_nodes),
        "selected": selected,
        "passed": summary_counts["passed"],
        "failed": failed,
        "skipped": summary_counts["skipped"],
        "xfailed": summary_counts["xfailed"],
        "coverage": {
            "line_pct": round(coverage_pct, 2),
            "report_path": str(coverage_path),
        },
        "index_path": str(test_index_path),
        "logs": [str(log_path)],
    }

    if collect_result.returncode != 0:
        status = "failed"
        test_details["message"] = "Pytest collection failed."
    if coverage_result.returncode != 0:
        test_details["coverage"]["line_pct"] = 0.0
        test_details["coverage"]["error"] = coverage_result.stderr.strip()

    return StageResult("test", status, test_details)


def _stage_package(context: PipelineContext) -> StageResult:
    build_data = json.loads(context.stage_output(Stage.BUILD).read_text())["details"]
    test_data = json.loads(context.stage_output(Stage.TEST).read_text())["details"]

    manifest = {
        "repo_id": context.repo.id,
        "source": {
            "url": context.repo.url,
            "commit": context.repo.commit,
            "license": context.repo.license,
        },
        "build": build_data,
        "tests": test_data,
        "image": {
            "name": f"ghcr.io/open-cwm/{context.repo.id}:{context.repo.commit}",
            "size_mb": 0,
            "digest": "sha256:placeholder",
        },
        "artifacts": [
            build_data["env_manifest"],
            test_data["index_path"],
            test_data["coverage"]["report_path"],
            *test_data["logs"],
        ],
        "capabilities": {
            "run_pytest": True,
            "non_network": False,
            "deterministic_seed": True,
        },
    }
    manifest_path = context.artifact_path("repo_image_manifest.json")
    dump_json(manifest_path, manifest)
    package_details = {
        "manifest_path": str(manifest_path),
        "artifact_count": len(manifest["artifacts"]),
    }
    return StageResult("package", "completed", package_details)


def _stage_publish(context: PipelineContext) -> StageResult:
    manifest_path = context.artifact_path("repo_image_manifest.json")
    if not manifest_path.exists():
        raise RuntimeError("Package stage must produce a manifest before publish.")
    publish_details = {
        "manifest_path": str(manifest_path),
        "image_tag": f"ghcr.io/open-cwm/{context.repo.id}:{context.repo.commit}",
        "pushed": False,
    }
    return StageResult("publish", "pending", publish_details)


_STAGE_HANDLERS: Dict[Stage, StageHandler] = {
    Stage.DISCOVER: _stage_discover,
    Stage.PLAN: _stage_plan,
    Stage.BUILD: _stage_build,
    Stage.TEST: _stage_test,
    Stage.PACKAGE: _stage_package,
    Stage.PUBLISH: _stage_publish,
}


class RepoPipeline:
    """Stateful orchestrator that executes the module 1 state machine."""

    def __init__(self, context: PipelineContext) -> None:
        self.context = context

    def run_until(self, target_stage: Stage) -> StageResult:
        last_result: Optional[StageResult] = None
        for stage in Stage.ordered():
            last_result = self.run_stage(stage)
            if stage is target_stage:
                break
        assert last_result is not None
        return last_result

    def run_stage(self, stage: Stage) -> StageResult:
        stage_output = self.context.stage_output(stage)
        if stage_output.exists():
            cached = StageResult.from_dict(json.loads(stage_output.read_text()))
            return cached
        handler = _STAGE_HANDLERS[stage]
        result = handler(self.context)
        dump_json(stage_output, result.to_dict())
        return result

    def status(self) -> Dict[str, str]:
        statuses: Dict[str, str] = {}
        for stage in Stage.ordered():
            stage_output = self.context.stage_output(stage)
            if stage_output.exists():
                data = json.loads(stage_output.read_text())
                statuses[stage.name.lower()] = data.get("status", "unknown")
        return statuses
