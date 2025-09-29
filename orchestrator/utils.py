from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Mapping, Sequence


class CommandError(RuntimeError):
    """Raised when a subprocess exits with a non-zero status code."""

    def __init__(self, command: Sequence[str], returncode: int, stdout: str, stderr: str) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"Command {' '.join(command)} failed with exit code {returncode}\nSTDOUT:{stdout}\nSTDERR:{stderr}"
        )


def run_command(
    command: Sequence[str],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Execute a subprocess command and return the completed process."""

    process_env = os.environ.copy()
    if env:
        process_env.update(env)

    result = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        env=process_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise CommandError(command, result.returncode, result.stdout, result.stderr)
    return result


def ensure_directory(path: str | Path) -> Path:
    """Create a directory and return its Path object."""

    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_file(path: str | Path) -> str:
    """Compute the SHA256 hash of the provided file."""

    digest = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump_json(path: str | Path, payload: Mapping[str, object], *, indent: int = 2) -> None:
    """Write structured JSON to disk with a trailing newline for readability."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=indent, sort_keys=True) + "\n")
