# fythvm — Warp Project Rules

## Cloud Agent Environment (Oz)

**Cloud agents run on Linux.** Do not use Docker. Use `uv` directly:

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Lint
uv run ruff check

# Format
uv run ruff format

# Type check
uv run mypy src
```

`llvmlite` pre-built Linux wheels are available via PyPI — no LLVM or CMake installation is needed.

## Local Development

**Default local development uses Docker**, except for one supported host path:

- Intel macOS
- Python 3.14
- vendored wheel at `vendor/llvmlite/llvmlite-0.47.0-cp314-cp314-macosx_12_0_x86_64.whl`

On that exact host combination, use `uv` directly:

```bash
uv sync
uv run pytest
uv run ruff check
uv run ruff format
uv run mypy src
```

For all other local hosts, use Docker. That includes Apple Silicon macOS, Windows, and unsupported Python versions.

- Use the provided Warp environment: `ghcr.io/mannygit/warp-env-fythvm:latest`
- Use `vendor/llvmlite/llvmlite-python314-build.md` only when the supported Intel macOS host path needs the vendored wheel rebuilt.
- Do not suggest arbitrary BYO LLVM flows outside that documented Intel macOS wheel-build path.
- If a local command fails due to host/toolchain issues on an unsupported machine, instruct the user to use Docker instead of trying to force a host install.

## Project Skills

When asked to add, update, or continue an experiment under `explorations/`, use the
project skill at `.codex/skills/add-exploration-lab/SKILL.md`.
