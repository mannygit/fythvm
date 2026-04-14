# fythvm — Warp Project Rules

## Non-Linux Development

For development in non-Linux environments (macOS, Windows), `llvmlite` pre-built wheels are not available. Development requires one of:

1. **Docker** (recommended) — use the provided Warp environment (`ghcr.io/mannygit/warp-env-fythvm:latest`)
2. **BYO LLVM** — install LLVM and CMake manually before running `uv sync`
   - macOS: `brew install llvm cmake`
