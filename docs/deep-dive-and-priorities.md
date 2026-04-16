# fythvm Deep Dive And Priorities

This document captures what the repo has learned so far, how the code has evolved,
and what should be prioritized next.

It is intentionally broader than `explorations/BACKLOG.md`. The backlog is a useful
queue for experiments, but the repo has now crossed the point where the main question
is no longer "what can we explore?" It is increasingly "what have we already proven,
what has been promoted successfully, and what should the package architecture
stabilize around?"

## Executive Summary

The biggest story in `fythvm` is the shift from isolated llvmlite experiments toward
real reusable package code.

The repo now has:

- a coherent promoted codegen layer in [src/fythvm/codegen](/Users/manny/fythvm/src/fythvm/codegen/__init__.py:1)
- a real schema-driven dictionary package in [src/fythvm/dictionary](/Users/manny/fythvm/src/fythvm/dictionary/__init__.py:1)
- a real calculator implementation in [src/fythvm/rpn16.py](/Users/manny/fythvm/src/fythvm/rpn16.py:1)
- an exploration set that is no longer just random probes, but a provenance record
  for package design decisions
- automatic exploration smoke coverage through pytest

The highest-value work now is not "more execution tricks" and not "more low-level
intrinsic trivia." The highest-value work is:

1. stabilize schema -> generated layout -> hand-authored wrapper conventions
2. refine dictionary construction and lookup abstractions
3. make the promoted codegen layer more uniform around struct-aware views and schema
4. codify architectural rules so future work promotes cleanly instead of accreting
   one-off emitters
5. delay real Forth execution work until the data model and generation boundaries are
   settled

## What The Repo Has Learned

### 1. The end-to-end llvmlite pipeline is no longer the hard part

The basics are now well understood:

- configure LLVM once
- build IR
- verify
- compile through MCJIT
- bridge to host through `ctypes`

That path has been captured repeatedly and is no longer the main source of risk.
Representative explorations include:

- [llvmlite-minimal-jit-pipeline](/Users/manny/fythvm/explorations/lab/llvmlite-minimal-jit-pipeline/README.md:1)
- [llvmlite-ir-to-ctypes-bridge](/Users/manny/fythvm/explorations/lab/llvmlite-ir-to-ctypes-bridge/README.md:1)
- [llvmlite-host-symbol-exposure](/Users/manny/fythvm/explorations/lab/llvmlite-host-symbol-exposure/README.md:1)
- [llvmlite-module-lifecycle-pattern](/Users/manny/fythvm/explorations/lab/llvmlite-module-lifecycle-pattern/README.md:1)

This matters because it changes what should be treated as "infrastructure" versus
"open design." The pipeline itself is mostly infrastructure now.

### 2. The best abstractions are semantic, not convenience wrappers

The promoted codegen layer did not get better by hiding LLVM. It got better by naming
real semantic units:

- [Join](/Users/manny/fythvm/src/fythvm/codegen/joins.py:1)
- [ParamLoop](/Users/manny/fythvm/src/fythvm/codegen/loops.py:1)
- [SharedExit](/Users/manny/fythvm/src/fythvm/codegen/exits.py:1)
- [SwitchDispatcher](/Users/manny/fythvm/src/fythvm/codegen/dispatch.py:1)
- stack operations in [stack.py](/Users/manny/fythvm/src/fythvm/codegen/stack.py:1)
- struct access in [structs.py](/Users/manny/fythvm/src/fythvm/codegen/structs.py:1)

The pattern is consistent:

- explicit CFG is still visible
- mechanical builder noise gets reduced
- the abstraction boundary names the machine-level idea
- invalid lifecycle usage is increasingly rejected instead of tolerated

This is the right style for the repo.

### 3. Structs were more foundational than they first appeared

The struct work turned out not to be a side topic. It became one of the central
architectural pivots in the repo.

The progression was:

1. understand llvmlite struct machinery itself
2. understand ctypes-to-LLVM reification
3. promote a thin bound-view layer into package code
4. use schema as the source of truth
5. generate IR layouts from schema
6. add logical bitfield views over physical storage
7. add a wrapper convention for generated layout code

Important exploration milestones:

