"""Show how a final phi can carry a search result or a sentinel."""

from __future__ import annotations

import ctypes
from contextlib import contextmanager
from dataclasses import dataclass

from llvmlite import binding, ir

I64 = ir.IntType(64)
HIDDEN_MASK = ir.Constant(I64, 1)
SEARCH_RECORD_TYPE = ir.global_context.get_identified_type("ResultCarrierSearchRecord")
if SEARCH_RECORD_TYPE.is_opaque:
    SEARCH_RECORD_TYPE.set_body(I64, I64, I64)
SEARCH_RECORD_PTR = SEARCH_RECORD_TYPE.as_pointer()


@dataclass(frozen=True)
class CompiledSearchDemo:
    llvm_ir: str
    engine: binding.ExecutionEngine
    raw_search_addr: int
    pythonic_search_addr: int
    raw_multi_stage_search_addr: int
    pythonic_multi_stage_search_addr: int


class ResultCarrierExit:
    """Local helper that centralizes the exit phi while leaving the CFG visible."""

    def __init__(self, function: ir.Function, prefix: str):
        self.builder = ir.IRBuilder(function.append_basic_block(f"{prefix}.entry"))
        self.entry_block = self.builder.basic_block
        self.loop_block = function.append_basic_block(f"{prefix}.loop")
        self.scan_block = function.append_basic_block(f"{prefix}.scan")
        self.found_block = function.append_basic_block(f"{prefix}.found")
        self.not_found_block = function.append_basic_block(f"{prefix}.not_found")
        self.exit_block = function.append_basic_block(f"{prefix}.exit")
        self._incoming: list[tuple[ir.Value, object]] = []
        self.builder.branch(self.loop_block)

    @contextmanager
    def found(self):
        self.builder.position_at_end(self.found_block)
        yield self
        if self.builder.basic_block.terminator is None:
            self.builder.branch(self.exit_block)

    @contextmanager
    def not_found(self):
        self.builder.position_at_end(self.not_found_block)
        yield self
        if self.builder.basic_block.terminator is None:
            self.builder.branch(self.exit_block)

    def remember(self, value: ir.Value) -> None:
        self._incoming.append((value, self.builder.basic_block))

    def finish(self, ty: ir.Type, name: str = "result") -> ir.Value:
        self.builder.position_at_end(self.exit_block)
        result = self.builder.phi(ty, name=name)
        for value, block in self._incoming:
            result.add_incoming(value, block)
        return result


class StagedRecordView:
    """Typed view over one candidate record while the search stays in raw LLVM terms."""

    def __init__(self, builder: ir.IRBuilder, record_ptr: ir.Value):
        self.builder = builder
        self.record_ptr = record_ptr

    def _field_ptr(self, index: int, name: str) -> ir.Value:
        return self.builder.gep(
            self.record_ptr,
            [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), index)],
            inbounds=True,
            name=f"{name}_ptr",
        )

    def flags(self) -> ir.Value:
        return self.builder.load(self._field_ptr(0, "flags"), name="flags")

    def length(self) -> ir.Value:
        return self.builder.load(self._field_ptr(1, "length"), name="length")

    def value(self) -> ir.Value:
        return self.builder.load(self._field_ptr(2, "value"), name="current_value")


class StagedResultSearch:
    """Own the staged guard protocol for a search with one semantic result."""

    def __init__(self, function: ir.Function, prefix: str):
        self.function = function
        self.prefix = prefix
        self.builder = ir.IRBuilder(function.append_basic_block(f"{prefix}.entry"))
        self.entry_block = self.builder.basic_block
        self.loop_block = function.append_basic_block(f"{prefix}.loop")
        self.scan_block = function.append_basic_block(f"{prefix}.scan")
        self.continue_block = function.append_basic_block(f"{prefix}.continue")
        self.not_found_block = function.append_basic_block(f"{prefix}.not_found")
        self.exit_block = function.append_basic_block(f"{prefix}.exit")
        self._incoming: list[tuple[ir.Value, ir.Block]] = []
        self.builder.branch(self.loop_block)

    def begin(self, candidates: ir.Argument, count: ir.Argument) -> tuple[ir.PhiInstr, StagedRecordView]:
        self.builder.position_at_end(self.loop_block)
        cursor = self.builder.phi(I64, name="cursor")
        cursor.add_incoming(ir.Constant(I64, 0), self.entry_block)
        reached_end = self.builder.icmp_signed(">=", cursor, count, name="reached_end")
        self.builder.cbranch(reached_end, self.not_found_block, self.scan_block)

        self.builder.position_at_end(self.scan_block)
        record_ptr = self.builder.gep(candidates, [cursor], inbounds=True, name="record_ptr")
        return cursor, StagedRecordView(self.builder, record_ptr)

    @contextmanager
    def require(self, name: str, predicate: ir.Value):
        passed_block = self.function.append_basic_block(f"{self.prefix}.{name}")
        self.builder.cbranch(predicate, passed_block, self.continue_block)
        self.builder.position_at_end(passed_block)
        yield self

    def accept(self, value: ir.Value) -> None:
        self._incoming.append((value, self.builder.basic_block))
        self.builder.branch(self.exit_block)

    def advance(self, cursor: ir.PhiInstr) -> None:
        self.builder.position_at_end(self.continue_block)
        next_cursor = self.builder.add(cursor, ir.Constant(I64, 1), name="next_cursor")
        cursor.add_incoming(next_cursor, self.continue_block)
        self.builder.branch(self.loop_block)

    def finish(self, failure_value: ir.Value) -> ir.Value:
        self.builder.position_at_end(self.not_found_block)
        self._incoming.append((failure_value, self.not_found_block))
        self.builder.branch(self.exit_block)

        self.builder.position_at_end(self.exit_block)
        result = self.builder.phi(I64, name="result")
        for value, block in self._incoming:
            result.add_incoming(value, block)
        return result


