# Handler Requirements

This document records the next layer after the current execution and family work:
declarative handler/lowering requirements over one uniform runtime handler ABI.

The working direction is:

- runtime handlers share one uniform logical surface over one machine state
- family metadata remains useful, but does not define handler ABI
- per-handler requirements describe what a lowering/helper implementation needs access
  to in order to emit or interpret that handler cleanly
- continuation/dispatch mechanics remain outside individual handler bodies

## Relationship To Neighboring Docs

- [docs/execution-invariants.md](/Users/manny/fythvm/docs/execution-invariants.md:1)
  defines the machine-state substrate and the uniform-handler direction
- [docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1)
  defines runtime families as supporting metadata around that substrate
- [docs/compiler-mode-contract.md](/Users/manny/fythvm/docs/compiler-mode-contract.md:1)
  defines parse-time/compiler-mode behavior that should not be collapsed into runtime
  associated-data sources
- [docs/references/forth/primitive-stack-shape-synthesis.md](/Users/manny/fythvm/docs/references/forth/primitive-stack-shape-synthesis.md:1)
  and the
  [python-shared-stack-kernels lab](/Users/manny/fythvm/explorations/lab/python-shared-stack-kernels/README.md:1)
  provide the strongest current reference pressure for shared lowering kernels

## Cross-Cutting Todo List

- [x] Record uniform-handler ABI as the execution direction.
- [x] Separate runtime associated-data source from parse-time/token input source.
- [x] Keep family metadata as semantic grouping rather than ABI definition.
- [x] Name a dedicated `HandlerRequirements` layer.
- [ ] Decide whether associated-data source becomes a first-class package type or lives
  only inside richer per-handler metadata.
- [ ] Decide whether `HandlerRequirements` lives directly on instruction descriptors or
  in a neighboring registry.
- [ ] Define the minimal stable set of requirement fields for package code.
- [ ] Define the first kernel ids/lookups that map onto the stack-shape synthesis work.
- [ ] Define the exact lowering-function injection convention in package code.
- [ ] Define how preflight checks, wrong-mode exits, and error exits are factored around
  handler bodies.

## Why This Layer Exists

The current package metadata already distinguishes:

- runtime family
- instruction category

The stack-shape synthesis and shared-kernel lab also already distinguish:

- user-facing word identity
- reusable implementation skeletons

What is still missing is the declarative layer that says:

- what resources a handler body requires
- what stack preconditions must hold
- what stack space must be available for the result
- whether the handler needs `ip`, `current_xt`, parse-time input, dictionary access,
  or error-exit facilities

That missing layer is `HandlerRequirements`.

## What Handler Requirements Are

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
- help select shared lowering kernels
- let Python/IR lowering code stay declarative

## Core Shape

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
  - additional output space that must be available at egress
- `min_return_stack_in`
  - minimum return-stack depth required at handler ingress
- `min_return_stack_out_space`
  - additional return-stack space that must be available at egress

These fields describe required shape and capacity. They do not change handler ABI.

### Injected Runtime Resources

- `needs_ip`
  - the handler reads inline data from the current thread
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

### Injected Parse-Time Resources

- `needs_input_source`
  - the handler or compiler/meta word consumes parse-time input state

This is intentionally separated from runtime associated-data sources:

- runtime inline operands come from `ip`
- parse-time tokens come from the input source and parse cursor

## Associated Data Sources Versus Requirements

The current runtime associated-data-source split is still:

- `NONE`
- `WORD_LOCAL_DFA`
- `INLINE_THREAD`

`HandlerRequirements` does not replace that split. It complements it.

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
    - `needs_ip=True`
    - `needs_error_exit=True`

- `EXIT`
  - family: `primitive-empty`
  - associated-data source: `NONE`
  - likely requirements:
    - `needs_return_stack=True`
    - `min_return_stack_in=1`
    - `needs_error_exit=True`

- `CREATE`
  - compile/meta vocabulary, not mainly a runtime-family example
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
def lower_lit(builder, *, data_stack, ip, err):
    # local body only
    ...
```

The important invariants are:

- resources are injected because they were declared
- positional ABI differences are not used to distinguish handlers
- continuation remains an outer framework responsibility

## Kernels And Shared Lowering Shapes

`HandlerRequirements` also gives the right home for shared lowering-kernel lookup.

This is the bridge to:

- [docs/references/forth/primitive-stack-shape-synthesis.md](/Users/manny/fythvm/docs/references/forth/primitive-stack-shape-synthesis.md:1)
- [python-shared-stack-kernels lab](/Users/manny/fythvm/explorations/lab/python-shared-stack-kernels/README.md:1)

The important distinction is:

- family is about runtime semantics
- category is about organization/inventory
- kernel is about reusable lowering shape

So a handler may eventually carry:

- family
- category
- associated-data source
- requirements
- kernel id

without any of those implying a different handler ABI.

## Continuation Stays Outside The Handler Body

This is one of the most important current constraints.

Handler bodies should not have to decide:

- tail-call chaining
- loop-and-switch re-entry
- hybrid dispatch re-entry

Those are continuation mechanics owned by the enclosing execution/lowering framework.

This matches the current execution direction:

- direct-threaded / `musttail`
- loop-and-switch
- hybrid

All of those should remain swappable without redefining handler-local lowering
contracts.

## Recommended Next Package Step

The next useful package-level move is likely one of:

1. add `HandlerRequirements` to concrete instruction descriptors
2. add a neighboring per-handler requirements registry layered over instruction
   descriptors

The decision should be driven by:

- how stable the requirement field set feels
- how much metadata we want family descriptors to carry
- whether kernel selection is better grouped with instruction descriptors or separated

## Short Version

The new layer is:

- not a new handler ABI
- not a replacement for families
- not a replacement for associated-data source

It is:

- the declarative contract for what a concrete handler/lowering body needs in order to
  emit or interpret its local behavior over one shared machine-state surface
