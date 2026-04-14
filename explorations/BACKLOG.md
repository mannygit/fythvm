# Exploration Backlog

Use this file to track exploration ideas that AI agents should pick up, continue, or
close out. Keep the backlog small and explicit.

## Ready

- `loop-carried-traversal-phis`
  - Title: Loop-carried traversal phis
  - Goal: Capture the linked-list traversal shape from `~/fyth` where one phi carries
    the loop cursor and another phi carries derived state like a count.
  - Why it matters: This is a stronger phi pattern than a simple branch/merge because
    it shows phis as loop-carried state in traversal code.
  - Success signal: The lab demonstrates traversal with a cursor phi, an accumulator
    phi, and at least one early-exit or derived-result case that makes the carried
    state visible.

- `result-carrier-phi-sentinels`
  - Title: Result-carrier phi with sentinel values
  - Goal: Show the comparison/search shape where a phi returns either a meaningful
    result or a sentinel such as `-1`.
  - Why it matters: `~/fyth` used this in byte and word comparison paths, and it is a
    real learned-by-doing pattern for compact loop results.
  - Success signal: The lab shows a loop or staged comparison whose final phi carries
    either a useful result or a sentinel, and explains why that is cleaner than
    branching out to separate return blocks.

- `musttail-chunked-memory-ops`
  - Title: `musttail` chunked copy and compare
  - Goal: Rebuild the abandoned `test_memory2.py` experiments that implemented copy
    and compare through chunked tail recursion over 8-byte, 4-byte, then 1-byte cases.
  - Why it matters: This is unusually low-level IR work that clearly came from
    experimentation and is not represented anywhere in the current labs.
  - Success signal: The lab demonstrates one or both chunked memory operations,
    explains the `musttail` constraints, and makes the chunk-selection logic and tail
    recursion shape visible in the emitted IR and output.

## Triage

- `multi-stage-early-exit-search`
  - Title: Multi-stage early-exit search blocks
  - Goal: Capture the pattern of several decision stages converging on one `exit`
    block with a phi carrying either the found value or a sentinel.
  - Why it matters: `~/fyth` used this for hidden checks, length checks, and compare
    loops, and it is a useful lowering shape for searches.
  - Distinct from existing labs: the current phi lab is simpler and does not cover
    multi-stage early-exit composition.

- `direct-threaded-musttail-dispatch`
  - Title: Direct-threaded interpreter dispatch with `musttail`
  - Goal: Capture the `next_fn` / `@EXECUTE` / `EXECUTE` pattern from `forth.py` and
    `forth_base.py` as a direct-threaded interpreter dispatch shape.
  - Why it matters: This is one of the most distinctive patterns in `~/fyth` and a
    good example of learned LLVM control-flow design.
  - Distinct from existing labs: none of the current labs cover threaded interpreter
    dispatch or tail-called continuation threading.

- `terminator-rewrite-next-trampoline`
  - Title: Terminator rewrite for next-step trampolines
  - Goal: Capture the pattern where generated functions are post-processed by
    replacing their terminator, appending a `next` block, and tail-calling a shared
    continuation.
  - Why it matters: This is an unusual but concrete technique for retrofitting a
    common continuation onto existing emitted functions.
  - Distinct from existing labs: it is not the same as delayed export or generic tail
    calls; it is specifically about CFG rewriting after function generation.

- `forward-declare-then-reopen-function`
  - Title: Forward declare and reopen function emission
  - Goal: Capture the `create_function()` pattern that reuses an existing named
    function when reopening emission after a forward declaration.
  - Why it matters: This is adjacent to delayed export, but it is its own pattern for
    safe re-entry into function construction.
  - Distinct from existing labs: `delayed-ir-export-pattern` focuses on module-scoped
    export planning, not reopening an already-declared function by name.

- `alignment-bit-tricks-vs-branch-phi`
  - Title: Alignment bit tricks versus branch-plus-phi
  - Goal: Capture the shift from a branchy alignment calculation to the compact
    bit-mask form `(index + 3) & -4`.
  - Why it matters: It is a small but real lowering insight that likely came from
    experimentation rather than formal compiler training.
  - Distinct from existing labs: this is a low-level address arithmetic pattern, not a
    control-flow or lifecycle pattern.

- `select-driven-comparison-builtins`
  - Title: `select`-driven comparison builtin factoring
  - Goal: Capture the shared-helper shape used in `forth_equality.py` where several
    stack comparisons lower to `icmp` plus `select`.
  - Why it matters: It is a compact pattern for repeated comparison lowering and shows
    where helper abstraction stays acceptable.
  - Distinct from existing labs: it overlaps slightly with `metaprogramming-ir-builders`
    but is specifically about arithmetic/comparison lowering via `select`.

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