def _configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def _emit_raw_search(module: ir.Module) -> None:
    ptr_i64 = I64.as_pointer()
    fn_ty = ir.FunctionType(I64, [ptr_i64, I64, I64])

    raw_func = ir.Function(module, fn_ty, name="find_first_ge_raw")
    raw_entry = raw_func.append_basic_block(name="entry")
    raw_loop = raw_func.append_basic_block(name="loop")
    raw_scan = raw_func.append_basic_block(name="scan")
    raw_found = raw_func.append_basic_block(name="found")
    raw_not_found = raw_func.append_basic_block(name="not_found")

    builder = ir.IRBuilder(raw_entry)
    builder.branch(raw_loop)

    builder.position_at_end(raw_loop)
    loop_index = builder.phi(I64, name="index")
    loop_index.add_incoming(ir.Constant(I64, 0), raw_entry)
    reached_end = builder.icmp_signed(">=", loop_index, raw_func.args[1], name="reached_end")
    builder.cbranch(reached_end, raw_not_found, raw_scan)

    builder.position_at_end(raw_scan)
    element_ptr = builder.gep(raw_func.args[0], [loop_index], inbounds=True, name="element_ptr")
    current_value = builder.load(element_ptr, name="current_value")
    meets_threshold = builder.icmp_signed(
        ">=", current_value, raw_func.args[2], name="meets_threshold"
    )
    next_index = builder.add(loop_index, ir.Constant(I64, 1), name="next_index")
    loop_index.add_incoming(next_index, raw_scan)
    builder.cbranch(meets_threshold, raw_found, raw_loop)

    builder.position_at_end(raw_found)
    builder.ret(current_value)

    builder.position_at_end(raw_not_found)
    builder.ret(ir.Constant(I64, -1))


def _emit_pythonic_search(module: ir.Module) -> None:
    ptr_i64 = I64.as_pointer()
    fn_ty = ir.FunctionType(I64, [ptr_i64, I64, I64])

    py_func = ir.Function(module, fn_ty, name="find_first_ge_pythonic")
    search = ResultCarrierExit(py_func, "py_find_first_ge")
    builder = search.builder

    builder.position_at_end(search.loop_block)
    loop_index = builder.phi(I64, name="index")
    loop_index.add_incoming(ir.Constant(I64, 0), search.entry_block)
    reached_end = builder.icmp_signed(">=", loop_index, py_func.args[1], name="reached_end")
    builder.cbranch(reached_end, search.not_found_block, search.scan_block)

    builder.position_at_end(search.scan_block)
    element_ptr = builder.gep(py_func.args[0], [loop_index], inbounds=True, name="element_ptr")
    current_value = builder.load(element_ptr, name="current_value")
    meets_threshold = builder.icmp_signed(
        ">=", current_value, py_func.args[2], name="meets_threshold"
    )
    next_index = builder.add(loop_index, ir.Constant(I64, 1), name="next_index")
    loop_index.add_incoming(next_index, search.scan_block)
    builder.cbranch(meets_threshold, search.found_block, search.loop_block)

    with search.found():
        search.remember(current_value)

    with search.not_found():
        search.remember(ir.Constant(I64, -1))

    result = search.finish(I64, name="result")
    builder.ret(result)


