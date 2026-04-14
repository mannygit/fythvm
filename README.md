# fythvm

Fyth virtual machine — a Python-based VM built with [llvmlite](https://llvmlite.readthedocs.io/).

## Requirements

- [uv](https://docs.astral.sh/uv/) — **all dependency management must be done via `uv`**. Do not use `pip`, `poetry`, or any other tool.

## Setup

```bash
uv sync
```

## Dependency Management

| Action | Command |
|---|---|
| Install all dependencies | `uv sync` |
| Add a runtime dependency | `uv add <package>` |
| Add a dev dependency | `uv add --dev <package>` |
| Remove a dependency | `uv remove <package>` |
| Update dependencies | `uv lock --upgrade` |

## Development

```bash
# Run tests
uv run pytest

# Lint
uv run ruff check

# Format
uv run ruff format

# Type check
uv run mypy src
```