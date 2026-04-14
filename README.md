# fythvm

Fyth virtual machine — a Python-based VM built with [llvmlite](https://llvmlite.readthedocs.io/).

## Requirements

- Docker
- [uv](https://docs.astral.sh/uv/) inside the container — **all dependency management must be done via `uv`**. Do not use `pip`, `poetry`, or any other tool.

> **macOS / Windows**: local development must run in Docker. `llvmlite` wheels are available in the Linux-based development image, which avoids host LLVM/CMake setup entirely.

## Setup

Build the development image:

```bash
docker compose build
```

Install dependencies into the persisted container environment:

```bash
docker compose run --rm dev uv sync
```

The compose setup mounts two named Docker volumes:

- `venv` at `/workspace/.venv`
- `uv-cache` at `/workspace/.uv-cache`

That means dependencies and downloaded wheels are reused across container runs and only need to be rebuilt if those volumes are removed.

## Dependency Management

| Action | Command |
|---|---|
| Install all dependencies | `docker compose run --rm dev uv sync` |
| Add a runtime dependency | `docker compose run --rm dev uv add <package>` |
| Add a dev dependency | `docker compose run --rm dev uv add --dev <package>` |
| Remove a dependency | `docker compose run --rm dev uv remove <package>` |
| Update dependencies | `docker compose run --rm dev uv lock --upgrade` |

## Development

```bash
# Run tests
docker compose run --rm dev uv run pytest

# Lint
docker compose run --rm dev uv run ruff check

# Format
docker compose run --rm dev uv run ruff format

# Type check
docker compose run --rm dev uv run mypy src
```
