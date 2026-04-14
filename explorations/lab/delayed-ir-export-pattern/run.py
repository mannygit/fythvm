"""Demonstrate raw and Pythonic delayed llvmlite export planning."""

from __future__ import annotations

import ctypes
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

from llvmlite import binding, ir


I64 = ir.IntType(64)
CALLABLE_I64_TO_I64 = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)


def configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def compile_module(module: ir.Module, function_name: str) -> tuple[str, binding.ExecutionEngine, CALLABLE_I64_TO_I64]:
    """Verify a module and return the IR, live engine, and callable function pointer."""

    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()
    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()
    address = engine.get_function_address(function_name)
    return llvm_ir, engine, CALLABLE_I64_TO_I64(address)


def make_raw_plan(module_name: str) -> dict[str, object]:
    module = ir.Module(name=module_name)
    module.triple = binding.get_default_triple()
    return {
        "module": module,
        "exports": {},
        "declaration_counter": 0,
        "definition_counter": 0,
        "finalized": False,
        "engine": None,
        "callables": {},
    }


def raw_declare(plan: dict[str, object], name: str, function_type: ir.FunctionType) -> ir.Function:
    exports = plan["exports"]
    assert isinstance(exports, dict)
    if name in exports:
        raise ValueError(f"duplicate export declaration: {name}")

    module = plan["module"]
    assert isinstance(module, ir.Module)
    function = ir.Function(module, function_type, name=name)
    declaration_index = int(plan["declaration_counter"])
    exports[name] = {
        "name": name,
        "signature": str(function_type),
        "function": function,
        "declaration_index": declaration_index,
        "definition_index": None,
    }
    plan["declaration_counter"] = declaration_index + 1
    return function


def raw_function(plan: dict[str, object], name: str) -> ir.Function:
    exports = plan["exports"]
    assert isinstance(exports, dict)
    return exports[name]["function"]  # type: ignore[index]


def raw_define(
    plan: dict[str, object],
    name: str,
    emitter: Callable[[ir.IRBuilder, dict[str, object], ir.Function], None],
) -> None:
    exports = plan["exports"]
    assert isinstance(exports, dict)
    record = exports.get(name)
    if record is None:
        raise KeyError(f"cannot define undeclared export: {name}")
    if record["definition_index"] is not None:
        raise ValueError(f"export already defined: {name}")

    function = record["function"]
    assert isinstance(function, ir.Function)
    entry = function.append_basic_block(name="entry")
    builder = ir.IRBuilder(entry)
    emitter(builder, plan, function)
    record["definition_index"] = int(plan["definition_counter"])
    plan["definition_counter"] = int(plan["definition_counter"]) + 1


def raw_missing_definitions(plan: dict[str, object]) -> list[str]:
    exports = plan["exports"]
    assert isinstance(exports, dict)
    return [name for name, record in exports.items() if record["definition_index"] is None]


def raw_describe_exports(plan: dict[str, object]) -> list[str]:
    exports = plan["exports"]
    assert isinstance(exports, dict)
    lines = []
    for record in sorted(exports.values(), key=lambda item: item["declaration_index"]):
        state = "defined" if record["definition_index"] is not None else "declared"
        lines.append(
            f"{record['declaration_index']:>2}: {record['name']} :: {record['signature']} "
            f"[{state}, definition_order={record['definition_index']}]"
        )
    return lines


def raw_finalize(plan: dict[str, object]) -> None:
    if plan["finalized"]:
        return
    missing = raw_missing_definitions(plan)
    if missing:
        raise RuntimeError(f"cannot finalize; missing definitions for: {', '.join(missing)}")

    module = plan["module"]
    assert isinstance(module, ir.Module)
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()
    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()
    plan["engine"] = engine

    callables = plan["callables"]
    assert isinstance(callables, dict)
    exports = plan["exports"]
    assert isinstance(exports, dict)
    for name in exports:
        callables[name] = CALLABLE_I64_TO_I64(engine.get_function_address(name))

    plan["finalized"] = True


