from __future__ import annotations

from pathlib import Path

from orchestrator.pipeline import (
    _build_install_commands,
    _build_marker_expression,
    _parse_pytest_summary,
)


def test_build_marker_expression() -> None:
    assert _build_marker_expression(["slow", "network"]) == "not slow and not network"
    assert _build_marker_expression([]) == ""


def test_parse_pytest_summary_counts() -> None:
    summary = """
    =============================== 5 passed, 2 skipped, 1 xfailed, 1 warning in 0.50s ===============================
    """.strip()
    counts = _parse_pytest_summary(summary)
    assert counts["passed"] == 5
    assert counts["skipped"] == 2
    assert counts["xfailed"] == 1
    assert counts["warnings"] == 1


def test_parse_pytest_summary_handles_failures() -> None:
    summary = """
    =============================== 3 passed, 1 failed, 2 errors in 1.00s ===============================
    """.strip()
    counts = _parse_pytest_summary(summary)
    assert counts["passed"] == 3
    assert counts["failed"] == 1
    assert counts["errors"] == 2


def test_parse_pytest_summary_quiet_output() -> None:
    summary = "5 passed, 1 skipped, 2 warnings in 0.12s"
    counts = _parse_pytest_summary(summary)
    assert counts["passed"] == 5
    assert counts["skipped"] == 1
    assert counts["warnings"] == 2


def test_build_install_commands_infers_requirements(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("pytest\n")
    (tmp_path / "pyproject.toml").write_text(
        """
        [project]
        name = "demo"
        version = "0.0.0"

        [project.optional-dependencies]
        test = ["pytest"]
        """
    )
    commands = _build_install_commands(tmp_path)
    assert ["python", "-m", "pip", "install", "-r", "requirements.txt"] in commands
    assert ["python", "-m", "pip", "install", "-e", ".[test]"] in commands
    assert ["python", "-m", "pip", "install", "pytest", "coverage"] in commands
