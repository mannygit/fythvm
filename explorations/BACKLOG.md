# Exploration Backlog

Use this file to track exploration ideas that AI agents should pick up, continue, or
close out. Keep the backlog small and explicit.

## Ready

- `ssa-phi-merge`
  - Title: SSA / phi merge patterns in llvmlite
  - Goal: Show how to model a value that comes from multiple predecessor blocks.
  - Why it matters: Control-flow-heavy codegen is hard to reason about without a
    reliable phi pattern.
  - Success signal: The lab shows a working merge shape, the generated IR, and the
    conditions where phi is required instead of ad hoc temporaries.

- `metaprogramming-ir-builders`
  - Title: Metaprogramming patterns for repetitive IR construction
  - Goal: Capture a reusable way to generate repeated llvmlite builder code without
    turning the codegen path opaque.
  - Why it matters: Repetition is easy to generate but hard to keep readable and
    debuggable.
  - Success signal: The lab demonstrates one pattern that improves reuse and clearly
    states when the abstraction helps versus when it obscures the IR shape.

- `ir-inspection-tooling`
  - Title: IR inspection and debugging helpers
  - Goal: Explore small tooling shapes for printing, diffing, or annotating emitted
    IR during experimentation.
  - Why it matters: Faster feedback makes it easier to validate codegen ideas before
    they harden into package code.
  - Success signal: The lab yields one or more practical helper patterns that make IR
    exploration faster without hiding the emitted LLVM.

- `delayed-ir-export-pattern`
  - Title: Deferred IR export and finalization pattern
  - Goal: Redesign the useful idea behind `~/fyth`'s delayed export flow without
    reproducing its fragile global import-time architecture.
  - Why it matters: Some codegen paths want forward declarations first and concrete IR
    emission later, but the coordination needs to stay explicit and testable.
  - Success signal: The lab shows a clean delayed-definition workflow with obvious
    ordering rules and without leaning on global mutable registries as magic.

- `word-header-packing-and-flags`
  - Title: Word header packing and hidden/immediate flags
  - Goal: Rebuild the word-name/header packing idea from `~/fyth` as a small focused
    experiment.
  - Why it matters: Dictionary formats are easiest to reason about when the byte-level
    layout and flag semantics are made concrete.
  - Success signal: The lab demonstrates packing, unpacking, and comparison behavior
    with clear output and explicit limits.

- `dictionary-linked-memory-layout`
  - Title: Linked dictionary layout in linear memory
  - Goal: Explore a linked-list-style dictionary layout derived from `~/fyth` without
    inheriting its unstable direct implementation path.
  - Why it matters: A clean linked dictionary model could still be useful, but the old
    path needs redesign rather than extraction.
  - Success signal: The lab shows insertion and traversal semantics in a way that is
    simpler and more reliable than the old code.

## In Progress

None.

## Done

- `llvmlite-minimal-jit-pipeline`
  - Title: Minimal llvmlite JIT pipeline
  - Goal: Capture the smallest complete path from IR construction to executable code.
  - Why it matters: It is the base shape many future llvmlite explorations will build
    on.
  - Success signal: The lab prints the generated IR, executes the compiled function,
    and explains why this is the right baseline pattern for later experiments.
  - Takeaway: Start from a full end-to-end IR -> verify -> engine -> call pipeline so
    later experiments change one concern at a time.
  - Lab: `explorations/lab/llvmlite-minimal-jit-pipeline/`

- `llvmlite-module-lifecycle-pattern`
  - Title: Module lifecycle pattern for llvmlite JIT modules
  - Goal: Demonstrate an explicit host-driven lifecycle for JIT modules without
    `llvm.global_ctors` or `llvm.global_dtors`.
  - Why it matters: MCJIT lifecycle behavior should be predictable across macOS and
    Linux and should not depend on loader-driven startup or teardown semantics.
  - Success signal: The lab shows explicit load/init/fini/unload/reload behavior,
    generation-safe stale callback rejection, and deterministic finalization before
    `remove_module()`.
  - Takeaway: Treat JIT lifecycle as a host-owned protocol with explicit init/fini and
    generation tracking instead of delegating setup and teardown to global ctor/dtor
    machinery.
  - Lab: `explorations/lab/llvmlite-module-lifecycle-pattern/`

- `llvmlite-ir-to-ctypes-bridge`
  - Title: llvmlite IR to ctypes bridge
  - Goal: Rebuild the old `~/fyth` type-bridging idea as a small clear lab that maps
    useful IR types into `ctypes` wrappers and uses them against live JIT addresses.
  - Why it matters: Host/JIT interop gets much easier once the ABI mapping rules are
    explicit instead of ad hoc.
  - Success signal: The lab prints the type mappings, reads a JIT global through a
    mapped struct, and calls a JIT function through a mapped function signature.
  - Takeaway: Treat IR-to-ctypes conversion as an explicit ABI bridge and validate it
    against real JIT addresses rather than assuming the types "obviously" line up.
  - Lab: `explorations/lab/llvmlite-ir-to-ctypes-bridge/`

- `llvmlite-host-symbol-exposure`
  - Title: llvmlite host symbol exposure
  - Goal: Demonstrate the clean part of `~/fyth`'s host-function exposure pattern
    using `llvm.add_symbol` and a live Python callback.
  - Why it matters: JITed code often needs a deliberate path back into host-owned
    behavior, and that path should be explicit and easy to debug.
  - Success signal: The lab shows a JITed function calling a host-registered symbol,
    returning a value, and leaving visible host-side evidence of the call sequence.
  - Takeaway: Expose host behavior by registering stable callback symbols explicitly,
    not by hiding the boundary behind framework magic.
  - Lab: `explorations/lab/llvmlite-host-symbol-exposure/`

- `llvmlite-jit-stack-operations`
  - Title: llvmlite JIT stack operations
  - Goal: Rebuild the old `~/fyth` stack idea as a minimal JITed downward-growing
    stack with explicit exported operations.
  - Why it matters: A stack discipline is one of the clearest low-level runtime shapes
    worth preserving from the older project.
  - Success signal: The lab shows push/pop/dup/swap/over behavior with both JITed
    operations and host-visible stack snapshots after each step.
  - Takeaway: Keep the memory model and the logical stack model visible at the same
    time so stack semantics stay interpretable.
  - Lab: `explorations/lab/llvmlite-jit-stack-operations/`

## Icebox

None.
