"""Smoke tests for exploration lab entrypoints."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parent.parent
LAB_ROOT = ROOT / "explorations" / "lab"


def iter_lab_dirs() -> list[Path]:
    return sorted(
        path
        for path in LAB_ROOT.iterdir()
        if path.is_dir() and path.name != "_template"
    )


@pytest.mark.parametrize("lab_dir", iter_lab_dirs(), ids=lambda path: path.name)
def test_lab_default_run_entrypoint_succeeds(lab_dir: Path) -> None:
    run_py = lab_dir / "run.py"
    completed = subprocess.run(
        [sys.executable, str(run_py)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, (
        f"{lab_dir.name} failed with code {completed.returncode}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
