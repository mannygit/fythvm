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
    needs_ip=False,
    needs_current_xt=False,
    needs_return_stack=False,
    needs_input_source=False,
    needs_error_exit=False,
    needs_dictionary=False,
    needs_here=False,
    kernel=None,
)
```

This is still a design sketch, not yet package code.

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

- `needs_ip`
  - current code spelling for "this handler needs thread-position access"
  - this is likely too coarse long-term and probably wants to split into cursor-like
    and jump-like thread capabilities
- `needs_current_xt`
  - the handler recovers word-local data via `current_xt -> DFA`
- `needs_return_stack`
  - the handler needs direct return/control-stack access
- `needs_error_exit`
  - the handler expects an error-exit facility
- `needs_dictionary`
  - the handler needs dictionary access
- `needs_here`
  - the handler needs the current dictionary write cursor

### Injected Parse-Time Resource

- `needs_input_source`
  - the handler or compiler/meta word consumes parse-time input state

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
    - `needs_ip=True` for now, though the real need is closer to a thread-cursor
      capability than a raw `ip` integer
    - `needs_error_exit=True`

- `EXIT`
  - family: `primitive-empty`
  - associated-data source: `NONE`
  - likely requirements:
    - `needs_return_stack=True`
    - `min_return_stack_in=1`
    - `needs_error_exit=True`

- `CREATE`
  - compiler/meta vocabulary example
  - likely requirements:
    - `needs_input_source=True`
    - `needs_dictionary=True`
    - `needs_here=True`
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
```

Important invariants:

- resources are injected because they were declared
- positional ABI differences are not used to distinguish handlers
- continuation remains an outer framework responsibility
- inline-operand handlers should consume thread data through a helper/cursor surface,
  not by returning a synthetic `next_ip`

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
- whether `needs_ip` should split into thread-cursor and thread-jump capabilities
- how preflight checks, wrong-mode exits, and error exits are factored around handler
  bodies
