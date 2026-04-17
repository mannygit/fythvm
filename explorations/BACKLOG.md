# Exploration Backlog

Use this file to track exploration ideas that AI agents should pick up, continue, or
close out. Keep the backlog small and explicit.

## Ready

- `llvmlite-assume-and-overflow-intrinsics`
  - Title: llvmlite assume and overflow intrinsics
  - Goal: Show how `llvm.assume` and the integer overflow intrinsics are exposed in
    llvmlite and what they actually mean at the IR level.
  - Why it matters: These intrinsics are directly available today, but they are easy
    to misread as runtime checks or magic arithmetic.

- `bit-twiddling-intrinsics`
  - Title: Bit-twiddling intrinsics in llvmlite
  - Goal: Demonstrate `bswap`, `bitreverse`, `ctpop`, `ctlz`, and `cttz` through the
    current `IRBuilder` helpers.
  - Why it matters: They form a coherent intrinsic family and make a good contrast
    with the manually declared mem* intrinsics.

- `memcpy-vs-handbuilt-copy`
  - Title: LLVM mem intrinsics versus hand-built copy lowering
  - Goal: Compare the mem-intrinsics lab against the musttail chunked copy lab so the
    tradeoff between built-in intrinsics and explicit control-flow lowering is
    captured directly.
  - Why it matters: The repo now has both patterns, but not yet one place that
    explains when you would pick one over the other.

## Triage

- `direct-threaded-musttail-dispatch`
  - Title: Direct-threaded interpreter dispatch with `musttail`
  - Goal: Capture the `next_fn` / `@EXECUTE` / `EXECUTE` pattern from `forth.py` and
    `forth_base.py` as a direct-threaded interpreter dispatch shape.
  - Source in `~/fyth`: start from `src/fyth/forth.py` and `src/fyth/forth_base.py`,
    especially the history around commits `bf07ecd`, `8e84625`, and `7945486`.
  - What to mine: the real pattern is a threaded continuation model where builtins
    tail-call the next interpreter step; do not reduce it to generic tail recursion.
  - Why it matters: This is one of the most distinctive patterns in `~/fyth` and a
    good example of learned LLVM control-flow design.
  - Current priority: Deprioritized until the dictionary/schema/layout abstractions
    settle. The execution shape is still valuable, but it should not drive the next
    round of structural decisions.
  - Distinct from existing labs: none of the current labs cover threaded interpreter
    dispatch or tail-called continuation threading.

- `terminator-rewrite-next-trampoline`
  - Title: Terminator rewrite for next-step trampolines
  - Goal: Capture the pattern where generated functions are post-processed by
    replacing their terminator, appending a `next` block, and tail-calling a shared
    continuation.
  - Source in `~/fyth`: start from `src/fyth/forth_base.py`, especially the history
    around commits `bf07ecd` and `7945486`.
  - What to mine: this is CFG surgery after function emission so existing generated
    bodies all rejoin a common `next` trampoline; do not restate it as generic
    "tail-call helper" code.
  - Why it matters: This is an unusual but concrete technique for retrofitting a
    common continuation onto existing emitted functions.
  - Current priority: Keep behind the schema/dictionary abstraction work. It is more
    useful once the execution model is ready to stabilize.
  - Distinct from existing labs: it is not the same as delayed export or generic tail
    calls; it is specifically about CFG rewriting after function generation.

- `alignment-bit-tricks-vs-branch-phi`
  - Title: Alignment bit tricks versus branch-plus-phi
  - Goal: Capture the shift from a branchy alignment calculation to the compact
    bit-mask form `(index + 3) & -4`.
  - Source in `~/fyth`: start from `src/fyth/memory.py`, especially the history
    around commit `0e3e942`.
  - What to mine: the interesting part is the learned lowering step from branchy
    alignment logic into compact arithmetic, not just the final formula by itself.
  - Why it matters: It is a small but real lowering insight that likely came from
    experimentation rather than formal compiler training.
  - Distinct from existing labs: this is a low-level address arithmetic pattern, not a
    control-flow or lifecycle pattern.

