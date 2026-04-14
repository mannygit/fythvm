# llvmlite host symbol exposure

## Question

What is the smallest reliable pattern for exposing a host-owned Python callback to
JITed llvmlite code?

## Setup

This lab is a clean-room reinterpretation of the useful part of `~/fyth`'s
host-function exposure idea. It rebuilds the pattern without carrying over the old
framework layer.

The host:

- defines a Python callback with `ctypes.CFUNCTYPE`
- registers it with `llvm.add_symbol`
- keeps the callback object alive explicitly

The JIT module:

- declares the callback symbol as an external function
- calls it from an exported function named `exercise_host_symbol`

## How to Run

```bash
uv run python explorations/lab/llvmlite-host-symbol-exposure/run.py
```

Local macOS or Windows development should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/llvmlite-host-symbol-exposure/run.py
```

## What It Shows

The output shows:

- the generated IR that references a host-provided symbol
- the host symbol name and address registered with LLVM
- the ordered host-side call log captured by the Python callback
- the return value computed by JITed code through that callback

That makes the host/JIT boundary visible instead of hiding it behind a larger export
framework.

## Pattern / Takeaway

When JITed code needs to call back into the host, do it explicitly:

1. define a stable host callback
2. register its address with `llvm.add_symbol`
3. declare the symbol in the JIT module
4. resolve and call the JITed entrypoint as normal

This gives you a narrow, debuggable interop pattern that is easy to inspect.

## Non-Obvious Failure Modes

`llvm.add_symbol` does not keep the Python callback alive for you. The callback object
still needs a live Python reference for as long as the JITed code may call it.

That is a classic learned-by-doing trap. The name registration step feels global and
authoritative, but it does not change Python object lifetime. If the callback gets
collected, the symbol registration can outlive the object that made it safe.

The other subtlety is scope: symbol registration is process-level binding state, not a
per-module capability negotiation system. Use stable names deliberately and do not
assume a JIT module unload automatically undoes the registration for you.

## Apply When

Use this pattern when:

- JITed code needs to invoke host-owned helpers or logging hooks
- you want to keep the interop surface small and inspectable
- you need a clear proof that control crossed the host/JIT boundary

## Avoid When

Do not turn this pattern into an implicit global service locator. The point is to make
the boundary explicit, not to create a hidden framework that every module silently
depends on.

Avoid using this as a replacement for a larger runtime context when many services or
stateful resources must cross the boundary.

## Next Questions

- When should a callback remain a direct symbol versus moving behind a runtime context?
- What is the cleanest way to structure multiple host callbacks without creating name
  collisions or hidden dependencies?
- Which host/JIT interactions should return status codes instead of direct values?