- [llvmlite-struct-machinery](/Users/manny/fythvm/explorations/lab/llvmlite-struct-machinery/README.md:1)
- [ctypes-struct-reification](/Users/manny/fythvm/explorations/lab/ctypes-struct-reification/README.md:1)
- [generated-layout-wrapper-convention](/Users/manny/fythvm/explorations/lab/generated-layout-wrapper-convention/README.md:1)

Important package outcomes:

- [StructHandle](/Users/manny/fythvm/src/fythvm/codegen/structs.py:165)
- [BitField](/Users/manny/fythvm/src/fythvm/codegen/structs.py:124)
- [dictionary/schema.py](/Users/manny/fythvm/src/fythvm/dictionary/schema.py:1)
- generated [dictionary/layout.py](/Users/manny/fythvm/src/fythvm/dictionary/layout.py:1)
- the generator at [scripts/generate_dictionary_layout.py](/Users/manny/fythvm/scripts/generate_dictionary_layout.py:1)

The lesson is that "layout projection" is not merely implementation detail. It is one
of the main stable boundaries in the project.

### 4. The real dictionary is a linear-memory protocol, not just a ctypes struct

This was a major clarification.

Fixed records from `~/fyth` map cleanly to ctypes structs and generated layouts.
Dictionary words do not. The dictionary word shape is fundamentally:

- linked linear memory
- variable-length name encoding
- fixed prefix after the variable-size name blob
- CFA/DFA derived from aligned byte math

That insight now exists in both exploration and package form:

- [variable-word-entry-layout](/Users/manny/fythvm/explorations/lab/variable-word-entry-layout/README.md:1)
- [ctypes-dictionary-runtime](/Users/manny/fythvm/explorations/lab/ctypes-dictionary-runtime/README.md:1)
- [src/fythvm/dictionary/runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:1)

This means future work should not try to "struct-ify" the whole dictionary. It should
keep fixed-record schema and variable word-entry protocol as different but connected
concepts.

### 5. A pure Python + ctypes runtime is not throwaway code

The pure Python + `ctypes` dictionary runtime is not just a temporary fake. It is a
valuable debug runtime.

Reasons:

- layout is real
- offsets are real
- traversal and lookup rules are real
- visibility is excellent
- tests can use it to pin down semantics before JIT emission exists

The repo should treat that runtime as a first-class debugging and semantic-reference
layer, not as scaffolding to discard once JIT execution appears.

### 6. The repo now has a real promotion path

The repo has effectively established a repeatable promotion pipeline:

1. isolate an idea in `explorations/`
2. keep a raw source-of-truth path visible
3. discover the minimal semantic abstraction
4. promote only the thin reusable part into `src/fythvm/codegen` or another package
   layer
5. keep the exploration as provenance and explanation
6. add smoke coverage so regressions become obvious

That is one of the most important things the repo has learned. It should be
documented and protected.

## How The Code Has Evolved

### Phase 1: exploration-first

The early focus was proving llvmlite and LLVM concepts directly:

- minimal JIT
- phi/joins
- host symbol exposure
- lifecycle
- stack storage
- mem intrinsics

This phase established confidence in the toolchain and basic control-flow patterns.

### Phase 2: local pattern extraction

The calculator and stack work began to expose recurring local shapes:

- loop header as block parameters
- shared status/result exits
- stack semantics over explicit storage
- declarative dispatch

At this point the repo started preferring "promote the real semantic primitive" over
"keep tidying this one emitter."

### Phase 3: package promotion

This is the most important architectural shift so far.

The repo added:

- [src/fythvm/codegen](/Users/manny/fythvm/src/fythvm/codegen/__init__.py:1)
- [src/fythvm/rpn16.py](/Users/manny/fythvm/src/fythvm/rpn16.py:1)
- [src/fythvm/dictionary](/Users/manny/fythvm/src/fythvm/dictionary/__init__.py:1)

That means the project is no longer exploration-only. It is now a real package with:

- internal reusable machinery
- concrete package-level consumers
- schema, generated layout, runtime, and test boundaries

### Phase 4: schema and generation become the center of gravity

The dictionary package pushed the repo toward a better architecture:

- `schema.py` is authoritative
- `layout.py` is generated
- `runtime.py` is hand-authored
- wrapper conventions are being explored explicitly

This is a stronger architectural direction than "one more emitter convenience helper."

### Phase 5: newer package code is pulling older abstractions upward

Recent changes show a clear cleanup vector:

