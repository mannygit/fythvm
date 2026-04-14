# llvmlite IR to ctypes bridge

## Question

What is the smallest useful pattern for turning llvmlite IR types into `ctypes`
shapes that can safely wrap live JIT globals and functions?

## Setup

This lab is a clean-room reinterpretation of the old `~/fyth` `ctypes_utils.py`
pattern. It rebuilds only the useful idea: map a narrow set of IR types into Python
`ctypes`, then prove the mapping against real JIT addresses.

The demo module contains:

- a global literal struct named `pair_data`
- a simple arithmetic function named `sum_scaled`

The host side maps the IR struct and function types into `ctypes`, reads the global
through the mapped struct, and calls the function through the mapped signature.

## How to Run

```bash
uv run python explorations/lab/llvmlite-ir-to-ctypes-bridge/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/llvmlite-ir-to-ctypes-bridge/run.py
```

## What It Shows

The output is labeled to make the bridge explicit:

- the generated IR
- a readable summary of several IR-to-`ctypes` mappings
- a live read of a JIT global through a mapped `ctypes.Structure`
- a live call through a mapped `ctypes.CFUNCTYPE` signature

That demonstrates the pattern with real addresses rather than just printing type
objects in isolation.

## Pattern / Takeaway

Treat IR-to-`ctypes` conversion as an explicit ABI bridge:

1. choose a narrow supported subset of IR types
2. map those types deliberately into `ctypes`
3. validate the mapping against live JIT addresses
4. keep the mapping logic small enough that its assumptions stay obvious

This is a good foundational pattern for host/JIT interop work because it replaces
guessing with a concrete bridge you can inspect and test.

## Non-Obvious Failure Modes

"The types look the same" is not enough. A mapping is only useful if it matches the
ABI shape the JIT actually produced.

That is the trap this lab is trying to avoid. It is easy to write a clever generic
mapper that feels complete but silently assumes too much about structs, pointers, or
calling conventions. The safer pattern is to support a narrow, demonstrated subset and
prove it against real addresses.

Another subtle issue is that wrapping a function address with `ctypes` does not keep
the JIT resources alive for you. The execution engine still needs to stay alive while
the wrapped callable is in use.

## Apply When

Use this pattern when:

- you need to call a JITed function from Python through a stable signature
- you need to inspect a JIT global from the host side
- you want a small explicit bridge between llvmlite IR and `ctypes`

## Avoid When

Do not treat this lab as a complete IR-to-`ctypes` compatibility layer. It is a small
reference for a useful subset, not a promise that every LLVM type should be mapped
this way.

Avoid growing the mapper indiscriminately. Once the type surface becomes large, it is
easy to hide ABI assumptions behind generic-looking helper code.

## Next Questions

- Which additional IR shapes are genuinely worth supporting in a future bridge?
- How should pointer-heavy or nested-runtime layouts be validated safely?
- When does it make sense to stop using `ctypes` and move to a different FFI boundary?
