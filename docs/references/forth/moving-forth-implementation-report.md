# Moving Forth Implementation Report

This report explains what Brad Rodriguez's first four "Moving Forth" articles are
actually teaching, what Forth implementation they imply, and what is most relevant to
`fythvm`.

Files referenced here:

- [Moving Forth: Part 1](/Users/manny/fythvm/docs/references/forth/moving1.md:1)
- [Moving Forth: Part 2](/Users/manny/fythvm/docs/references/forth/moving2.md:1)
- [Moving Forth: Part 3](/Users/manny/fythvm/docs/references/forth/moving3.md:1)
- [Moving Forth: Part 4](/Users/manny/fythvm/docs/references/forth/moving4.md:1)

## Executive Summary

These four articles are not a finished Forth source listing. They are a design manual
for building one.

The concrete implementation center is a 16-bit Forth on small CPUs, especially a 6809
kernel used as the main worked example. Around that, Rodriguez compares what changes on
an 8051, a Z80, and other architectures. The series is really teaching a method:

- choose a Forth cell model first
- choose a threading model that fits the CPU
- assign the classical Forth virtual registers onto real CPU resources
- benchmark a small but representative set of kernel words
- make the code field / parameter field contract explicit
- only then decide how the system should be built for the first time

The most important takeaway is that a Forth kernel is defined less by surface syntax
than by a small set of runtime invariants:

- how threads are represented
- what `NEXT`, `ENTER`, and `EXIT` do
- how the current word's parameter field is recovered
- how data and return stack discipline map onto the target CPU
- how defining words manufacture new dictionary entries with shared code-field actions

That makes "Moving Forth" especially useful for `fythvm`, because those are exactly the
boundaries where our own code has been converging:

- explicit threaded control-flow rather than implicit call/return
- named code/data layout projections
- stack semantics separated from storage/layout
- dictionary entries understood as protocol plus shared behavior

## 1. What The Series Is Really About

Part 1 frames the task as porting or creating a Forth kernel on a new CPU, not as
writing application-level Forth code
([moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:15),
[moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:17)).

That matters because the series is solving a lower-level problem than JonesForth:

- JonesForth shows one complete Linux/i386 system
- Moving Forth teaches how to choose the runtime model before the full system exists

So the subject is not "here is my finished Forth." It is:

- what decisions define a Forth kernel
- how those decisions interact with real hardware
- how to evaluate them without writing the whole system several times

That is why the articles spend so much time on:

- threading alternatives
- virtual register allocation
- benchmarks for a tiny primitive subset
- code field / parameter field semantics
- assembler vs metacompiler bootstrapping

## 2. The Forth Model Rodriguez Is Assuming

The assumed baseline is a conventional 16-bit Forth kernel, usually on 8-bit CPUs
([moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:23),
[moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:37)).

That implies:

- 16-bit cells
- 16-bit addresses in the high-level thread
- a classical dual-stack Forth model
- a runtime organized around a small set of virtual registers

Part 1 names the classical Forth registers and their relative importance:

- `W`
- `IP`
- `PSP`
- `RSP`
- optional scratch register(s)
- sometimes a top-of-stack register

([moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:216),
[moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:226))

This is a key point: Rodriguez is not starting from a parser or a compiler. He is
starting from the execution substrate. The language grows on top of that substrate.

## 3. Threading Is The First Big Decision

Part 1 treats threading technique as the first major design choice
([moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:39)).

The series walks through:

- Indirect Threaded Code (ITC)
- Direct Threaded Code (DTC)
- Subroutine Threaded Code (STC)
- Token Threaded Code (TTC)
- segment-threaded variants for 8086-family concerns

### ITC

ITC is presented as the classical model:

- thread cells contain CFA addresses
- `NEXT` fetches the CFA through `IP`
- then fetches the code address through `W`
- code-field actions for colon definitions eventually redirect `IP` into the body

([moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:43),
[moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:56))

The conceptual benefit is uniformity:

- every word has a one-cell code field
- colon definitions are just lists of cells
- the representation is elegant and easy to reason about

The cost is the extra indirection in `NEXT`
([moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:94)).

### DTC

