"""Demonstrate a host-owned lifecycle protocol for llvmlite MCJIT modules."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import binding, ir


I1 = ir.IntType(1)
I8 = ir.IntType(8)
I32 = ir.IntType(32)
I64 = ir.IntType(64)
I64_PTR = I64.as_pointer()
RUNTIME_SLOT_NAMES = (
    "resource_counter",
    "init_effects",
    "fini_effects",
    "last_generation_marker",
)


@dataclass
class RuntimeSnapshot:
    resource_counter: int
    init_effects: int
    fini_effects: int
    last_generation_marker: int


class RuntimeContext(ctypes.Structure):
    """A tiny host-owned context used to make lifecycle side effects visible."""

    _fields_ = [
        ("resource_counter", ctypes.c_int64),
        ("init_effects", ctypes.c_int64),
        ("fini_effects", ctypes.c_int64),
        ("last_generation_marker", ctypes.c_int64),
    ]

    def snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            resource_counter=self.resource_counter,
            init_effects=self.init_effects,
            fini_effects=self.fini_effects,
            last_generation_marker=self.last_generation_marker,
        )

    def as_void_p(self) -> ctypes.c_void_p:
        return ctypes.c_void_p(ctypes.addressof(self))


@dataclass
class ModuleCallbacks:
    init_addr: int
    fini_addr: int
    is_initialized_addr: int
    generation_marker_addr: int
    init: object
    fini: object
    is_initialized: object
    generation_marker: object


@dataclass
class ModuleRecord:
    module_id: str
    generation: int
    module_ref: binding.ModuleRef
    llvm_ir: str
    state: str
    callbacks: ModuleCallbacks | None


class LifecycleError(RuntimeError):
    """Base error for registry lifecycle mistakes."""


class StaleGenerationError(LifecycleError):
    """Raised when a caller uses an old generation token."""


def ensure_llvm_initialized() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def context_slot_ptr(builder: ir.IRBuilder, ctx_arg: ir.Argument, index: int) -> ir.Value:
    ctx_words = builder.bitcast(ctx_arg, I64_PTR, name="ctx_words")
    return builder.gep(
        ctx_words,
        [ir.Constant(I32, index)],
        inbounds=True,
        name=f"slot_{index}_ptr",
    )


def increment_slot(builder: ir.IRBuilder, ctx_arg: ir.Argument, index: int, delta: int) -> None:
    slot_ptr = context_slot_ptr(builder, ctx_arg, index)
    current = builder.load(slot_ptr, name=f"slot_{index}")
    updated = builder.add(current, ir.Constant(I64, delta), name=f"slot_{index}_updated")
    builder.store(updated, slot_ptr)


def write_slot(builder: ir.IRBuilder, ctx_arg: ir.Argument, index: int, value: int) -> None:
    builder.store(ir.Constant(I64, value), context_slot_ptr(builder, ctx_arg, index))


def build_lifecycle_module(module_id: str, generation: int) -> ir.Module:
    """Build a module that uses explicit lifecycle callbacks instead of global ctors."""
    module = ir.Module(name=f"{module_id}_gen_{generation}")
    module.triple = binding.get_default_triple()

    is_initialized = ir.GlobalVariable(module, I1, name="module_initialized")
    is_initialized.initializer = ir.Constant(I1, 0)

    init_fn = ir.Function(module, ir.FunctionType(I32, [I8.as_pointer()]), name="module_init")
    entry = init_fn.append_basic_block(name="entry")
    already = init_fn.append_basic_block(name="already_initialized")
    do_init = init_fn.append_basic_block(name="do_init")

    builder = ir.IRBuilder(entry)
    initialized = builder.load(is_initialized, name="initialized")
    builder.cbranch(initialized, already, do_init)

    builder.position_at_end(already)
    builder.ret(ir.Constant(I32, 0))

    builder.position_at_end(do_init)
    increment_slot(builder, init_fn.args[0], 0, 1)
    increment_slot(builder, init_fn.args[0], 1, 1)
    write_slot(builder, init_fn.args[0], 3, generation)
    builder.store(ir.Constant(I1, 1), is_initialized)
    builder.ret(ir.Constant(I32, 0))

    fini_fn = ir.Function(module, ir.FunctionType(I32, [I8.as_pointer()]), name="module_fini")
    entry = fini_fn.append_basic_block(name="entry")
    already = fini_fn.append_basic_block(name="already_finalized")
    do_fini = fini_fn.append_basic_block(name="do_fini")

    builder = ir.IRBuilder(entry)
    initialized = builder.load(is_initialized, name="initialized")
    builder.cbranch(initialized, do_fini, already)

    builder.position_at_end(already)
    builder.ret(ir.Constant(I32, 0))

    builder.position_at_end(do_fini)
    increment_slot(builder, fini_fn.args[0], 0, -1)
    increment_slot(builder, fini_fn.args[0], 2, 1)
    write_slot(builder, fini_fn.args[0], 3, generation)
    builder.store(ir.Constant(I1, 0), is_initialized)
    builder.ret(ir.Constant(I32, 0))

    state_fn = ir.Function(module, ir.FunctionType(I32, []), name="module_is_initialized")
    block = state_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    state = builder.load(is_initialized, name="state")
    builder.ret(builder.zext(state, I32))

    generation_fn = ir.Function(
        module,
        ir.FunctionType(I64, []),
        name="module_generation_marker",
    )
    block = generation_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    builder.ret(ir.Constant(I64, generation))

    return module


class LifecycleRegistry:
    """Own the live module registry and callback validity rules."""

    def __init__(self) -> None:
        ensure_llvm_initialized()
        backing_module = binding.parse_assembly("")
        target = binding.Target.from_default_triple()
        target_machine = target.create_target_machine()
        self.engine = binding.create_mcjit_compiler(backing_module, target_machine)
        self.modules: dict[str, ModuleRecord] = {}
        self.next_generation = 1

    def load_module(self, module_id: str) -> ModuleRecord:
        if module_id in self.modules:
            raise LifecycleError(f"module {module_id!r} is already live")

        generation = self.next_generation
        self.next_generation += 1

        module = build_lifecycle_module(module_id, generation)
        llvm_ir = str(module)
        module_ref = binding.parse_assembly(llvm_ir)
        module_ref.verify()

        self.engine.add_module(module_ref)
        self.engine.finalize_object()

        callbacks = self._resolve_callbacks()
        record = ModuleRecord(
            module_id=module_id,
            generation=generation,
            module_ref=module_ref,
            llvm_ir=llvm_ir,
            state="registered",
            callbacks=callbacks,
        )
        self.modules[module_id] = record
        return record

    def init_module(
        self,
        module_id: str,
        generation: int,
        runtime_ctx: RuntimeContext,
    ) -> int:
        record = self._require_live_record(module_id, generation)
        if record.callbacks is None:
            raise LifecycleError(f"module {module_id!r} has no live callbacks")

        rc = record.callbacks.init(runtime_ctx.as_void_p())
        if rc == 0:
            record.state = "initialized" if record.callbacks.is_initialized() else record.state
        else:
            record.state = "init_failed"
        return rc

    def unload_module(
        self,
        module_id: str,
        generation: int,
        runtime_ctx: RuntimeContext,
    ) -> list[str]:
        record = self._require_live_record(module_id, generation)
        if record.callbacks is None:
            raise LifecycleError(f"module {module_id!r} has no live callbacks")

        events: list[str] = []
        events.append("call module_fini")
        rc = record.callbacks.fini(runtime_ctx.as_void_p())
        events.append(f"module_fini returned {rc}")
        if rc != 0:
            record.state = "fini_failed"
            raise LifecycleError(f"module_fini failed for {module_id!r} with rc={rc}")

        record.state = "finalized"
        events.append("drop callback addresses from registry")
        record.callbacks = None

        events.append("engine.remove_module")
        self.engine.remove_module(record.module_ref)
        record.state = "unloaded"
        events.append("mark unloaded")
        del self.modules[module_id]
        return events

    def _resolve_callbacks(self) -> ModuleCallbacks:
        init_addr = self.engine.get_function_address("module_init")
        fini_addr = self.engine.get_function_address("module_fini")
        is_initialized_addr = self.engine.get_function_address("module_is_initialized")
        generation_marker_addr = self.engine.get_function_address("module_generation_marker")
        return ModuleCallbacks(
            init_addr=init_addr,
            fini_addr=fini_addr,
            is_initialized_addr=is_initialized_addr,
            generation_marker_addr=generation_marker_addr,
            init=ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p)(init_addr),
            fini=ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p)(fini_addr),
            is_initialized=ctypes.CFUNCTYPE(ctypes.c_int32)(is_initialized_addr),
            generation_marker=ctypes.CFUNCTYPE(ctypes.c_int64)(generation_marker_addr),
        )

    def _require_live_record(self, module_id: str, generation: int) -> ModuleRecord:
        if module_id not in self.modules:
            raise LifecycleError(f"unknown module {module_id!r}")

        record = self.modules[module_id]
        if record.generation != generation:
            raise StaleGenerationError(
                f"stale generation for {module_id!r}: got {generation}, live generation is "
                f"{record.generation}"
            )
        return record


def format_snapshot(snapshot: RuntimeSnapshot) -> str:
    values = {
        name: getattr(snapshot, name)
        for name in RUNTIME_SLOT_NAMES
    }
    return ", ".join(f"{key}={value}" for key, value in values.items())


def main() -> None:
    runtime_ctx = RuntimeContext()
    registry = LifecycleRegistry()
    module_id = "demo_lifecycle_module"

    print("== Question ==")
    print("How should a llvmlite MCJIT module manage explicit init/fini, unload, and reload?")
    print()

    record_v1 = registry.load_module(module_id)
    assert record_v1.callbacks is not None

    print("== Generated IR (generation 1) ==")
    print(record_v1.llvm_ir.rstrip())
    print()
    print("contains llvm.global_ctors:", "@llvm.global_ctors" in record_v1.llvm_ir)
    print("contains llvm.global_dtors:", "@llvm.global_dtors" in record_v1.llvm_ir)
    print()

    print("== Load / Init / Idempotence ==")
    print(f"loaded {module_id!r} generation {record_v1.generation}")
    print(
        "resolved marker via exported symbol:",
        record_v1.callbacks.generation_marker(),
    )
    print("runtime before init:", format_snapshot(runtime_ctx.snapshot()))
    print("module_is_initialized before init:", record_v1.callbacks.is_initialized())

    rc = registry.init_module(module_id, record_v1.generation, runtime_ctx)
    print("module_init rc:", rc)
    print("runtime after first init:", format_snapshot(runtime_ctx.snapshot()))
    print("module_is_initialized after first init:", record_v1.callbacks.is_initialized())

    rc = registry.init_module(module_id, record_v1.generation, runtime_ctx)
    print("second module_init rc:", rc)
    print("runtime after second init:", format_snapshot(runtime_ctx.snapshot()))
    print()

    print("== Unload Ordering ==")
    unload_events = registry.unload_module(module_id, record_v1.generation, runtime_ctx)
    for event in unload_events:
        print(event)
    print("runtime after unload:", format_snapshot(runtime_ctx.snapshot()))
    print()

    print("== Reload / Generation Safety ==")
    record_v2 = registry.load_module(module_id)
    assert record_v2.callbacks is not None
    print(f"reloaded {module_id!r} generation {record_v2.generation}")
    print(
        "resolved marker via same symbol names:",
        record_v2.callbacks.generation_marker(),
    )

    try:
        registry.init_module(module_id, record_v1.generation, runtime_ctx)
    except StaleGenerationError as exc:
        print("stale generation rejected:", exc)

    rc = registry.init_module(module_id, record_v2.generation, runtime_ctx)
    print("generation 2 module_init rc:", rc)
    print("runtime after generation 2 init:", format_snapshot(runtime_ctx.snapshot()))

    rc = record_v2.callbacks.fini(runtime_ctx.as_void_p())
    print("manual module_fini rc:", rc)
    print("runtime after first fini:", format_snapshot(runtime_ctx.snapshot()))

    rc = record_v2.callbacks.fini(runtime_ctx.as_void_p())
    print("second module_fini rc:", rc)
    print("runtime after second fini:", format_snapshot(runtime_ctx.snapshot()))
    unload_events = registry.unload_module(module_id, record_v2.generation, runtime_ctx)
    print("generation 2 unload after repeated fini requests:")
    for event in unload_events:
        print(event)
    print("runtime after final unload:", format_snapshot(runtime_ctx.snapshot()))
    print()

    print("== Takeaway ==")
    print(
        "Treat module lifecycle as a host-owned protocol: explicit init/fini, "
        "generation tracking, and finalization before remove_module()."
    )


if __name__ == "__main__":
    main()