def _emit_raw_multi_stage_search(module: ir.Module) -> None:
    fn_ty = ir.FunctionType(I64, [SEARCH_RECORD_PTR, I64, I64, I64])

    raw_func = ir.Function(module, fn_ty, name="find_first_visible_length_value_raw")
    raw_entry = raw_func.append_basic_block(name="entry")
    raw_loop = raw_func.append_basic_block(name="loop")
    raw_scan = raw_func.append_basic_block(name="scan")
    raw_visible = raw_func.append_basic_block(name="visible")
    raw_same_length = raw_func.append_basic_block(name="same_length")
    raw_same_value = raw_func.append_basic_block(name="same_value")
    raw_continue = raw_func.append_basic_block(name="continue")
    raw_not_found = raw_func.append_basic_block(name="not_found")
    raw_exit = raw_func.append_basic_block(name="exit")

    builder = ir.IRBuilder(raw_entry)
    builder.branch(raw_loop)

    builder.position_at_end(raw_loop)
    cursor = builder.phi(I64, name="cursor")
    cursor.add_incoming(ir.Constant(I64, 0), raw_entry)
    reached_end = builder.icmp_signed(">=", cursor, raw_func.args[1], name="reached_end")
    builder.cbranch(reached_end, raw_not_found, raw_scan)

    builder.position_at_end(raw_scan)
    record_ptr_value = builder.gep(raw_func.args[0], [cursor], inbounds=True, name="record_ptr")
    record = StagedRecordView(builder, record_ptr_value)
    hidden_bits = builder.and_(record.flags(), HIDDEN_MASK, name="hidden_bits")
    is_visible = builder.icmp_unsigned("==", hidden_bits, ir.Constant(I64, 0), name="is_visible")
    builder.cbranch(is_visible, raw_visible, raw_continue)

    builder.position_at_end(raw_visible)
    length = record.length()
    same_length = builder.icmp_signed("==", length, raw_func.args[2], name="same_length")
    builder.cbranch(same_length, raw_same_length, raw_continue)

    builder.position_at_end(raw_same_length)
    current_value = record.value()
    matches_value = builder.icmp_signed("==", current_value, raw_func.args[3], name="matches_value")
    builder.cbranch(matches_value, raw_same_value, raw_continue)

    builder.position_at_end(raw_same_value)
    builder.branch(raw_exit)

    builder.position_at_end(raw_continue)
    next_cursor = builder.add(cursor, ir.Constant(I64, 1), name="next_cursor")
    cursor.add_incoming(next_cursor, raw_continue)
    builder.branch(raw_loop)

    builder.position_at_end(raw_not_found)
    builder.branch(raw_exit)

    builder.position_at_end(raw_exit)
    result = builder.phi(I64, name="result")
    result.add_incoming(current_value, raw_same_value)
    result.add_incoming(ir.Constant(I64, -1), raw_not_found)
    builder.ret(result)


def _emit_pythonic_multi_stage_search(module: ir.Module) -> None:
    fn_ty = ir.FunctionType(I64, [SEARCH_RECORD_PTR, I64, I64, I64])

    py_func = ir.Function(module, fn_ty, name="find_first_visible_length_value_pythonic")
    search = StagedResultSearch(py_func, "py_find_visible_length_value")
    builder = search.builder

    cursor, record = search.begin(py_func.args[0], py_func.args[1])
    hidden_bits = builder.and_(record.flags(), HIDDEN_MASK, name="hidden_bits")
    is_visible = builder.icmp_unsigned("==", hidden_bits, ir.Constant(I64, 0), name="is_visible")

    with search.require("visible", is_visible):
        length = record.length()
        same_length = builder.icmp_signed("==", length, py_func.args[2], name="same_length")
        with search.require("same_length", same_length):
            current_value = record.value()
            matches_value = builder.icmp_signed(
                "==", current_value, py_func.args[3], name="matches_value"
            )
            with search.require("same_value", matches_value):
                search.accept(current_value)

    search.advance(cursor)
    result = search.finish(ir.Constant(I64, -1))
    builder.ret(result)


def build_search_module() -> ir.Module:
    module = ir.Module(name="result_carrier_phi_sentinels")
    module.triple = binding.get_default_triple()

    _emit_raw_search(module)
    _emit_pythonic_search(module)
    _emit_raw_multi_stage_search(module)
    _emit_pythonic_multi_stage_search(module)
    return module