## In Progress

- `generated-layout-wrapper-convention`
  - Title: Generated layout wrapper convention
  - Goal: Capture the convention where the generated layout core is marked `DO NOT
    EDIT` and a neighboring hand-authored wrapper is the intentional place to add
    ergonomic naming and helper methods.
  - Why it matters: Agents and humans need a clear edit boundary once generated layout
    files become normal package infrastructure.
  - Lab target: `explorations/lab/generated-layout-wrapper-convention/`

## Done

- `lowered-handler-python-loop-seam`
  - Title: Lowered handler Python loop seam
  - Goal: Show the smallest useful seam where Python owns dispatch but one handler is
    lowered and mutates shared host-visible state.
  - Why it matters: The next phase of interpreter work needs a slow lowering path
    that does not immediately collapse visibility into a native dispatch engine.
  - Takeaway: A good first seam is to lower `HALT`, let native code set a halt bit in
    shared state, and let the Python loop decide what that means after the native call
    returns. Use `HandlerRequirements` to inject lowered op surfaces and let the
    wrapper, not the local op body, own `ret`.
  - Lab: `explorations/lab/lowered-handler-python-loop-seam/`

- `handler-requirements-python-loop`
  - Title: HandlerRequirements-driven Python loop
  - Goal: Show a tiny Python interpreter loop wiring package metadata into
    inline-thread words, arithmetic kernels, `DOCOL`, and a tiny compile-to-thread
    path without pretending the final runtime or lowering path is settled.
  - Why it matters: The repo now has family metadata, associated-data-source
    metadata, and `HandlerRequirements`; this lab makes that trio executable and easy
    to inspect.
  - Takeaway: Treat family as semantic grouping, associated-data source as the
    runtime data-location clue, and `HandlerRequirements` as the concrete injection,
    cursor/jump, and preflight contract for local handler bodies.
  - Lab: `explorations/lab/handler-requirements-python-loop/`

- `python-shared-stack-kernels`
  - Title: Python shared stack kernels
  - Goal: Show the requested JonesForth-style primitive-empty words in a pure Python
    lab that stays grouped by requested operation type while routing repeated behavior
    through shared kernels.
  - Why it matters: The repo now has a concrete synthesis of primitive stack shapes,
    and this lab makes the reuse boundary visible without flattening the source into
    one kernel-centric file.
  - Takeaway: Keep the reader-facing source split aligned with the requested Forth
    operation groups, but still lower repeated behavior through a smaller set of
    shared kernels backed by explicit Forth-name metadata.
  - Lab: `explorations/lab/python-shared-stack-kernels/`

- `dictionary-construction-abstractions`
  - Title: Dictionary construction abstractions
  - Goal: Refine the pure Python + ctypes dictionary runtime into cleaner word
    creation, offset derivation, lookup/tracing, and IR-side helper boundaries before
    any execution machinery is layered on top.
  - Why it matters: The dictionary data model and helper boundaries needed to settle
    before threaded execution work could land cleanly.
  - Success signal: The package exposes a stable dictionary contract, the pure Python
    runtime preserves the real layout and lookup rules, the IR-side module can create
    and find words against that same layout, and the linked-list/name-region patterns
    are captured in labs.
  - Takeaway: Settle the dictionary as one contract across schema, runtime, layout,
    and IR helpers before introducing execution; newest-first traversal, canonical
    `CodeField` metadata, and explicit CFA/DFA helpers make the later interpreter work
    much simpler.
  - Package: `src/fythvm/dictionary/runtime.py`, `src/fythvm/dictionary/ir.py`,
    `docs/dictionary-contract.md`
  - Labs: `explorations/lab/ctypes-dictionary-runtime/`,
    `explorations/lab/variable-word-entry-layout/`,
    `explorations/lab/previous-link-list-ir-abstractions/`