DTC removes one indirection by making the code field contain machine code or a machine
branch to shared code
([moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:100)).

This:

- speeds `NEXT`
- typically increases per-word size
- makes "how do I recover the PFA?" a CPU-specific issue

Rodriguez recommends DTC for most new kernels
([moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:122)).

### STC

STC discards the explicit interpreter pointer and represents colon definitions as
literal CPU call sequences
([moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:132)).

The key advantage is architectural:

- no `IP` register is needed

That is why STC becomes attractive on cramped CPUs like the 8051
([moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:151),
[moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:251)).

### TTC

TTC is framed as the size-minimizing option:

- thread holds compact tokens
- a dispatch table maps tokens back to words
- speed is sacrificed for space

([moving1.md](/Users/manny/fythvm/docs/references/forth/moving1.md:196))

### The Real Lesson

The real lesson is not "always choose DTC." It is:

- threading is a hardware fit problem
- the right answer depends on addressing modes, call/return overhead, available
  registers, and memory pressure

That perspective maps directly onto our exploration style: do not pick the abstraction
first and hope the machine likes it.

## 4. `NEXT`, `ENTER`, And `EXIT` Define The Core Runtime

Part 2 reduces the kernel to a benchmarkable essence:

- `NEXT`
- `ENTER` / `DOCOL`
- `EXIT`
- `DOVAR`
- `DOCON`
- `LIT`
- core stack/memory/arithmetic primitives

([moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:17),
[moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:55))

That is one of the most useful things in the series. It says:

- you do not need a whole Forth to evaluate the kernel shape
- you need a small set of words that expose the main tradeoffs

This is also close to how `fythvm` has evolved:

- first get the loop / join / stack / exit machinery right
- then build richer runtime structure on top

## 5. The 6809 Worked Design

The 6809 is Rodriguez's main positive case study
([moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:57)).

Why it fits Forth well:

- two hardware stack pointers
- multiple address registers
- orthogonal addressing modes
- decent 16-bit support on an 8-bit machine

([moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:59))

Initial register mapping:

- `X = W`
- `Y = IP`
- `S = RSP`
- `U = PSP`

([moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:81),
[moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:83))

The initial design pressure favors DTC because on the 6809:

- `NEXT` can be a single instruction

([moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:85),
[moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:97))

That is a powerful reminder that "inner interpreter" cost dominates enough that one
instruction in `NEXT` can decide the shape of the system.

## 6. Benchmark-Driven Register Decisions

Part 2 is strongest when it turns vague design advice into micro-benchmarks.

The 6809 case study shows:

- some words are neutral between TOS-in-register and TOS-in-memory
- stack operators and arithmetic often benefit from TOS in register
- memory-reference words can get slightly worse when top-of-stack is not already an
  address register

([moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:154),
[moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:179),
[moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:220))

The important design lesson is not the exact 6809 result. It is:

- benchmark words should be chosen to expose specific tradeoffs
- performance comes from the interaction of stack representation, memory access, and
  register assignment
- top-of-stack caching is not universally good or bad; it changes which operations get
  cheaper

This is very close to how our newer `rpn16` and stack code evolved:

- promote semantic operations (`push`, `pop2`, `peek`)
- then isolate the remaining shape predicates
- then bind those operations to the active builder and context view

The spirit is the same: make the real cost centers explicit.

## 7. The 8051 Case Study Shows When The Machine Wins

The 8051 case study is valuable because it forces a non-ideal answer.

Rodriguez says the 8051 is harsh for Forth because:

- only one general-purpose address register exists
- arithmetic is accumulator-centric
- the hardware stack is tiny and awkward for full Forth use

([moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:243))

So the implementation direction changes:

- use the program counter as the effective thread mechanism
- prefer STC because there is no realistic `IP` register to spare
- accept single-task limitations rather than paying huge per-word penalties

([moving2.md](/Users/manny/fythvm/docs/references/forth/moving2.md:251))

This is a strong anti-dogma point:

- the CPU can force the design
- elegance is subordinate to workable constraints

That is exactly the kind of realism we should keep when deciding how far to mimic
traditional Forth execution structures in `fythvm`.

