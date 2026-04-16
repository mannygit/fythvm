# Forth Implementation Alignment Report

This report is a synthesis of the two existing reference reports:

- [JonesForth Implementation Report](/Users/manny/fythvm/docs/references/forth/jonesforth/implementation-report.md:1)
- [Moving Forth Implementation Report](/Users/manny/fythvm/docs/references/forth/moving-forth-implementation-report.md:1)

The goal here is not just comparison. It is to build one decision-support document for
`fythvm` that shows:

- where JonesForth and Moving Forth clearly align
- where they diverge
- what those differences mean
- which parts look durable enough to adopt
- which parts should remain open decisions

This document should be read as a superset of the two underlying reports.

## Executive Summary

JonesForth and Moving Forth are highly aligned on fundamentals and different in
presentation level.

They agree on the deepest parts of traditional Forth implementation:

- Forth is defined by a small runtime substrate, not by surface syntax
- dual stacks matter
- dictionary entries are linked records with code/data structure
- colon definitions are runtime-managed threaded code, not ordinary host-language
  procedures
- `NEXT`, `DOCOL`/`ENTER`, and `EXIT` are the execution center
- defining words and shared code-field actions are a core abstraction, not a side
  feature
- the self-hosted layer grows after the substrate exists

They differ mainly in emphasis:

- JonesForth is a concrete Linux/i386 implementation
- Moving Forth is a kernel-design manual for fitting Forth onto many CPUs, especially
  8-bit machines

So:

- JonesForth shows one full answer
- Moving Forth explains how to choose among answers

For `fythvm`, the combined lesson is:

1. We should adopt the structural invariants they agree on.
2. We should treat threading, codeword shape, and bootstrap boundaries as explicit
   architectural decisions.
3. We should not copy JonesForth literally where Moving Forth makes clear that the
   right answer depends on runtime and tooling constraints.
4. The next work should now shift from basic dictionary/layout stabilization toward:
   - defining-word / word-family abstractions
   - explicit execution invariants
   - stack/runtime semantics that future executors must preserve
   while still deferring commitment to one execution form.

## 1. What Each Reference Is Good For

### JonesForth

JonesForth is best as:

- a concrete implementation reference
- a complete dictionary/runtime example
- a demonstration of one successful indirect-threaded, self-hosted Forth

Use it when the question is:

- what does a real finished system actually do?
- how are dictionary headers really laid out?
- how do `FIND`, `INTERPRET`, `CREATE`, `:`, and `;` fit together in one runtime?

### Moving Forth

Moving Forth is best as:

- a kernel-design manual
- a tradeoff guide
- a way to reason about "why this design and not another?"

Use it when the question is:

- which threading model should we prefer?
- what invariants does `NEXT` imply?
- how should code-field / parameter-field recovery work?
- how much of the design is machine-constrained?

### Combined Use

Together they provide:

- JonesForth: one strong answer
- Moving Forth: the framework for evaluating that answer

That combination is unusually useful. It means we can avoid:

- blindly copying JonesForth because it is concrete
- floating in abstraction because Moving Forth is generic

## 2. Strong Alignment: Runtime Substrate First

Both references agree that a Forth system starts with a runtime substrate, not with
syntax sugar.

JonesForth's assembly layer establishes:

- stacks
- `NEXT`
- `DOCOL`
- dictionary search
- parsing
- `INTERPRET`
- `CREATE`
- compile/execute state

before the larger self-hosted language grows
([jonesforth/implementation-report.md](/Users/manny/fythvm/docs/references/forth/jonesforth/implementation-report.md:1)).

Moving Forth starts even earlier, by saying the first real decisions are:

- cell model
- threading model
- register allocation
- benchmark primitives
- code-field contract

([moving-forth-implementation-report.md](/Users/manny/fythvm/docs/references/forth/moving-forth-implementation-report.md:1)).

This is a very strong alignment.

### Implication for `fythvm`

This supports the path the codebase has already taken:

- layout and schema before execution polish
- stack semantics before larger interpreters
- dictionary construction before code execution
- promoted codegen primitives before whole-program machinery

This is not procrastination from "real interpreter work." It is the same order these
systems say matters.

