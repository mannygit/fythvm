"""Show how a final phi can carry a search result or a sentinel."""

from __future__ import annotations

import ctypes
from contextlib import contextmanager
from dataclasses import dataclass

from llvmlite import binding, ir


@dataclass(frozen=True)
class CompiledSearchDemo:
    llvm_ir: str
    engine: binding.ExecutionEngine
    raw_search_addr: int
    pythonic_search_addr: int


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


def _configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def _emit_raw_search(module: ir.Module) -> None:
    i64 = ir.IntType(64)
    ptr_i64 = i64.as_pointer()
    fn_ty = ir.FunctionType(i64, [ptr_i64, i64, i64])

    raw_func = ir.Function(module, fn_ty, name="find_first_ge_raw")
    raw_entry = raw_func.append_basic_block(name="entry")
    raw_loop = raw_func.append_basic_block(name="loop")
    raw_scan = raw_func.append_basic_block(name="scan")
    raw_found = raw_func.append_basic_block(name="found")
    raw_not_found = raw_func.append_basic_block(name="not_found")

    builder = ir.IRBuilder(raw_entry)
    builder.branch(raw_loop)

    builder.position_at_end(raw_loop)
    loop_index = builder.phi(i64, name="index")
    loop_index.add_incoming(ir.Constant(i64, 0), raw_entry)
    reached_end = builder.icmp_signed(">=", loop_index, raw_func.args[1], name="reached_end")
    builder.cbranch(reached_end, raw_not_found, raw_scan)

    builder.position_at_end(raw_scan)
    element_ptr = builder.gep(raw_func.args[0], [loop_index], inbounds=True, name="element_ptr")
    current_value = builder.load(element_ptr, name="current_value")
    meets_threshold = builder.icmp_signed(
        ">=", current_value, raw_func.args[2], name="meets_threshold"
    )
    next_index = builder.add(loop_index, ir.Constant(i64, 1), name="next_index")
    loop_index.add_incoming(next_index, raw_scan)
    builder.cbranch(meets_threshold, raw_found, raw_loop)

    builder.position_at_end(raw_found)
    builder.ret(current_value)

    builder.position_at_end(raw_not_found)
    builder.ret(ir.Constant(i64, -1))


def _emit_pythonic_search(module: ir.Module) -> None:
    i64 = ir.IntType(64)
    ptr_i64 = i64.as_pointer()
    fn_ty = ir.FunctionType(i64, [ptr_i64, i64, i64])

    py_func = ir.Function(module, fn_ty, name="find_first_ge_pythonic")
    search = ResultCarrierExit(py_func, "py_find_first_ge")
    builder = search.builder

    builder.position_at_end(search.loop_block)
    loop_index = builder.phi(i64, name="index")
    loop_index.add_incoming(ir.Constant(i64, 0), search.entry_block)
    reached_end = builder.icmp_signed(">=", loop_index, py_func.args[1], name="reached_end")
    builder.cbranch(reached_end, search.not_found_block, search.scan_block)

    builder.position_at_end(search.scan_block)
    element_ptr = builder.gep(py_func.args[0], [loop_index], inbounds=True, name="element_ptr")
    current_value = builder.load(element_ptr, name="current_value")
    meets_threshold = builder.icmp_signed(
        ">=", current_value, py_func.args[2], name="meets_threshold"
    )
    next_index = builder.add(loop_index, ir.Constant(i64, 1), name="next_index")
    loop_index.add_incoming(next_index, search.scan_block)
    builder.cbranch(meets_threshold, search.found_block, search.loop_block)

    with search.found():
        search.remember(current_value)

    with search.not_found():
        search.remember(ir.Constant(i64, -1))

    result = search.finish(i64, name="result")
    builder.ret(result)


def build_search_module() -> ir.Module:
    module = ir.Module(name="result_carrier_phi_sentinels")
    module.triple = binding.get_default_triple()

    _emit_raw_search(module)
    _emit_pythonic_search(module)
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
    )


def make_search_fn(address: int) -> ctypes._CFuncPtr:
    signature = ctypes.CFUNCTYPE(
        ctypes.c_int64,
        ctypes.POINTER(ctypes.c_int64),
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


def main() -> None:
    _configure_llvm()
    compiled = compile_module(build_search_module())
    raw_search = make_search_fn(compiled.raw_search_addr)
    pythonic_search = make_search_fn(compiled.pythonic_search_addr)

    cases = [
        ([4, 7, 11, 15], 10),
        ([1, 3, 5], 4),
        ([2, 6, 8], 2),
    ]

    print("== Question ==")
    print("When should a loop's final phi carry the semantic result of a search instead of branching to separate returns?")
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

    print("== What To Notice ==")
    print("The raw version is the source of truth: the search still has explicit loop, found, and not_found blocks.")
    print("The Pythonic version keeps that CFG visible, but a tiny helper centralizes the exit phi and the sentinel contract.")
    print("Both forms still make the loop cursor phi and the result contract separate, which is the important SSA distinction.")


if __name__ == "__main__":
    main()