## 8. Part 3: The Most Important Conceptual Shift Is The Code Field Contract

Part 3 begins with an "oops" correction, but that correction is itself a major lesson.

Rodriguez realizes that his earlier 6809 DTC `ENTER` logic fails for `EXECUTE` because
it assumed the current CFA could be recovered from `IP`
([moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:11),
[moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:36)).

That leads to the general rule:

- if `NEXT` does not leave the word-being-executed address in a register, DTC code
  fields must use a call, not a jump

([moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:38))

This is exactly the kind of kernel invariant that is easy to get wrong if you reason
locally instead of systemically.

Then Part 3 broadens the discussion into the real conceptual center:

- every word body consists of a code field plus parameter field
- the code field selects a shared action
- the parameter field is interpreted according to that action

([moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:74),
[moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:88))

Rodriguez explicitly describes this in three equivalent ways:

- action + data
- subroutine call + in-line parameters
- one-method object + instance variables

([moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:78))

This is the deepest connection to the codebase here.

Our current work has converged on the same separation:

- layout/schema
- generated structural projection
- hand-authored wrapper
- semantics layered over storage

The vocabulary is different, but the move is the same.

## 9. `DOCON`, `DOVAR`, And `ENTER` Are Really Shared Field Interpreters

Part 3 walks through how shared actions like `DOCON`, `DOVAR`, and `ENTER` recover and
interpret the parameter field under ITC, DTC, and STC
([moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:113)).

That is useful because it makes the following explicit:

- different classes of words share the same code-field routine
- only the parameter payload differs between instances
- the threading model decides how the parameter field address reaches that routine

This is close in spirit to:

- generated `StructHandle` plus named `BoundStructView`
- logical bitfield views over storage-unit fields
- dictionary entries whose behavior depends on a fixed prefix plus variable payload

In other words, the series is not just about execution. It is also about how to
structure families of runtime records with shared behavior.

## 10. `DOES>` Matters Because It Makes New Classes Of Words Possible

Part 3 is nominally about `DOES>`, but its real contribution is the explanation of why
defining words are so powerful.

The important point is:

- the kernel comes with a small set of shared code-field routines
- but the programmer can create new defining words that produce new bodies with new
  shared actions

([moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:94),
[moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:107))

That is a useful conceptual bridge for future `fythvm` work:

- dictionary entries are not just data blobs
- they are data plus a shared behavioral interpretation path

We should not copy the exact mechanism blindly, but the separation is worth keeping in
mind.

## 11. CODE Words Are The Exception That Proves The Rule

Part 3 also highlights that CODE words are special:

- their machine code is the payload
- they do not need the parameter field passed as data
- in DTC/STC the code field and body boundary effectively collapses

([moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:245))

This is important because it prevents overgeneralization.

Not every word family fits a neat "shared routine interprets parameters" model. Some
families are just raw executable code. That distinction is worth preserving in our own
design thinking if we ever bridge dictionary entries to execution.

## 12. `CREATE` And `;CODE` Reveal How The Dictionary Grows

Toward the end of Part 3, Rodriguez starts answering the practical questions:

- how do you create a word with arbitrary parameter data?
- how do you assign it a chosen code-field action?
- how do you compile the action?

([moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:255))

The answer begins with:

- `CREATE` builds the new header and initial code field
- high-level Forth fills the parameter field
- `;CODE` transitions to machine code for the shared action

([moving3.md](/Users/manny/fythvm/docs/references/forth/moving3.md:265))

This is not yet a full dictionary report like JonesForth, but it is enough to show the
core model:

- defining words are dictionary construction programs
- the dictionary is not only storage, but storage with executable layout conventions

That dovetails strongly with the newer dictionary work in this repo.

## 13. Part 4 Is About Bootstrapping, Not Runtime Semantics

Part 4 changes level. It is not mainly about how the target Forth executes. It is
about how you build the target system for the first time
([moving4.md](/Users/manny/fythvm/docs/references/forth/moving4.md:13)).

Rodriguez contrasts:

- hand-building threaded definitions in assembler with `DW` lists
- using a metacompiler / cross-compiler from an existing host Forth
- writing a Forth in C

