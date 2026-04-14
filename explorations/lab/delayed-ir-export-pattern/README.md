# Delayed IR Export Pattern

## Question

How do you stage llvmlite exports so declarations arrive before bodies, without a
global registry?

## Setup

This lab builds a small module-scoped export plan. Phase 1 declares the exported
symbols and signatures. Phase 2 fills in the function bodies later, even if a body
needs to call another export whose definition has not been emitted yet.

The host owns the plan object, not a process-wide registry. Finalization is explicit:
the host verifies the module, creates the execution engine, resolves function
addresses, and only then exposes callable Python wrappers.

## How to Run

```bash
uv run python explorations/lab/delayed-ir-export-pattern/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/delayed-ir-export-pattern/run.py
```

## What It Shows

The output walks through the two-phase workflow:

- declaration order for the module exports
- definition order, including a body emitted before its callee body
- the final LLVM IR after both phases are complete
- runtime calls that only become possible after explicit finalization
- error messages for duplicate names, calling before finalization, and finalizing
  with a missing body

That makes the ordering rules visible instead of implicit.

## Pattern / Takeaway

Use a host-owned export plan per module when bodies need to be delayed. Declare the
symbol and signature first, define bodies later, and make finalization the one explicit
step that turns IR into something callable.

This keeps dependency order local to the module and avoids ambient registries or hidden
startup side effects.

## Non-Obvious Failure Modes

- A declaration is not a callable definition. It only reserves the symbol and type.
- Duplicate names are a real bug, not a convenience. A module-scoped plan should fail
  fast instead of silently shadowing or reusing a symbol.
- Forgetting to finalize means you still have IR, but no live callable export.
- Defining a body that depends on another export is safe only if the callee was already
  declared.
- Ambient registries make the dependency graph feel easier at first, but they hide where
  exported symbols come from and make module-local ordering harder to reason about.

## Apply When

Use this pattern when:

- a module has several exports that reference each other
- you need to assemble bodies in stages instead of all at once
- you want export availability to be explicit and testable
- the host should control when IR becomes callable

## Avoid When

Do not use this pattern for a one-function toy where declaration and definition happen
in the same place and never vary.

It is also the wrong tool if you want implicit, global, import-time registration. This
lab is specifically about replacing that with a module-scoped protocol.

## Next Questions

- How should delayed export plans interact with external host symbols?
- What is the cleanest way to represent cross-module dependencies without reintroducing
  a global registry?
- When does a delayed export plan want to become a reusable helper versus staying a
  one-off module-local object?