- `nested-schema-family-generation`
  - Title: Nested schema family generation
  - Goal: Generalize schema-driven layout generation so nested struct families are
    discovered from declared roots instead of maintained as a hand-curated flat list.
  - Why it matters: The dictionary package now depends on schema-driven generation, so
    nested families needed to become generic rather than manually curated.
  - Success signal: The schema declares roots, derives the full struct family
    generically, and the dictionary layout generator consumes that derived family.
  - Takeaway: Let the schema own the family boundary; generation should walk nested
    structs from declared roots instead of duplicating the family by hand.
  - Package: `src/fythvm/dictionary/schema.py`, `scripts/generate_dictionary_layout.py`

- `logical-bitfield-views`
  - Title: Logical bitfield views over physical storage
  - Goal: Add named logical accessors over packed storage fields such as `CodeField`
    instead of stopping at the physical storage-unit view.
  - Why it matters: The generated layout layer now needs to expose pleasant logical
    field access without lying about the underlying packed storage.
  - Success signal: Promoted `BitField` / `BoundBitField` descriptors exist in package
    code, generated dictionary layout views expose logical `CodeField` accessors, and
    the generated accessors are covered by tests.
  - Takeaway: Keep physical storage explicit, but generate logical bitfield views on
    top of it when the schema is already authoritative.
  - Package: `src/fythvm/codegen/structs.py`, `src/fythvm/dictionary/layout.py`

- `ctypes-composite-runtime-layout`
  - Title: ctypes composite runtime layout
  - Goal: Show how the fixed runtime records from `~/fyth` map into nested ctypes
    structs, arrays, pointers, and promoted llvmlite struct views.
  - Why it matters: The fixed-record half of the old runtime is a clean fit for
    promoted struct helpers, but that relationship needed to be demonstrated
    explicitly.
  - Success signal: The lab prints the concrete ctypes layouts, emitted IR for raw and
    Pythonic nested access, and live proof against real ctypes instances.
  - Takeaway: Fixed runtime records are a good fit for promoted StructHandle views;
    nested structs, arrays, and pointers still reduce to ordinary field and element
    access once the layout is explicit.
  - Lab: `explorations/lab/ctypes-composite-runtime-layout/`

- `variable-word-entry-layout`
  - Title: Variable word entry layout
  - Goal: Show how a dictionary word uses variable-size name bytes before a fixed word
    prefix and derives CFA/DFA cells from the aligned name blob.
  - Why it matters: The real dictionary entry is not a plain fixed struct, so the
    variable-layout protocol needs to be preserved directly.
  - Success signal: The lab prints raw offset reconstruction, the corresponding
    Pythonic word view, lookup traces, and a memory snapshot.
  - Takeaway: Treat the word entry as a linear-memory protocol: variable name blob
    first, fixed prefix second, and explicit byte-to-cell transitions at the CFA/DFA
    boundary.
  - Lab: `explorations/lab/variable-word-entry-layout/`

- `ctypes-dictionary-runtime`
  - Title: ctypes dictionary runtime
  - Goal: Demonstrate the integrated pure Python + ctypes dictionary runtime for
    debug-visible word creation, traversal, and lookup.
  - Why it matters: The project needed a visibility-friendly runtime prototype before
    any execution machinery is layered on top.
  - Success signal: The lab prints the actual Python classes, live traversal and
    lookup behavior, and the runtime debug snapshot.
  - Takeaway: A pure Python + ctypes dictionary is a useful long-lived debug runtime
    as long as it preserves the real layout and lookup rules.
  - Lab: `explorations/lab/ctypes-dictionary-runtime/`