At this point in `fythvm`, much of that substrate-first work is no longer only a
direction. It exists:

- schema as source of truth
- generated layout projections
- an explicit runtime dictionary package
- an IR-side dictionary package layer
- a written dictionary contract

## 3. Strong Alignment: Dual-Stack Semantics Matter

JonesForth makes the dual-stack model explicit:

- data stack
- return stack for threaded control flow

It treats the return stack as part of the language/runtime contract, not an incidental
CPU detail.

Moving Forth treats `PSP` and `RSP` as classical virtual registers and makes their
placement a central design problem.

This is another strong alignment:

- a serious traditional Forth has two stacks
- return-stack discipline is part of the semantics
- execution structure depends on it

### Implication for `fythvm`

This does **not** mean `fythvm` must immediately implement a classic return-stack-based
executor.

It does mean:

- stack roles should remain explicit in the architecture
- even if execution is deferred, the design should leave room for data-stack and
  control/return-stack distinctions
- our runtime and dictionary work should avoid baking in assumptions that would later
  make a second stack awkward

## 4. Strong Alignment: Dictionary Entries Are Structured Runtime Records

JonesForth shows this concretely:

- link pointer
- flags/length byte
- name bytes
- alignment padding
- code/data area

Moving Forth explains the deeper abstraction:

- word body = code field + parameter field
- the code field chooses the shared action
- the parameter field carries the per-instance payload

These are two views of the same thing:

- JonesForth gives the concrete layout
- Moving Forth gives the conceptual contract

### Implication for `fythvm`

This is one of the most important combined lessons.

It validates the direction we have already moved toward:

- schema for fixed runtime records
- generated layout projections
- wrappers for ergonomic named access
- dictionary entries understood as structural protocol plus shared interpretation

This suggests a durable architecture:

1. fixed layout/schema layer
2. generated mechanical projection layer
3. hand-authored ergonomic wrapper layer
4. semantic/runtime layer

That architecture now has a strong historical justification behind it.

In `fythvm`, this is no longer hypothetical. The package is already close to this
shape:

- `dictionary.schema`
- generated `dictionary.layout`
- wrapper/edit conventions explored explicitly
- `dictionary.runtime`
- `dictionary.ir`

## 5. Strong Alignment: Defining Words Are Central

JonesForth demonstrates:

- `CREATE`
- codeword conventions
- compiled words that grow the dictionary
- later self-hosted defining behavior

Moving Forth makes the underlying mechanism explicit:

- shared code-field actions
- parameter payload determined by the defining word
- `DOES>` and defining words as the route to new word families

This is an especially important alignment because it means the dictionary is not just a
symbol table. It is a structured word-factory.

### Implication for `fythvm`

This argues strongly that future dictionary work should not stop at:

- append bytes
- link entries
- find by name

We should also think in terms of:

- word families
- shared code/data interpretation
- defining-word-like construction abstractions

Even before execution, this matters. It affects how we model:

- codefield flags
- payload start
- CFA/DFA derivation
- later execution metadata

## 6. Strong Alignment: Self-Hosting Is A Phase Boundary

JonesForth splits:

- machine substrate
- self-hosted growth

Moving Forth splits:

- kernel design
- bootstrap/build strategy

Again, the alignment is clear:

- there is a phase boundary between "minimal executable substrate" and "language grows
  itself"

### Implication for `fythvm`

This supports continuing to treat our work in stages:

- schema/layout/runtime substrate
- dictionary semantics
- minimal execution substrate
- then larger self-hosted or more expressive layers

Trying to collapse all of that into one phase would go against what both references
show works.

## 7. Important Deviation: JonesForth Gives One Runtime Answer, Moving Forth Says It Depends

This is the biggest difference.

JonesForth commits to one implementation:

- Linux/i386
- indirect threading
- one particular dictionary header shape
- one particular relationship between assembly kernel and self-hosted layer

Moving Forth says many of those choices are contingent:

- ITC vs DTC vs STC depends on the CPU
- code-field call vs jump depends on how CFA/PFA recovery works
- TOS-in-register depends on which primitives dominate
- even the build strategy depends on toolchain reality

### What This Means

JonesForth is authoritative about:

- one successful design