([moving4.md](/Users/manny/fythvm/docs/references/forth/moving4.md:15),
[moving4.md](/Users/manny/fythvm/docs/references/forth/moving4.md:31),
[moving4.md](/Users/manny/fythvm/docs/references/forth/moving4.md:58))

This matters because it clarifies that "implementation" has two layers:

- target runtime design
- host-side generation strategy

That distinction is directly relevant to how this repo has evolved:

- explorations establish the model
- generated layout files capture mechanical structure
- wrappers give the human-editable surface
- package code becomes the host-side authoring environment

Part 4's pro/con lists remain current in spirit:

- assemblers expose everything and match the target exactly
- metacompilers make the program easier to read and port
- C broadens portability but constrains low-level control

([moving4.md](/Users/manny/fythvm/docs/references/forth/moving4.md:35),
[moving4.md](/Users/manny/fythvm/docs/references/forth/moving4.md:46),
[moving4.md](/Users/manny/fythvm/docs/references/forth/moving4.md:60))

## 14. So What Forth Is Actually Being Implemented?

The best answer is:

- a family of small, conventional, 16-bit Forth kernels
- with the 6809 version as the most concrete worked design
- and with CPU-specific adaptations for machines like the 8051 and Z80

It is not yet one final named system with complete source in these four files.

The concrete implementation direction by the end of Part 3 is roughly:

- conventional dual-stack Forth
- 16-bit cells on 8-bit hardware
- a benchmark-driven kernel core
- code-field / parameter-field bodies
- defining words built around `CREATE`
- shared code-field actions like `DOCON`, `DOVAR`, and `ENTER`
- 6809 design revised so the code-field call/jump strategy is consistent with
  `EXECUTE`

Part 4 then says the remaining open question is how to emit the finished system:

- assembler
- metacompiler
- or less desirably, C

So the "particular Forth" here is less like JonesForth's final system and more like a
carefully reasoned kernel blueprint.

## 15. What Is Most Relevant To `fythvm`

Several themes line up strongly with how `fythvm` has already evolved.

### a. Runtime invariants first

The series starts with:

- threading
- register allocation
- stack discipline
- field-address recovery

before it worries about user-facing syntax or compiler niceties.

That is the right order for us too.

### b. Shared action plus payload is the right mental model

The code-field / parameter-field explanation in Part 3 is one of the clearest old
Forth articulations of:

- fixed structural prefix
- shared interpretation path
- per-instance payload

That is highly relevant to:

- dictionary word prefixes
- code-field flag views
- generated layout plus hand-authored wrappers

### c. Benchmark the kernel, not the whole dream

Part 2's benchmark mindset is valuable:

- evaluate a minimal kernel subset
- expose real cost centers
- do not wait for a whole interpreter to learn whether the core shape is wrong

That is already consistent with the lab-heavy development style here.

### d. Execution design should stay subordinate to data/layout clarity for now

The series does contain execution machinery, but even here the strongest lessons for
the current repo are about:

- explicit runtime structure
- recovering the right payload from the right prefix
- making system invariants consistent across all entry paths

That supports the current choice to prioritize data structures and abstractions before
full execution.

## 16. Where Moving Forth Differs From JonesForth

These references complement each other well because they answer different questions.

JonesForth gives:

- one explicit, complete system
- one dictionary format
- one threaded runtime
- one self-hosted growth path

Moving Forth gives:

- the design space that leads to a system like that
- hardware-sensitive tradeoffs
- why `NEXT`, `ENTER`, and code-field conventions look the way they do
- how you might build the first version on a new CPU

So:

- JonesForth is a concrete artifact
- Moving Forth is a kernel design manual

## 17. Recommended Takeaways

If we are going to use these articles as design references, the main takeaways should
be:

1. Treat threading choice as a real architectural decision, not inherited folklore.
2. Make the contracts around current-word identity, CFA/PFA recovery, and entry paths
   explicit.
3. Keep shared-action-plus-payload as a first-class design idea.
4. Benchmark a small primitive subset before committing to wider execution machinery.
5. Keep host-side generation strategy separate from target runtime design.

Those are the parts of "Moving Forth" that have aged best and map most cleanly onto
what `fythvm` is becoming.