- `previous-link-list-ir-abstractions`
  - Title: Previous-link list IR abstractions
  - Goal: Rebuild the old `~/fyth` linked-list helper shape around a node convention
    of `[previous link][data...]`, and show the modern boundary between raw emission
    and a small traversal helper.
  - Why it matters: The dictionary is now explicitly a newest-first linked list, so
    the IR/codegen side needs a clear place to own the previous-link node convention
    without hiding the traversal CFG.
  - Success signal: The lab emits raw and helper-based append/count/get-nth functions,
    proves they produce identical memory, and captures the null-sentinel and
    offset-minus-one-cell failure modes explicitly.
  - Takeaway: Let the helper own the node convention and loop scaffolding; keep the
    actual previous-link traversal shape visible.
  - Lab: `explorations/lab/previous-link-list-ir-abstractions/`

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

- `llvmlite-mem-intrinsics`
  - Title: llvmlite mem intrinsics
  - Goal: Show the exact `llvmlite` pattern for declaring and calling LLVM
    `memcpy`, `memmove`, and `memset` intrinsics directly.
  - Why it matters: The builder has no convenience helpers for these intrinsics in the
    installed llvmlite, so the real declaration and call shape needs to be captured
    explicitly.
  - Success signal: The lab prints emitted intrinsic declarations and demonstrates
    working `memcpy`, overlapping `memmove`, and `memset` behavior against live
    `ctypes` buffers.
  - Takeaway: Use `Module.declare_intrinsic(...)` plus a normal call with the trailing
    `i1 isvolatile` argument; the memory intrinsics are supported, just not wrapped by
    IRBuilder helper methods.
  - Lab: `explorations/lab/llvmlite-mem-intrinsics/`

- `llvmlite-struct-machinery`
  - Title: llvmlite struct machinery
  - Goal: Show how literal versus identified structs, packed layout, field GEPs, and
    host-visible ctypes bridging actually work in llvmlite.
  - Why it matters: Several labs already depend on structs, but the struct machinery
    itself was still implicit and easy to misunderstand.
  - Success signal: The lab prints emitted IR, concrete ABI layout summaries, live
    ctypes-visible proof for literal/identified/packed structs, and captures the
    identified-struct packed-layout limitation explicitly.
  - Takeaway: Literal versus identified mostly changes naming and body-definition
    style; packed layout changes ABI offsets and size, and the host bridge must match
    that packedness exactly.
  - Lab: `explorations/lab/llvmlite-struct-machinery/`

- `ctypes-struct-reification`
  - Title: ctypes struct reification
  - Goal: Start from real `ctypes.Structure` declarations and reify the correct
    llvmlite layout plus a named bound view, including real ctypes bitfields.
  - Why it matters: Once ctypes declarations already exist, re-declaring the same
    shape by hand in llvmlite is repetitive and easy to get subtly wrong.
  - Success signal: The lab prints the ctypes declarations, the reified
    logical-to-physical mapping, emitted IR, matching layout summaries, and live proof
    that grouped bitfield storage works from both the host and JIT side.
  - Takeaway: Treat ctypes as the layout source of truth, reify physical storage
    first, and build logical named field views over that storage instead of pretending
    bitfields are standalone LLVM struct members.
  - Lab: `explorations/lab/ctypes-struct-reification/`

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

- `context-struct-stack-storage`
  - Title: Context-struct-backed stack storage
  - Goal: Make the abstract stack-op layer explicit and show concrete emitters that
    derive stack pointers from module globals, pointer globals, or context-struct
    fields.
  - Why it matters: This matches the direction the older `~/fyth` stack/layout code
    was already taking once stacks lived inside a larger runtime context.
  - Success signal: The lab shows one raw context-struct source-of-truth emitter plus
    Pythonic subclasses for all three storage strategies, and all variants produce the
    same stack trace.
  - Takeaway: Keep stack semantics in one abstract emitter layer and let concrete
    subclasses own only the IR pointer derivation for their storage layout.
  - Lab: `explorations/lab/context-struct-stack-storage/`

