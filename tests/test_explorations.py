"""Validation for exploration lab structure and docs."""

from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parent.parent
LAB_ROOT = ROOT / "explorations" / "lab"
REQUIRED_FILES = ("README.md", "lab.toml", "run.py")
REQUIRED_METADATA = (
    "slug",
    "title",
    "summary",
    "status",
    "tags",
    "run",
    "agent_authored",
    "safe_to_smoke",
)
REQUIRED_README_HEADINGS = (
    "## Question",
    "## Setup",
    "## How to Run",
    "## What It Shows",
    "## Pattern / Takeaway",
    "## Non-Obvious Failure Modes",
    "## Apply When",
    "## Next Questions",
)
ALLOWED_STATUSES = {"draft", "stable", "archived"}


def iter_lab_dirs() -> list[Path]:
    return sorted(
        path
        for path in LAB_ROOT.iterdir()
        if path.is_dir() and path.name != "_template"
    )


def test_exploration_template_exists() -> None:
    template_dir = LAB_ROOT / "_template"
    assert template_dir.is_dir()
    for filename in REQUIRED_FILES:
        assert (template_dir / filename).is_file()


def test_exploration_labs_follow_structure_and_metadata_contract() -> None:
    labs = iter_lab_dirs()
    assert labs, "Expected at least one concrete exploration lab."

    for lab_dir in labs:
        for filename in REQUIRED_FILES:
            assert (lab_dir / filename).is_file(), f"{lab_dir.name} is missing {filename}"

        metadata = tomllib.loads((lab_dir / "lab.toml").read_text())
        for key in REQUIRED_METADATA:
            assert key in metadata, f"{lab_dir.name} is missing metadata key {key}"

        assert metadata["slug"] == lab_dir.name
        assert metadata["status"] in ALLOWED_STATUSES
        assert isinstance(metadata["tags"], list)
        assert metadata["run"] == f"uv run python explorations/lab/{lab_dir.name}/run.py"


def test_exploration_labs_include_required_readme_sections() -> None:
    for lab_dir in iter_lab_dirs():
        readme = (lab_dir / "README.md").read_text()
        for heading in REQUIRED_README_HEADINGS:
            assert heading in readme, f"{lab_dir.name} README is missing {heading}"

        assert (
            "## Avoid When" in readme or "## Limits" in readme
        ), f"{lab_dir.name} README must define limitations"
