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

## Icebox

None.
