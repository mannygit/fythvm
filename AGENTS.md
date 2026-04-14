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

**All local development must use Docker.** Do not attempt to run tests, install dependencies, or execute any project commands directly on the host machine (macOS or Windows).

- Use the provided Warp environment: `ghcr.io/mannygit/warp-env-fythvm:latest`
- Never suggest or use `brew install llvm cmake` or BYO LLVM as an alternative.
- If a command fails due to missing `llvmlite`, `cmake`, or `LLVM`, instruct the user to use Docker — do not attempt to fix it on the host.