def raw_call_i64(plan: dict[str, object], name: str, value: int) -> int:
    if not plan["finalized"]:
        raise RuntimeError("export plan must be finalized before calling exports")
    callables = plan["callables"]
    assert isinstance(callables, dict)
    return int(callables[name](value))


def raw_emit_offset_then_scale(builder: ir.IRBuilder, plan: dict[str, object], function: ir.Function) -> None:
    value = function.args[0]
    offset = builder.add(value, ir.Constant(I64, 5), name="offset")
    builder.ret(builder.mul(offset, ir.Constant(I64, 3), name="scaled"))


def raw_emit_pipeline_entry(builder: ir.IRBuilder, plan: dict[str, object], function: ir.Function) -> None:
    helper = raw_function(plan, "offset_then_scale")
    helper_result = builder.call(helper, [function.args[0]], name="helper_result")
    builder.ret(builder.add(helper_result, ir.Constant(I64, 1), name="final_result"))


def build_raw_success_plan() -> dict[str, object]:
    plan = make_raw_plan("delayed_ir_export_pattern_raw")
    signature = ir.FunctionType(I64, [I64])
    raw_declare(plan, "offset_then_scale", signature)
    raw_declare(plan, "pipeline_entry", signature)
    raw_define(plan, "pipeline_entry", raw_emit_pipeline_entry)
    raw_define(plan, "offset_then_scale", raw_emit_offset_then_scale)
    return plan


def raw_duplicate_declaration_failure() -> str:
    plan = make_raw_plan("delayed_ir_export_pattern_raw_duplicate")
    signature = ir.FunctionType(I64, [I64])
    raw_declare(plan, "duplicate", signature)
    try:
        raw_declare(plan, "duplicate", signature)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip()
    return "unexpected success"


def raw_call_before_finalize_failure() -> str:
    plan = build_raw_success_plan()
    try:
        raw_call_i64(plan, "pipeline_entry", 7)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip()
    return "unexpected success"


def raw_finalize_missing_body_failure() -> str:
    plan = make_raw_plan("delayed_ir_export_pattern_raw_missing_body")
    signature = ir.FunctionType(I64, [I64])
    raw_declare(plan, "declared_only", signature)
    try:
        raw_finalize(plan)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip()
    return "unexpected success"


@dataclass
class ExportRecord:
    name: str
    signature: str
    function: ir.Function
    declaration_index: int
    definition_index: int | None = None


class ExportPlan:
    """Host-owned, module-scoped export plan with an explicit body staging context manager."""

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

    @contextmanager
    def define(self, name: str):
        record = self._exports.get(name)
        if record is None:
            raise KeyError(f"cannot define undeclared export: {name}")
        if record.definition_index is not None:
            raise ValueError(f"export already defined: {name}")

        entry = record.function.append_basic_block(name="entry")
        builder = ir.IRBuilder(entry)
        try:
            yield builder, record.function
        except Exception:
            raise
        else:
            record.definition_index = self._definition_counter
            self._definition_counter += 1

    def missing_definitions(self) -> list[str]:
        return [name for name, record in self._exports.items() if record.definition_index is None]

    def describe_exports(self) -> list[str]:
        lines = []
        for record in sorted(self._exports.values(), key=lambda item: item.declaration_index):
            state = "defined" if record.definition_index is not None else "declared"
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

        for name in self._exports:
            self._callables[name] = CALLABLE_I64_TO_I64(engine.get_function_address(name))

        self._finalized = True

    def call_i64(self, name: str, value: int) -> int:
        if not self._finalized:
            raise RuntimeError("export plan must be finalized before calling exports")
        return int(self._callables[name](value))

    def llvm_ir(self) -> str:
        return str(self.module)


