# Handler Requirements

This document is the canonical helper/lowering-requirements contract for `fythvm`.

It defines:

- the declarative per-handler requirements layer
- stack ingress/egress requirements
- injected runtime and parse-time resources
- kernel lookup role
- the rule that continuation stays outside handler bodies

It does **not** define:

- runtime family semantics
- dictionary entry structure
- the core machine-state model

For those, see:

- [docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1)
- [docs/dictionary-contract.md](/Users/manny/fythvm/docs/dictionary-contract.md:1)
- [docs/execution-invariants.md](/Users/manny/fythvm/docs/execution-invariants.md:1)

## Core Contract

`HandlerRequirements` are declarative metadata attached to a concrete handler or
lowering entry point.

They do **not**:

- define a different runtime ABI
- imply different executor call shapes per family
- own continuation/dispatch mechanics

They do:

- describe required machine-state resources
- describe stack and return-stack preconditions
- describe required egress space
- support shared lowering-kernel selection
- let Python/IR lowering code stay declarative

## Intended Shape

The current intended shape is roughly:

```python
HandlerRequirements(
    min_data_stack_in=0,
    min_data_stack_out_space=0,
    min_return_stack_in=0,
    min_return_stack_out_space=0,
    needs_thread_cursor=False,
    needs_thread_jump=False,
    needs_execution_control=False,
    needs_current_xt=False,
    needs_return_stack=False,
    needs_input_source=False,
    needs_source_cursor=False,
    needs_error_exit=False,
    needs_dictionary=False,
    needs_here=False,
    needs_thread_emitter=False,
    needs_patch_stack=False,
    kernel=None,
)
```

This now exists in package code, though the exact field set may still evolve as more
execution shapes are exercised.

## Canonical Requirement Fields

### Stack Requirements

- `min_data_stack_in`
  - minimum data-stack depth required at handler ingress
- `min_data_stack_out_space`
  - output space required at egress
- `min_return_stack_in`
  - minimum return-stack depth required at handler ingress
- `min_return_stack_out_space`
  - output space required on the return/control stack

### Injected Runtime Resources

- `needs_thread_cursor`
  - the handler consumes inline data from the current thread through a cursor-like
    helper
- `needs_thread_jump`
  - the handler may redirect thread position through a jump/control helper
- `needs_execution_control`
  - the handler needs an execution-control surface for local actions like halt or
    return requests without owning the outer dispatch policy
- `needs_current_xt`
  - the handler recovers word-local data via `current_xt -> DFA`
- `needs_return_stack`
  - the handler needs direct return/control-stack access
- `needs_input_source`
  - the handler or compiler/meta word needs the low-level parse/input facility used by
    primitives like `KEY`, `WORD`, and `CHAR`
- `needs_source_cursor`
  - the handler or compiler/meta word needs a structured parse-time cursor
- `needs_error_exit`
  - the handler expects an error-exit facility
- `needs_dictionary`
  - the handler needs dictionary access
- `needs_here`
  - the handler needs the current dictionary write cursor
- `needs_thread_emitter`
  - the handler or compiler/meta word needs a higher-level definition/thread emitter
    that wraps `HERE`
- `needs_patch_stack`
  - the handler or compiler/meta word needs control-flow patch bookkeeping

This stays separate from runtime associated-data-source metadata.

## Associated-Data Source Versus Requirements

The runtime associated-data-source split is still:

- `NONE`
- `WORD_LOCAL_DFA`
- `INLINE_THREAD`

`HandlerRequirements` complements that split. It does not replace it.

The relationship is:

- family metadata says what runtime semantics a handler belongs to
- associated-data source says where runtime-associated data comes from
- handler requirements say what helper/lowering resources and checks are needed

Examples:

- `+`
  - family: `primitive-empty`
  - associated-data source: `NONE`
  - likely requirements:
    - `min_data_stack_in=2`
    - `min_data_stack_out_space=1`
    - `needs_error_exit=True`

- `LIT`
  - family: `primitive-inline-operand`
  - associated-data source: `INLINE_THREAD`
  - likely requirements:
    - `min_data_stack_in=0`
    - `min_data_stack_out_space=1`
    - `needs_thread_cursor=True`
    - `needs_error_exit=True`

- `BRANCH`
  - family: `primitive-inline-operand`
  - associated-data source: `INLINE_THREAD`
  - likely requirements:
    - `needs_thread_cursor=True`
    - `needs_thread_jump=True`
    - `needs_error_exit=True`

- `EXIT`
  - family: `primitive-empty`
  - associated-data source: `NONE`
  - likely requirements:
    - `needs_return_stack=True`
    - `min_return_stack_in=1`
    - `needs_error_exit=True`

- `HALT`
  - family: `primitive-empty`
  - associated-data source: `NONE`
  - likely requirements:
    - `needs_execution_control=True`
    - `needs_error_exit=True`

- `CREATE`
  - compiler/meta vocabulary example
  - likely requirements:
    - `needs_input_source=True`
    - `needs_dictionary=True`
    - `needs_here=True`
    - `needs_error_exit=True`

- `S"`
  - compiler/meta vocabulary example
  - likely requirements:
    - `needs_source_cursor=True`
    - `needs_thread_emitter=True`
    - `needs_error_exit=True`

## Lowering Entry Points

The intended lowering style is:

- requirements are declared separately
- the lowering function receives injected resources matching those declarations
- the lowering function emits the local handler body only
- the lowering function does not own tail-thread or continuation logic

Example shape:

```python
def lower_lit(builder, *, data_stack, thread_cursor, err):
    ...

def lower_branch(builder, *, thread_cursor, thread_jump, err):
    ...

def op_halt_ir(builder, *, control, err):
    ...

def handle_s_quote(*, source_cursor, thread_emitter, err):
    ...
```

Important invariants:

- resources are injected because they were declared
- positional ABI differences are not used to distinguish handlers
- continuation remains an outer framework responsibility
- inline-operand handlers should consume thread data through a cursor surface and
  redirect control only through an injected jump/control surface, not by returning a
  synthetic `next_ip`

## Kernels And Shared Lowering Shapes

`HandlerRequirements` is also the natural home for shared lowering-kernel lookup.

That is the bridge to:

- [docs/references/forth/primitive-stack-shape-synthesis.md](/Users/manny/fythvm/docs/references/forth/primitive-stack-shape-synthesis.md:1)
- [python-shared-stack-kernels lab](/Users/manny/fythvm/explorations/lab/python-shared-stack-kernels/README.md:1)

Keep the axes separate:

- family
  - runtime semantics
- category
  - organization/inventory
- kernel
  - reusable lowering shape

## Continuation Stays Outside The Handler Body

Handler bodies should not decide:

- tail-call chaining
- loop-and-switch re-entry
- hybrid dispatch re-entry

Those are continuation mechanics owned by the enclosing execution/lowering framework.

This keeps handler-local lowering contracts stable even if dispatch form changes.

## Open Points

The remaining open points here are intentionally narrow.

- whether associated-data source becomes first-class package metadata or remains inside
  richer handler metadata
- whether `HandlerRequirements` lives directly on instruction descriptors or in a
  neighboring registry
- the minimal stable field set for package code
- the first kernel ids/lookups to standardize
- the exact injection convention for lowering functions
- how preflight checks, wrong-mode exits, and error exits are factored around handler
  bodies