- identified handle caching moved into [StructHandle.identified(...)](/Users/manny/fythvm/src/fythvm/codegen/structs.py:198)
- stack access became struct-aware through [StructViewStackAccess](/Users/manny/fythvm/src/fythvm/codegen/stack.py:140)
- `rpn16` stopped using raw field indices and now uses a named context view

This is exactly the kind of evolution the repo should continue: newer abstractions
should simplify older promoted code, not merely coexist beside it.

## What Is Working Well Now

### Package surfaces

The repo now has three reasonably coherent package-level surfaces:

- `fythvm.codegen`
- `fythvm.dictionary`
- `fythvm.rpn16`

That is enough structure to start talking about architecture instead of just labs.

### Test shape

The test story is now strong:

- metadata tests for explorations
- subprocess smoke for every exploration default run
- focused package tests
- integration-style package tests

This is a major asset. It means refactors can be bolder without turning reckless.

### Conventions that are becoming clear

Good conventions are emerging:

- promote narrow proven pieces
- keep generated files mechanical
- use wrappers for ergonomics
- prefer schema-authoritative generation
- keep runtime semantics visible
- avoid magic abstractions that obscure CFG or memory layout

These should be made even more explicit.

## Current Architectural Tensions

### 1. Some promoted code still reflects older abstraction eras

Examples:

- [ContextStructStackAccess](/Users/manny/fythvm/src/fythvm/codegen/stack.py:119) still exists and is valid, but the repo now clearly prefers struct-aware access
- some generated-vs-hand-authored layout conventions are still being tested rather
  than fully codified
- `rpn16` still contains some local hand-authored layout projection that would be
  generated in a larger system

This is not a problem, but it shows where cleanup energy should go.

### 2. Codegen and schema/generation are still separate stories

The repo now has:

- strong codegen primitives
- real schema-driven generation

But these are still somewhat adjacent rather than fully unified.

The main open architectural question is:

- how much of codegen should become schema-driven by default?

Not all of it should. But layout projection clearly should.

### 3. The public/internal boundary is still soft

`fythvm.codegen` is explicitly an unstable internal promotion layer. That is good.
But the repo still needs a clearer answer to:

- what package surfaces are intended for direct use?
- what is stable enough for other modules to depend on?
- what remains intentionally provisional?

This matters more now than it did when everything was still an exploration.

### 4. Execution work is tempting, but structurally premature

The repo now has enough ingredients that direct-threaded execution work is tempting.
But the dictionary/runtime/schema side is still evolving fast enough that execution
would likely drag abstractions into place prematurely.

The current restraint here is correct.

## Recommended Priorities

These priorities are not simply a restatement of the backlog. They are based on the
code’s actual trajectory.

### Priority 1: Codify the generated-layout architecture

This is the most important structural priority now.

The repo has already proven:

- schema-authoritative generation works
- generated core plus wrapper convention is useful
- bitfield/logical view generation works
- nested schema-family discovery works

What is still needed is to make this feel like an architecture, not a successful set
of examples.

Concrete work:

- add a repo-level design doc for schema/layout generation conventions
- define when a layout should be:
  - hand-authored
  - generated
  - generated plus wrapped
- define the naming rules for:
  - schema classes
  - generated handles
  - generated view classes
  - wrapper modules/classes
- define the regeneration workflow for humans and agents
- make the "DO NOT EDIT / EDIT THIS FILE" convention explicit and repeatable

Why this is first:

- it affects every future runtime/data-structure surface
- it reduces future architectural drift
- it makes agent work safer

### Priority 2: Refine dictionary construction abstractions

This is the most important runtime priority now.

The repo already has a good dictionary runtime foundation:

- [DictionaryRuntime](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:132)
- [WordRecord](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:94)
- [NameHeader](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:22)

But the next step is not execution. The next step is making construction and lookup
semantics cleaner and more composable.

Concrete work:

- separate word-creation planning from memory mutation
- introduce explicit creation/result records instead of ad hoc return bundles
- improve tracing and debugging APIs around lookup and traversal
- make offset derivation and name encoding helpers more composable
- clarify invariants around `here`, `latest`, hidden words, and data payload sizing

Why this is second:

- it directly affects the future interpreter
- it improves testability
- it strengthens the pure Python runtime as a semantic reference

### Priority 3: Unify struct-aware codegen usage across package consumers

The struct/view work is now mature enough that package consumers should converge on
one style.