def build_pythonic_success_plan() -> ExportPlan:
    plan = ExportPlan("delayed_ir_export_pattern_pythonic")
    signature = ir.FunctionType(I64, [I64])
    plan.declare("offset_then_scale", signature)
    plan.declare("pipeline_entry", signature)
    with plan.define("pipeline_entry") as (builder, function):
        helper = plan.function("offset_then_scale")
        helper_result = builder.call(helper, [function.args[0]], name="helper_result")
        builder.ret(builder.add(helper_result, ir.Constant(I64, 1), name="final_result"))
    with plan.define("offset_then_scale") as (builder, function):
        value = function.args[0]
        offset = builder.add(value, ir.Constant(I64, 5), name="offset")
        builder.ret(builder.mul(offset, ir.Constant(I64, 3), name="scaled"))
    return plan


def pythonic_duplicate_declaration_failure() -> str:
    plan = ExportPlan("delayed_ir_export_pattern_pythonic_duplicate")
    signature = ir.FunctionType(I64, [I64])
    plan.declare("duplicate", signature)
    try:
        plan.declare("duplicate", signature)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip()
    return "unexpected success"


def pythonic_call_before_finalize_failure() -> str:
    plan = build_pythonic_success_plan()
    try:
        plan.call_i64("pipeline_entry", 7)
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip()
    return "unexpected success"


def pythonic_finalize_missing_body_failure() -> str:
    plan = ExportPlan("delayed_ir_export_pattern_pythonic_missing_body")
    signature = ir.FunctionType(I64, [I64])
    plan.declare("declared_only", signature)
    try:
        plan.finalize()
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip()
    return "unexpected success"


def main() -> None:
    configure_llvm()

    raw_plan = build_raw_success_plan()
    pythonic_plan = build_pythonic_success_plan()

    raw_finalize(raw_plan)
    raw_ir = str(raw_plan["module"])
    raw_exports = raw_describe_exports(raw_plan)

    pythonic_plan.finalize()
    pythonic_ir = pythonic_plan.llvm_ir()
    pythonic_exports = pythonic_plan.describe_exports()

    samples = (0, 4, 9)

    print("== Question ==")
    print("How do you stage llvmlite exports so declarations arrive before bodies, without a global registry?")
    print()

    print("== Raw Baseline ==")
    print("source of truth: explicit plain-state export staging")
    for line in raw_exports:
        print(line)
    print("ordering rule: declare every export first so later bodies can refer to their symbols explicitly")
    print(raw_ir.rstrip())
    print()
    print("results")
    for sample in samples:
        print(f"pipeline_entry({sample}) -> {raw_call_i64(raw_plan, 'pipeline_entry', sample)}")
    print()

    print("== Pythonic Variant ==")
    print("readability layer: a tiny plan object with a body-staging context manager")
    for line in pythonic_exports:
        print(line)
    print("the plan object keeps the same phase ordering visible while reducing the staging boilerplate")
    print(pythonic_ir.rstrip())
    print()
    print("results")
    for sample in samples:
        print(f"pipeline_entry({sample}) -> {pythonic_plan.call_i64('pipeline_entry', sample)}")
    print()

    print("== Non-Obvious Failure Modes ==")
    print(f"raw duplicate declaration: {raw_duplicate_declaration_failure()}")
    print(f"raw call before finalize: {raw_call_before_finalize_failure()}")
    print(f"raw finalize with missing body: {raw_finalize_missing_body_failure()}")
    print(f"pythonic duplicate declaration: {pythonic_duplicate_declaration_failure()}")
    print(f"pythonic call before finalize: {pythonic_call_before_finalize_failure()}")
    print(f"pythonic finalize with missing body: {pythonic_finalize_missing_body_failure()}")
    print()

    print("== Comparison ==")
    print("Both versions export the same pipeline, but the raw one makes the module-state transitions obvious.")
    print("The Pythonic version earns its keep by staging bodies with a context manager instead of threading book-keeping through every emitter.")
    print()

    print("== Pattern / Takeaway ==")
    print("Treat export declaration as planning, body emission as a later stage, and finalization as the explicit moment when the module becomes callable.")
    print()

    print("== Takeaway ==")
    print("Keep the raw plan as the correctness reference, then let a small Pythonic layer reduce the ceremony around delayed bodies and finalization.")


if __name__ == "__main__":
    main()
