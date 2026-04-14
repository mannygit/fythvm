# fythvm

Fyth virtual machine — a Python-based VM built with [llvmlite](https://llvmlite.readthedocs.io/).

## Requirements

- [uv](https://docs.astral.sh/uv/) — **all dependency management must be done via `uv`**. Do not use `pip`, `poetry`, or any other tool.

> **Non-Linux environments (macOS, Windows)**: `llvmlite` requires LLVM and CMake to build from source on non-Linux platforms. Pre-built wheels are only available for Linux. You have two options:
>
> 1. **Docker** (recommended) — run development inside the provided Docker environment where Linux wheels are available.
> 2. **BYO LLVM** — install LLVM and CMake manually (e.g. `brew install llvm cmake` on macOS), then run `uv sync`.
>
> Without one of the above, `uv sync` will fail on macOS/Windows.

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