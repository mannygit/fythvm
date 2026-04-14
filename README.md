# fythvm

Fyth virtual machine — a Python-based VM built with [llvmlite](https://llvmlite.readthedocs.io/).

## Requirements

- [uv](https://docs.astral.sh/uv/) — **all dependency management must be done via `uv`**. Do not use `pip`, `poetry`, or any other tool.
- Docker for unsupported local hosts
- Intel macOS + Python 3.14 can also use the host workflow described below

> **Supported host exception**: this repo now supports local host development on Intel macOS with Python 3.14 by using the vendored `llvmlite 0.47.0` wheel in `vendor/llvmlite/`.
>
> **All other local hosts** should continue using Docker. That includes Apple Silicon macOS, Windows, and any macOS/Python combination that does not match the vendored wheel tag.

## Setup

### Supported Intel macOS Host Setup

If the host is Intel macOS and `python3 --version` is a 3.14 release, install directly on the host:

```bash
uv sync
```

The project uses a marker-gated `tool.uv.sources` entry so `uv` will prefer the vendored
wheel at `vendor/llvmlite/llvmlite-0.47.0-cp314-cp314-macosx_12_0_x86_64.whl` only on
that supported host combination.

If the wheel needs to be rebuilt, use:

`vendor/llvmlite/llvmlite-python314-build.md`

### Docker Setup

For unsupported local hosts, use Docker.

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
| Install all dependencies on supported Intel mac host | `uv sync` |
| Install all dependencies via Docker | `docker compose run --rm dev uv sync` |
| Add a runtime dependency | `uv add <package>` or `docker compose run --rm dev uv add <package>` |
| Add a dev dependency | `uv add --dev <package>` or `docker compose run --rm dev uv add --dev <package>` |
| Remove a dependency | `uv remove <package>` or `docker compose run --rm dev uv remove <package>` |
| Update dependencies | `uv lock --upgrade` or `docker compose run --rm dev uv lock --upgrade` |

## Development

```bash
# Host Intel macOS + Python 3.14
uv run pytest
uv run ruff check
uv run ruff format
uv run mypy src

# Run tests
docker compose run --rm dev uv run pytest

# Lint
docker compose run --rm dev uv run ruff check

# Format
docker compose run --rm dev uv run ruff format

# Type check
docker compose run --rm dev uv run mypy src
```

## Host Support Notes

- The supported host path is intentionally narrow: Intel macOS, Python 3.14, and the vendored `llvmlite 0.47.0` wheel.
- Apple Silicon macOS is not supported by this host workflow yet.
- If the host wheel becomes invalid or needs to be regenerated, rebuild it using [llvmlite-python314-build.md](/Users/manny/fythvm/vendor/llvmlite/llvmlite-python314-build.md:1).
- Docker remains the fallback for every local environment outside that exact host combination.

## Explorations

Exploratory runnable research artifacts live under `explorations/`.

See `explorations/README.md` for the lab format, authoring rules, and backlog-driven
workflow.