def compile_module(module: ir.Module) -> CompiledSearchDemo:
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    return CompiledSearchDemo(
        llvm_ir=llvm_ir,
        engine=engine,
        raw_search_addr=engine.get_function_address("find_first_ge_raw"),
        pythonic_search_addr=engine.get_function_address("find_first_ge_pythonic"),
        raw_multi_stage_search_addr=engine.get_function_address("find_first_visible_length_value_raw"),
        pythonic_multi_stage_search_addr=engine.get_function_address("find_first_visible_length_value_pythonic"),
    )


def make_search_fn(address: int) -> ctypes._CFuncPtr:
    signature = ctypes.CFUNCTYPE(
        ctypes.c_int64,
        ctypes.POINTER(ctypes.c_int64),
        ctypes.c_int64,
        ctypes.c_int64,
    )
    return signature(address)


class SearchRecord(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_int64),
        ("length", ctypes.c_int64),
        ("value", ctypes.c_int64),
    ]


def make_record_search_fn(address: int) -> ctypes._CFuncPtr:
    signature = ctypes.CFUNCTYPE(
        ctypes.c_int64,
        ctypes.POINTER(SearchRecord),
        ctypes.c_int64,
        ctypes.c_int64,
        ctypes.c_int64,
    )
    return signature(address)


def as_i64_array(values: list[int]) -> tuple[ctypes.Array[ctypes.c_int64], ctypes.POINTER(ctypes.c_int64)]:
    array_type = ctypes.c_int64 * len(values)
    array = array_type(*values)
    return array, ctypes.cast(array, ctypes.POINTER(ctypes.c_int64))


def format_values(values: list[int]) -> str:
    return "[" + ", ".join(str(value) for value in values) + "]"


def as_records(rows: list[tuple[int, int, int]]) -> ctypes.Array[SearchRecord]:
    array_type = SearchRecord * len(rows)
    return array_type(*(SearchRecord(*row) for row in rows))


def main() -> None:
    _configure_llvm()
    compiled = compile_module(build_search_module())
    raw_search = make_search_fn(compiled.raw_search_addr)
    pythonic_search = make_search_fn(compiled.pythonic_search_addr)
    raw_window_search = make_record_search_fn(compiled.raw_multi_stage_search_addr)
    pythonic_window_search = make_record_search_fn(compiled.pythonic_multi_stage_search_addr)

    cases = [
        ([4, 7, 11, 15], 10),
        ([1, 3, 5], 4),
        ([2, 6, 8], 2),
    ]

    print("== Question ==")
    print("When should a search carry its answer through one exit block with a result phi, and how does that differ from the loop cursor phi?")
    print()

    print("== Sentinel Contract ==")
    print("This lab uses -1 to mean 'not found'. That is a host-level contract, not something LLVM understands.")
    print()

    print("== Target Triple ==")
    print(binding.get_default_triple())
    print()

    print("== Generated IR ==")
    print(compiled.llvm_ir.rstrip())
    print()

    print("== Raw vs Pythonic ==")
    for values, needle in cases:
        array, ptr = as_i64_array(values)
        raw_result = raw_search(ptr, len(values), needle)
        pythonic_result = pythonic_search(ptr, len(values), needle)
        print(
            f"values={format_values(values):<18} needle={needle:>2} -> "
            f"raw_search={raw_result:>3} | pythonic_search={pythonic_result:>3}"
        )
    print()

    staged_cases = [
        ([(1, 5, 11), (0, 4, 7), (0, 5, 9), (0, 5, 12)], 5, 9),
        ([(1, 3, 3), (0, 2, 8), (0, 3, 6), (0, 3, 10)], 3, 6),
        ([(1, 4, 12), (0, 4, 8), (0, 5, 8), (0, 5, 14)], 5, 14),
    ]

    print("== Multi-Stage Early Exit ==")
    for rows, length, needle in staged_cases:
        records = as_records(rows)
        raw_result = raw_window_search(records, len(rows), length, needle)
        pythonic_result = pythonic_window_search(records, len(rows), length, needle)
        summary = ", ".join(
            f"(hidden={flags}, len={record_length}, value={value})"
            for flags, record_length, value in rows
        )
        print(
            f"records=[{summary}] target_len={length:>2} needle={needle:>2} -> "
            f"raw_window_search={raw_result:>3} | pythonic_window_search={pythonic_result:>3}"
        )
    print()

    print("== What To Notice ==")
    print("The raw versions are the source of truth: they keep the loop cursor phi separate from the result phi and spell out the staged branches directly.")
    print("The Pythonic versions keep the same CFG visible, but the staged-search helper now carries the real protocol: visible candidate, matching length, matching value, one semantic result.")
    print("The richer multi-stage search is closer to the old `~/fyth` shape: cheap reject, cheap reject, deeper compare, one exit block with a result phi.")


if __name__ == "__main__":
    main()