Moving Forth is authoritative about:

- the design space around that success

### Implication for `fythvm`

We should not let JonesForth's concreteness overrule the more general lessons from
Moving Forth.

In practice:

- JonesForth is excellent as a structural reference
- Moving Forth should usually win when deciding which parts are universal and which are
  environment-dependent

## 8. Important Deviation: JonesForth Is Execution-Centric, Our Current Codebase Is Layout-Centric

JonesForth is heavily execution-oriented:

- `NEXT`
- `DOCOL`
- `INTERPRET`
- `FIND`
- compile/execute loop

Moving Forth is also centered on execution substrate, even when it is teaching design
method.

`fythvm`, by contrast, has recently evolved toward:

- schema-driven layout
- generated layout code
- wrappers
- dictionary construction/runtime introspection
- stack and loop codegen abstractions

That is a real deviation.

### Is That Bad?

No. It is mostly a sequencing difference.

The references suggest the substrate matters first. Our current work has mostly been
about making the substrate *representable and manipulable* in a modern codegen/runtime
codebase before committing to full execution.

The key risk is only this:

- if we keep postponing execution indefinitely, we may preserve abstractions that look
  nice structurally but turn out awkward for a threaded runtime

So the practical conclusion is:

- keep prioritizing data/layout clarity now
- but evaluate future abstraction work against explicit execution invariants

## 9. Important Deviation: Bootstrapping Strategy

Moving Forth explicitly treats the build strategy as a design dimension:

- assembler
- metacompiler
- C

JonesForth effectively shows an assembly-kernel plus self-hosted-growth path.

`fythvm` is on a different host/tooling base:

- Python
- `ctypes`
- `llvmlite`
- generated Python layout code
- exploration-to-package promotion flow

This is a major tooling deviation, but it does not invalidate the reference material.

### Implication for `fythvm`

We should translate the bootstrap lesson, not copy the tool choices.

The modern equivalent in this repo is roughly:

- schema is the source of truth
- generators produce mechanical layout/codegen projections
- wrappers are the editable ergonomic layer
- package code is the host-side "metacompiler environment"
- labs are the proving ground

That is our practical bootstrap story.

## 10. Decision Areas For `fythvm`

The real value of combining these references is not historical admiration. It is giving
us a better list of decisions to make.

### A. Dictionary Entry Shape

What both references support:

- linked newest-first dictionary
- explicit flags
- explicit payload boundary
- hidden-word handling in lookup
- CFA/DFA-style derivation or equivalent code/data boundary helpers

What remains open for `fythvm`:

- exact fixed prefix shape
- exact flag packing
- whether code/data boundaries are cell-oriented, byte-oriented, or both
- how much of the classic naming/layout protocol to keep

Current recommendation:

- treat newest-first linked lookup and hidden-word skipping as settled invariants
- treat the current schema/layout/runtime/IR split as substantially established
- keep CFA/DFA-like helpers explicit rather than burying them
- stop treating basic dictionary structure as the main open problem

### B. Threading Model

What JonesForth says:

- ITC works and is conceptually clean

What Moving Forth says:

- DTC is often preferable
- STC can be the right answer on register-starved machines
- the answer depends on the target constraints

What this means for `fythvm`:

- we should not commit to a classic runtime threading model until we decide whether
  the target is:
  - literal machine-like threaded execution
  - JIT-emitted helper calls
  - tail-call / continuation style lowering
  - some hybrid

Current recommendation:

- treat threading as still open
- document the invariants any future execution model must satisfy:
  - explicit current-word identity
  - recoverable code/data payload boundary
  - explicit data and return/control stack roles
  - consistent `EXECUTE` semantics

### C. Shared Actions / Codefield Abstraction

What both references strongly support:

- shared per-family behavior is fundamental
- code/data split must be explicit
- defining words should create families, not only individual records

Current recommendation:

- continue evolving the dictionary toward first-class word-family abstractions
- keep logical views and payload derivation explicit
- avoid modeling words as mere names plus opaque blobs

### D. Self-Hosted Boundary

What both references support:

- the substrate should become visible enough that the language can manipulate it

What this implies for `fythvm`:

- package-level runtime records and dictionary operations should remain explicit
- future self-hosted or higher-level facilities should sit on top of them, not replace
  them

## 11. A Concrete Step-By-Step Decision Sequence

If the goal is to make the best decisions for `fythvm`, this is the order I would
recommend.

### Step 1: Lock down dictionary invariants

Decide and document:

- newest-first link semantics
- hidden-word lookup behavior
- fixed prefix fields
- code/data boundary helpers
- name encoding and alignment rules

Why:

- both references make dictionary invariants central
- this work is already underway in the codebase
- it will constrain later execution work productively

Current status in `fythvm`:

- substantially complete
- the dictionary contract is written
- the runtime and IR layers follow the same fixed-prefix and name-region model
- newest-first traversal and hidden-word skipping are already implemented

### Step 2: Lock down runtime record architecture

Decide and document:

- schema as source of truth
- generated layout as mechanical projection
- wrapper as editable ergonomic layer
- runtime package as semantic layer

Why:

- this is already emerging in `fythvm`
- it is our host-side equivalent of making the kernel substrate explicit

Current status in `fythvm`:

- substantially complete
- schema/layout/runtime separation exists
- generated layout is real package infrastructure
- wrapper conventions are being explored explicitly rather than ad hoc

### Step 3: Define the "word family" abstraction more explicitly

Decide:

- how a word's shared behavior is represented
- how payload interpretation is attached to that behavior
- where codefield-like metadata lives in the runtime/package model

Why:

- this is where JonesForth's concrete dictionary and Moving Forth's code-field theory
  meet most productively

Current status in `fythvm`:

- partially complete
- `instruction` already has a clear meaning as primitive dispatch selector
- native and later-defined words already share one dictionary contract
- but there is not yet a first-class package abstraction for named word families and
  their payload interpretation

### Step 4: Specify execution invariants before choosing execution form

Document what any execution strategy must preserve:

- current-word identity
- `EXECUTE` correctness
- data vs return/control stack roles
- explicit payload boundary access
- immediate/compile behavior, if and when compilation is added

Why:

- this prevents premature commitment to one runtime lowering style
- it also prevents layout abstractions from drifting away from what execution needs

Current status in `fythvm`:

- still needed
- pieces of the answer exist across the dictionary contract and the reference reports
- but there is not yet one focused execution-invariants document

### Step 5: Only then choose the first real execution shape

Possible candidates:

- classic threaded model
- JIT-tail-call/continuation model
- helper-call-based model
- mixed runtime

Use JonesForth for "what a finished system does" and Moving Forth for "what tradeoffs
this commits us to."

Current status in `fythvm`:

- correctly deferred

## 12. What Looks Durable Enough To Adopt Now

These look stable enough to treat as strong reference-backed direction:

- linked newest-first dictionary traversal
- hidden-word skipping during lookup
- explicit code/data boundary helpers
- dual-stack awareness in the architecture
- substrate-first development order
- shared-family behavior as a core design concept
- explicit bootstrap phase boundaries

In addition, the following now look stable enough in the actual codebase:

- schema as source of truth
- generated layout as mechanical projection
- runtime and IR dictionary layers consuming the same contract
- linked-list IR helpers and aligned name-region comparison as real package/lab
  patterns

## 13. What Should Remain Open

These should stay open a bit longer:

- exact execution threading model
- exact codeword representation in any future executor
- exact return stack runtime form
- degree of classic Forth compatibility in compile/interpret machinery
- how much of JonesForth's specific parser/compiler loop to emulate directly

These are the places where Moving Forth is especially important, because it keeps us
from prematurely inheriting JonesForth's specific implementation.

The practical meaning of that list has now changed. The main open architectural work is
no longer "what is the dictionary?" or "how should layout generation work?" It is:

- how to model word families explicitly
- what execution invariants any future engine must preserve
- and only then which execution form best fits the host/JIT environment

## 14. Bottom Line

If I compress the combined guidance from these references down to one line, it is:

Build `fythvm` around explicit runtime invariants and structured word families first,
then choose the execution mechanism that best preserves those invariants in our actual
host/JIT environment.

That is the center of alignment between JonesForth and Moving Forth, and it is the best
decision framework they offer us.