- `ssa-phi-merge`
  - Title: SSA / phi merge patterns in llvmlite
  - Goal: Show how to model a value that comes from multiple predecessor blocks.
  - Why it matters: Control-flow-heavy codegen is hard to reason about without a
    reliable phi pattern.
  - Success signal: The lab shows a working merge shape, the generated IR, and the
    conditions where phi is required instead of ad hoc temporaries.
  - Takeaway: Use `phi` at real control-flow joins, and use `select` only when both
    candidate values are safe to compute eagerly in straight line.
  - Lab: `explorations/lab/ssa-phi-merge/`

- `ir-inspection-tooling`
  - Title: IR inspection and debugging helpers
  - Goal: Explore small tooling shapes for printing, diffing, or annotating emitted
    IR during experimentation.
  - Why it matters: Faster feedback makes it easier to validate codegen ideas before
    they harden into package code.
  - Success signal: The lab yields one or more practical helper patterns that make IR
    exploration faster without hiding the emitted LLVM.
  - Takeaway: Capture raw IR early and diff the raw text later; keep annotations thin
    enough that the LLVM itself stays visible.
  - Lab: `explorations/lab/ir-inspection-tooling/`

- `mcjit-global-ctor-dtor-negative-control`
  - Title: MCJIT global ctor/dtor negative control on macOS
  - Goal: Isolate the unsupported `llvm.global_ctors` / `llvm.global_dtors` path as a
    quarantined demonstration of why the explicit lifecycle pattern exists.
  - Why it matters: The lifecycle design is easier to trust when the risky alternative
    is captured as evidence instead of left as folklore.
  - Success signal: The lab documents the unsupported path, runs only as a manual or
    expected-failure experiment, and makes clear that production code must not depend
    on ctor/dtor execution through llvmlite MCJIT on macOS.
  - Takeaway: Keep risky ctor/dtor behavior as a quarantined negative control with a
    safe default run and any runtime attempt isolated in a child process.
  - Lab: `explorations/lab/mcjit-global-ctor-dtor-negative-control/`

- `metaprogramming-ir-builders`
  - Title: Metaprogramming patterns for repetitive IR construction
  - Goal: Capture a reusable way to generate repeated llvmlite builder code without
    turning the codegen path opaque.
  - Why it matters: Repetition is easy to generate but hard to keep readable and
    debuggable.
  - Success signal: The lab demonstrates one pattern that improves reuse and clearly
    states when the abstraction helps versus when it obscures the IR shape.
  - Takeaway: Bless one thin helper for repeated branch/phi boilerplate, but stop
    before helper composition starts hiding the CFG you need to understand.
  - Lab: `explorations/lab/metaprogramming-ir-builders/`

- `delayed-ir-export-pattern`
  - Title: Deferred IR export and finalization pattern
  - Goal: Redesign the useful idea behind `~/fyth`'s delayed export flow without
    reproducing its fragile global import-time architecture.
  - Why it matters: Some codegen paths want forward declarations first and concrete IR
    emission later, but the coordination needs to stay explicit and testable.
  - Success signal: The lab shows a clean delayed-definition workflow with obvious
    ordering rules and without leaning on global mutable registries as magic.
  - Takeaway: Use a host-owned, module-scoped export plan with declaration first,
    body emission later, and explicit finalization as the moment exports become callable.
  - Lab: `explorations/lab/delayed-ir-export-pattern/`

- `word-header-packing-and-flags`
  - Title: Word header packing and hidden/immediate flags
  - Goal: Rebuild the word-name/header packing idea from `~/fyth` as a small focused
    experiment.
  - Why it matters: Dictionary formats are easiest to reason about when the byte-level
    layout and flag semantics are made concrete.
  - Success signal: The lab demonstrates packing, unpacking, and comparison behavior
    with clear output and explicit limits.
  - Takeaway: Treat the lightweight `words.py` header as the v1 canonical shape:
    one byte for length and flags, with visibility and metadata policy layered on top.
  - Lab: `explorations/lab/word-header-packing-and-flags/`

- `dictionary-linked-memory-layout`
  - Title: Linked dictionary layout in linear memory
  - Goal: Explore a linked-list-style dictionary layout derived from `~/fyth` without
    inheriting its unstable direct implementation path.
  - Why it matters: A clean linked dictionary model could still be useful, but the old
    path needs redesign rather than extraction.
  - Success signal: The lab shows insertion and traversal semantics in a way that is
    simpler and more reliable than the old code.
  - Takeaway: Model the dictionary head as the newest payload offset and store the
    previous payload offset in the cell immediately before each payload.
  - Lab: `explorations/lab/dictionary-linked-memory-layout/`

## Icebox

None.
