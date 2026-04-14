# Building the vendored `llvmlite` wheel for Python 3.14 on Intel macOS

This machine is:

- `x86_64` Intel macOS
- running Python `3.14.3`

PyPI currently has `llvmlite 0.47.0` macOS `cp314` wheels for `arm64`, but not for `x86_64`, so this machine must build from source.

## What worked

- `llvmlite==0.47.0`
- Homebrew `llvm@20`
- Homebrew `cmake`
- Python `3.14` in a `uv` virtualenv

The built and smoke-tested wheel was:

```text
vendor/llvmlite/llvmlite-0.47.0-cp314-cp314-macosx_12_0_x86_64.whl
```

## Build commands

Install the toolchain:

```bash
brew install cmake llvm@20
```

Create a clean Python 3.14 environment with `uv`:

```bash
uv venv /tmp/llvmlite314 --python 3.14 --seed
```

Build the wheel:

```bash
export CMAKE_PREFIX_PATH=/usr/local/opt/llvm@20/lib/cmake
export MACOSX_DEPLOYMENT_TARGET=12.0
export _PYTHON_HOST_PLATFORM=macosx-12.0-x86_64

/tmp/llvmlite314/bin/python -m pip wheel \
  --no-cache-dir \
  --no-binary=:all: \
  --wheel-dir /tmp/llvmlite-wheelhouse-host \
  'llvmlite==0.47.0'
```

Copy the built wheel into the repo vendor directory:

```bash
cp /tmp/llvmlite-wheelhouse-host/llvmlite-0.47.0-cp314-cp314-macosx_12_0_x86_64.whl \
  vendor/llvmlite/
```

Install the vendored wheel into the host environment:

```bash
uv sync
```

## Smoke test

```bash
/tmp/llvmlite314/bin/python - <<'PY'
import llvmlite
from llvmlite import binding as llvm
from llvmlite import ir

print("llvmlite", llvmlite.__version__)
llvm.initialize_native_target()
llvm.initialize_native_asmprinter()

mod = ir.Module(name="smoke")
fty = ir.FunctionType(ir.VoidType(), ())
ir.Function(mod, fty, name="f")

parsed = llvm.parse_assembly(str(mod))
parsed.verify()
print("target", llvm.get_default_triple())
print("ok")
PY
```

Expected output:

```text
llvmlite 0.47.0
target x86_64-apple-darwin25.3.0
ok
```

## Notes

- Without `_PYTHON_HOST_PLATFORM=macosx-12.0-x86_64`, the build still worked but produced a narrower wheel tag: `macosx_26_0_x86_64`.
- `llvmlite.binding.initialize()` is deprecated in `0.47.0`; do not use it in the smoke test.
- Upstream `llvmlite` docs still say their preferred path is building against their own LLVM recipe, not arbitrary system LLVM builds. On this host, Homebrew `llvm@20` built and passed a smoke test.

## When to Rebuild

Rebuild and replace the vendored wheel when:

- `llvmlite` is upgraded
- Python 3.14 host compatibility changes and the current wheel stops working
- the vendored wheel is removed or corrupted

This host-support path is intentionally narrow. It is for Intel macOS + Python 3.14 only.

## References

- PyPI: <https://pypi.org/project/llvmlite/0.47.0/>
- Install docs: <https://llvmlite.pydata.org/en/latest/admin-guide/install.html>