Recent progress:

- [StructHandle](/Users/manny/fythvm/src/fythvm/codegen/structs.py:165)
- [StructViewStackAccess](/Users/manny/fythvm/src/fythvm/codegen/stack.py:140)
- named context view in [rpn16.py](/Users/manny/fythvm/src/fythvm/rpn16.py:159)

Concrete work:

- migrate remaining package consumers to struct-aware access where appropriate
- identify any older promoted helpers that still rely on raw indices or older style
- decide whether `ContextStructStackAccess` should remain as compatibility or become
  explicitly legacy
- consider whether more runtime/context helpers should take bound views instead of raw
  pointers

Why this is third:

- it reduces the number of parallel abstraction styles
- it keeps the promoted layer coherent
- it makes future schema-driven generation easier to apply to codegen consumers

### Priority 4: Turn repo conventions into explicit documentation

The repo now has enough conventions that undocumented behavior is becoming a risk.

Concrete work:

- document the promotion path from exploration to package code
- document codegen style:
  - semantic abstractions
  - honest CFG
  - where `goto_block(...)` helps and where it hurts
- document schema/layout/wrapper conventions
- document when to keep a pure Python + `ctypes` reference runtime
- document what kinds of experiments belong in `explorations/` versus `src/`

Why this matters:

- it reduces agent drift
- it reduces future refactor churn
- it helps preserve hard-won design choices

### Priority 5: Fill selective conceptual gaps, not random ones

There are still good exploration topics left, but they should be chosen to support the
architecture rather than just expand the lab catalog.

The current backlog already points at good examples:

- dictionary construction abstractions
- generated layout wrapper convention
- selected llvmlite intrinsic topics

But outside the backlog, the best exploration criterion should be:

- does this de-risk a structural package decision?

That is a better filter now than "is this a neat LLVM topic?"

## What Should Be Deprioritized

### 1. Full execution work

Keep direct-threaded `musttail` execution work behind the current priorities.

Reason:

- execution will pull on dictionary/runtime/schema/codegen boundaries all at once
- those boundaries are improving quickly right now
- forcing execution too early would likely create avoidable rewrites

### 2. Large generalized frameworks

The repo is doing well with narrow semantic primitives. It should continue to avoid:

- giant CFG DSLs
- giant schema meta-frameworks
- all-in-one runtime frameworks

The promotion style so far has been correct: narrow, proven, semantic.

### 3. Overfitting generated systems too early

Generation is becoming central, but it should not take over everything prematurely.

Not every local layout helper needs a generator immediately. For tiny local cases,
hand-authored projection is still fine, as noted in `rpn16`.

The right question is:

- is this layout truly schema-like and reused enough to deserve generation?

### 4. One-off low-level experiments with no architectural pull

The repo can still support them, but they should not dominate priorities now.

The project has moved beyond the stage where isolated low-level wins are the main
source of value.

## Concrete Next Steps

If the project wanted a strong near-term plan, this would be the recommended order:

1. Write and land a repo-level schema/layout generation design note.
   - Source of truth
   - generated output expectations
   - wrapper conventions
   - regeneration rules

2. Improve `fythvm.dictionary.runtime` around creation and traceability.
   - cleaner creation helpers
   - better lookup trace/reporting
   - explicit invariants

3. Audit `fythvm.codegen` for remaining older-style APIs and converge on struct-aware
   usage where it helps.

4. Tighten the generated-layout-wrapper convention from exploration into a package
   rule.

5. Only then decide whether the next major step is:
   - more dictionary abstraction work
   - a minimal execution bridge
   - or another schema-driven generated package surface

## A Practical Priority Order

If only a short list is needed:

1. schema/layout/wrapper architecture
2. dictionary construction and lookup abstractions
3. convergence on struct-aware codegen usage
4. explicit repo design documentation
5. selective supporting explorations
6. execution work later

## Final Take

The repo’s most important achievement is not any single lab. It is that `fythvm` now
has a believable architectural shape:

- explorations prove ideas
- package code promotes narrow semantic primitives
- schema defines layout
- generated code is mechanical
- wrappers add ergonomics
- pure Python + ctypes runtime remains a semantic reference

That is the direction to protect.

The best next work is the work that makes this shape clearer, more explicit, and more
repeatable. The wrong next work is anything that forces execution-centric decisions
before the structural pieces have fully settled.
