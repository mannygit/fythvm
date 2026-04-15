"""Smoke tests for exploration lab entrypoints."""

from __future__ import annotations

from pathlib import Path
import subprocess
import shlex
import tomllib

import pytest


ROOT = Path(__file__).resolve().parent.parent
LAB_ROOT = ROOT / "explorations" / "lab"


def iter_lab_dirs() -> list[Path]:
    return sorted(
        path
        for path in LAB_ROOT.iterdir()
        if path.is_dir() and path.name != "_template"
    )


def load_run_command(lab_dir: Path) -> tuple[str, list[str]]:
    metadata = tomllib.loads((lab_dir / "lab.toml").read_text())
    command = metadata["run"]
    return command, shlex.split(command)


@pytest.mark.parametrize("lab_dir", iter_lab_dirs(), ids=lambda path: path.name)
def test_lab_default_run_entrypoint_succeeds(lab_dir: Path) -> None:
    command, argv = load_run_command(lab_dir)
    try:
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"{lab_dir.name} timed out after {exc.timeout}s\n"
            f"command: {command}\n"
            f"stdout:\n{exc.stdout or ''}\n"
            f"stderr:\n{exc.stderr or ''}"
        )

    assert completed.returncode == 0, (
        f"{lab_dir.name} failed with code {completed.returncode}\n"
        f"command: {command}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
