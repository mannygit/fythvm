"""Demonstrate a delayed, module-scoped llvmlite export plan."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Callable

from llvmlite import binding, ir


I64 = ir.IntType(64)
CALLABLE_I64_TO_I64 = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)


def configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


@dataclass
class ExportRecord:
    name: str
    signature: str
    function: ir.Function
    declaration_index: int
    definition_index: int | None = None

    @property
    def declared(self) -> bool:
        return self.declaration_index >= 0

    @property
    def defined(self) -> bool:
        return self.definition_index is not None


class ExportPlan:
    """Host-owned, module-scoped export plan with explicit finalization."""

    def __init__(self, module_name: str) -> None:
        self.module = ir.Module(name=module_name)
        self.module.triple = binding.get_default_triple()
        self._exports: dict[str, ExportRecord] = {}
        self._declaration_counter = 0
        self._definition_counter = 0
        self._finalized = False
        self._engine: binding.ExecutionEngine | None = None
        self._callables: dict[str, Callable[[int], int]] = {}

    def declare(self, name: str, function_type: ir.FunctionType) -> ir.Function:
        if name in self._exports:
            raise ValueError(f"duplicate export declaration: {name}")
        function = ir.Function(self.module, function_type, name=name)
        self._exports[name] = ExportRecord(
            name=name,
            signature=str(function_type),
            function=function,
            declaration_index=self._declaration_counter,
        )
        self._declaration_counter += 1
        return function

    def function(self, name: str) -> ir.Function:
        try:
            return self._exports[name].function
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"unknown export: {name}") from exc

    def define(self, name: str, emitter: Callable[[ir.IRBuilder, "ExportPlan", ir.Function], None]) -> None:
        record = self._exports.get(name)
        if record is None:
            raise KeyError(f"cannot define undeclared export: {name}")
        if record.defined:
            raise ValueError(f"export already defined: {name}")

        entry = record.function.append_basic_block(name="entry")
        builder = ir.IRBuilder(entry)
        emitter(builder, self, record.function)
        record.definition_index = self._definition_counter
        self._definition_counter += 1

    def missing_definitions(self) -> list[str]:
        return [name for name, record in self._exports.items() if not record.defined]

    def describe_exports(self) -> list[str]:
        lines = []
        for record in sorted(self._exports.values(), key=lambda item: item.declaration_index):
            state = "defined" if record.defined else "declared"
            lines.append(
                f"{record.declaration_index:>2}: {record.name} :: {record.signature} "
                f"[{state}, definition_order={record.definition_index}]"
            )
        return lines

    def finalize(self) -> None:
        if self._finalized:
            return
        missing = self.missing_definitions()
        if missing:
            raise RuntimeError(f"cannot finalize; missing definitions for: {', '.join(missing)}")

        llvm_ir = str(self.module)
        parsed = binding.parse_assembly(llvm_ir)
        parsed.verify()
        target = binding.Target.from_default_triple()
        target_machine = target.create_target_machine()
        engine = binding.create_mcjit_compiler(parsed, target_machine)
        engine.finalize_object()
        self._engine = engine

        for name, record in self._exports.items():
            func_addr = engine.get_function_address(name)
            self._callables[name] = CALLABLE_I64_TO_I64(func_addr)

        self._finalized = True

    def call_i64(self, name: str, value: int) -> int:
        if not self._finalized:
            raise RuntimeError("export plan must be finalized before calling exports")
        return int(self._callables[name](value))

    def llvm_ir(self) -> str:
        return str(self.module)


def emit_offset_then_scale(builder: ir.IRBuilder, plan: ExportPlan, function: ir.Function) -> None:
    value = function.args[0]
    offset = builder.add(value, ir.Constant(I64, 5), name="offset")
    builder.ret(builder.mul(offset, ir.Constant(I64, 3), name="scaled"))


def emit_pipeline_entry(builder: ir.IRBuilder, plan: ExportPlan, function: ir.Function) -> None:
    helper = plan.function("offset_then_scale")
    helper_result = builder.call(helper, [function.args[0]], name="helper_result")
    builder.ret(builder.add(helper_result, ir.Constant(I64, 1), name="final_result"))


def build_success_plan() -> ExportPlan:
    plan = ExportPlan("delayed_ir_export_pattern")
    i64_to_i64 = ir.FunctionType(I64, [I64])
    plan.declare("offset_then_scale", i64_to_i64)
    plan.declare("pipeline_entry", i64_to_i64)
    plan.define("pipeline_entry", emit_pipeline_entry)
    plan.define("offset_then_scale", emit_offset_then_scale)
    return plan


def duplicate_declaration_failure() -> str:
    plan = ExportPlan("delayed_ir_export_pattern_duplicate")
    signature = ir.FunctionType(I64, [I64])
    plan.declare("duplicate", signature)
    try:
        plan.declare("duplicate", signature)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip()
    return "unexpected success"


def call_before_finalize_failure() -> str:
    plan = build_success_plan()
    try:
        plan.call_i64("pipeline_entry", 7)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip()
    return "unexpected success"


def finalize_missing_body_failure() -> str:
    plan = ExportPlan("delayed_ir_export_pattern_missing_body")
    signature = ir.FunctionType(I64, [I64])
    plan.declare("declared_only", signature)
    try:
        plan.finalize()
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip()
    return "unexpected success"


def main() -> None:
    configure_llvm()
    plan = build_success_plan()
    plan.finalize()

    print("== Question ==")
    print("How do you stage llvmlite exports so declarations arrive before bodies, without a global registry?")
    print()

    print("== Phase 1: Declare Signatures ==")
    for line in plan.describe_exports():
        print(line)
    print("ordering rule: declare every export first so later bodies can refer to their symbols explicitly")
    print()

    print("== Phase 2: Define Bodies Later ==")
    print("pipeline_entry was defined before offset_then_scale, but both symbols were already declared.")
    print("that lets one export call another without importing ambient host state or inventing placeholder globals.")
    print()

    print("== Finalization ==")
    print("host step: verify module, create MCJIT engine, resolve function addresses, then make the callables live")
    print(plan.llvm_ir().rstrip())
    print()

    print("== Runtime Results ==")
    for sample in (0, 4, 9):
        result = plan.call_i64("pipeline_entry", sample)
        print(f"pipeline_entry({sample}) -> {result}")
    print()

    print("== Non-Obvious Failure Modes ==")
    print(f"duplicate declaration: {duplicate_declaration_failure()}")
    print(f"call before finalize: {call_before_finalize_failure()}")
    print(f"finalize with missing body: {finalize_missing_body_failure()}")
    print()

    print("== Takeaway ==")
    print("Treat export declaration as a planning step and finalization as the explicit moment when the module becomes callable.")


if __name__ == "__main__":
    main()
