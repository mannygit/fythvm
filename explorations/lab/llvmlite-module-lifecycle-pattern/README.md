# Module lifecycle pattern for llvmlite JIT modules

## Question

How should a llvmlite MCJIT module handle setup, teardown, unload, and reload when
global constructor/destructor machinery is intentionally off the table, especially
on macOS where that ctor/dtor path is the unsafe one for llvmlite MCJIT?

## Setup

This lab builds two versions of the same small JIT module, then runs them through
the same host lifecycle harness:

- `build_lifecycle_module_raw()`
- `build_lifecycle_module_pythonic()`

Both export the same ordinary lifecycle functions:

- `module_init(ctx)`
- `module_fini(ctx)`
- `module_is_initialized()`
- `module_generation_marker()`

The host owns a lifecycle registry in Python. It loads the module with
`add_module()`, finalizes it, resolves lifecycle callbacks with
`get_function_address()`, and unloads it with `remove_module()`.

The raw version is the source of truth. It keeps the `IRBuilder` steps explicit and
close to 1:1 LLVM control flow. The Pythonic version uses a small slot helper and a
block-positioning context manager to make the repeated pointer work easier to read
without hiding the lifecycle order or the blocks themselves.

The runtime context is passed in as an opaque pointer shape (`i8*` in the emitted
IR, standing in for a conceptual `void*`). The lab uses a simple host-owned context
with counters so the side effects are visible.

Running this lab natively on Intel macOS is material, not just convenient. The
explicit lifecycle pattern here is partly a response to the MCJIT + Mach-O global
constructor/destructor problem, so native macOS execution validates the replacement
pattern on the platform that motivated it.

## How to Run

```bash
uv run python explorations/lab/llvmlite-module-lifecycle-pattern/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/llvmlite-module-lifecycle-pattern/run.py
```

## What It Shows

The run output demonstrates both variants side by side:

- the current target triple, so the platform under test is visible in the output
- the generated IR omits `llvm.global_ctors` and `llvm.global_dtors`
- the host can load a module, resolve lifecycle callbacks, and initialize it
- repeated `module_init()` and `module_fini()` requests are safe no-ops after the
  first successful transition
- unload ordering is explicit: `module_fini()` runs before the registry drops
  callbacks and before `remove_module()`
- a reloaded module receives a new generation even when the symbol names are the same
- the host rejects stale generation requests instead of calling an old callback path
- the raw and pythonic variants produce the same lifecycle effects and the same
  visible ordering, even though the pythonic version gets there with smaller helper
  objects

This is a runnable reference implementation of the simplest viable lifecycle pattern:
host-owned registry, explicit init/fini, host-owned runtime context, and generation
tracking from day one.

That matters more now that the lab can run natively on Intel macOS. The output is
no longer just evidence that the pattern works in the abstract or on Linux under
Docker. It is evidence that the explicit lifecycle protocol works on the real Mach-O
host where the implicit ctor/dtor path is the one under suspicion.

## Pattern / Takeaway

For llvmlite MCJIT modules with non-trivial setup or teardown, treat lifecycle as an
explicit host-driven protocol. Keep the raw builder version as the reference shape,
then layer small Python helpers on top when they improve readability without hiding
the actual block order:

1. build a normal module with exported lifecycle functions
2. load it with `add_module()` and `finalize_object()`
3. resolve lifecycle function addresses explicitly
4. call `module_init(ctx)` under host control
5. call `module_fini(ctx)` before unload
6. drop registry callbacks and then call `remove_module()`
7. assign a fresh generation on reload and reject requests against stale generations

That pattern is more portable and testable than trying to recover native-loader-like
startup semantics through LLVM global ctor/dtor features.

Native macOS execution makes this takeaway stronger. The lab is not merely arguing
for a cleaner abstraction. It is demonstrating a practical replacement on the host
platform that makes the native ctor/dtor route a bad bet for llvmlite MCJIT.

## Non-Obvious Failure Modes

Do not keep using callback addresses after `remove_module()`. Once the engine removes
the module, those addresses must be treated as dead even if the symbol names still
exist in a future reload.

This is a mental-model trap because `get_function_address()` gives you a plain integer
and the callback can be wrapped in `ctypes` successfully. Nothing about that wrapping
step tells you whether the underlying module is still live in the engine. Without a
host-owned registry plus generation checks, hot reload becomes a stale-pointer footgun.

Another easy misunderstanding is assuming the runtime can lean on constructor or
destructor behavior the way a normal compiled binary might. This lab intentionally
avoids that path. The point is to make lifecycle semantics host-owned and explicit,
not implicit, magical, or process-exit-driven.

It is also easy to treat a Linux-only or Docker-only run as sufficient evidence for
this design. That misses part of the point. The pattern exists partly because of
platform-specific behavior on macOS, so native Mach-O execution is materially better
evidence than a containerized Linux run.

The Pythonic variant should not hide lifecycle ordering. If the helper layer starts to
obscure when a slot is incremented or when `remove_module()` happens, the abstraction
has gone too far and the raw version should be the one you trust.

This lab also inherits the engine-lifetime rule from the minimal JIT pipeline lab:
keep the execution engine alive while any derived callback address is still in use.

## Apply When

Use this pattern when:

- a JIT module has setup or teardown work that must be portable and explicit
- modules may be unloaded and reloaded while the host process stays alive
- you need deterministic ordering and visibility around lifecycle transitions
- stale callbacks after hot reload would be dangerous

## Avoid When

Do not add lifecycle machinery to modules that are just pure stateless helper
functions. In those cases, a direct function-address lookup may be enough.

This lab also does not cover every lifecycle concern. It does not implement batch
rollback across several modules, dependency ordering, or a negative-control ctor/dtor
experiment on macOS. Those are follow-on explorations, not proof that the entire final
runtime design is complete.

## Next Questions

- What is the cleanest extension of this pattern to batch initialization with rollback
  on first failure?
- How should dependency ordering be modeled once modules depend on each other?
- A follow-on lab should isolate the unsupported global ctor/dtor path as a
  quarantined negative-control experiment on macOS so the reason for avoiding it is
  preserved as evidence, not just advice.
- What should the runtime context ABI look like once the toy counter-based context is
  replaced by real VM-owned services and handles?