- `cell-rpn-calculator`
  - Title: Raw-cell RPN calculator
  - Goal: Interpret tagged 16-bit cells through one loop-carried instruction pointer,
    one context-backed stack, and one explicit `{status, result}` exit contract.
  - Why it matters: It turns the stack and phi learnings into a real but still tiny
    machine instead of another isolated primitive.
  - Success signal: The lab runs both raw and Pythonic evaluator variants, handles
    `+ - * / % =`, and shows matching success and failure traces for raw cell
    programs.
  - Takeaway: Keep the program as raw cells, the stack in a passed context, and the
    exit contract explicit; let the Pythonic layer remove only repetitive pointer,
    dispatch, and exit bookkeeping.
  - Lab: `explorations/lab/cell-rpn-calculator/`

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

- `block-parameter-joins`
  - Title: Block parameter joins
  - Goal: Capture the general phi model where successor blocks conceptually take
    arguments and LLVM lowers those block parameters into phis at block entry.
  - Why it matters: The useful abstraction is not "a ternary with a phi" but
    "threading block-entry state through joins, continuations, and loop headers."
  - Success signal: The lab demonstrates `select` as the no-join degenerate case, a
    zero-live-in CFG join, a multi-value tuple join, and a named-state wrapper over
    the same phi lowering.
  - Takeaway: Treat phis as lowered block parameters: predecessors contribute edge
    values, and the join block reconstructs its entry environment one field at a time.
  - Lab: `explorations/lab/block-parameter-joins/`

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
  - Takeaway: Use thin helpers for repeated branch/phi and `icmp`/`select` lowering,
    but stop before helper composition starts hiding the CFG or making comparison
    classification look like a performance story.
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
    safe reopen-by-name for continued emission, body emission later, and explicit
    finalization as the moment exports become callable.
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

- `loop-carried-traversal-phis`
  - Title: Loop-carried traversal phis
  - Goal: Capture the linked-list traversal shape from `~/fyth` where one phi carries
    the loop cursor and another phi carries derived state like a count.
  - Why it matters: This is a stronger phi pattern than a simple branch/merge because
    it shows phis as loop-carried state in traversal code.
  - Success signal: The lab demonstrates traversal with a cursor phi, an accumulator
    phi, and at least one early-exit or derived-result case that makes the carried
    state visible.
  - Takeaway: Keep the traversal cursor phi separate from derived loop state, and use
    a distinct exit-result phi when the search answer is not the cursor itself.
  - Lab: `explorations/lab/loop-carried-traversal-phis/`

- `result-carrier-phi-sentinels`
  - Title: Result-carrier phi with sentinel values
  - Goal: Show the comparison/search shape where a phi returns either a meaningful
    result or a sentinel such as `-1`.
  - Why it matters: `~/fyth` used this in byte and word comparison paths, and it is a
    real learned-by-doing pattern for compact loop results.
  - Success signal: The lab shows a loop or staged comparison whose final phi carries
    either a useful result or a sentinel, and explains why that is cleaner than
    branching out to separate return blocks.
  - Takeaway: Use a final result phi when a search has one semantic answer and a clear
    sentinel contract, including multi-stage early-exit searches where several checks
    converge on one exit block.
  - Lab: `explorations/lab/result-carrier-phi-sentinels/`

- `musttail-chunked-memory-ops`
  - Title: `musttail` chunked copy and compare
  - Goal: Rebuild the abandoned `test_memory2.py` experiments that implemented copy
    and compare through chunked tail recursion over 8-byte, 4-byte, then 1-byte cases.
  - Why it matters: This is unusually low-level IR work that clearly came from
    experimentation and is not represented anywhere in the current labs.
  - Success signal: The lab demonstrates one or both chunked memory operations,
    explains the `musttail` constraints, and makes the chunk-selection logic and tail
    recursion shape visible in the emitted IR and output.
  - Takeaway: Treat `musttail` as a strict contract for chunked recursive helpers, not
    as a casual optimization hint.
  - Lab: `explorations/lab/musttail-chunked-memory-ops/`

## Icebox

None.
