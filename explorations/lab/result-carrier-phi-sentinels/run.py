"""Show how a final phi can carry a search result or a sentinel."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import binding, ir


@dataclass(frozen=True)
class CompiledSearchDemo:
    llvm_ir: str
    engine: binding.ExecutionEngine
    phi_search_addr: int
    multi_return_search_addr: int


def _configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def build_search_module() -> ir.Module:
    i64 = ir.IntType(64)
    ptr_i64 = i64.as_pointer()

    module = ir.Module(name="result_carrier_phi_sentinels")
    module.triple = binding.get_default_triple()

    fn_ty = ir.FunctionType(i64, [ptr_i64, i64, i64])

    phi_func = ir.Function(module, fn_ty, name="find_first_ge_phi")
    phi_entry = phi_func.append_basic_block(name="entry")
    phi_loop = phi_func.append_basic_block(name="loop")
    phi_scan = phi_func.append_basic_block(name="scan")
    phi_found = phi_func.append_basic_block(name="found")
    phi_not_found = phi_func.append_basic_block(name="not_found")
    phi_exit = phi_func.append_basic_block(name="exit")

    builder = ir.IRBuilder(phi_entry)
    builder.branch(phi_loop)

    builder.position_at_end(phi_loop)
    loop_index = builder.phi(i64, name="index")
    loop_index.add_incoming(ir.Constant(i64, 0), phi_entry)
    reached_end = builder.icmp_signed(">=", loop_index, phi_func.args[1], name="reached_end")
    builder.cbranch(reached_end, phi_not_found, phi_scan)

    builder.position_at_end(phi_scan)
    element_ptr = builder.gep(phi_func.args[0], [loop_index], inbounds=True, name="element_ptr")
    current_value = builder.load(element_ptr, name="current_value")
    meets_threshold = builder.icmp_signed(
        ">=", current_value, phi_func.args[2], name="meets_threshold"
    )
    next_index = builder.add(loop_index, ir.Constant(i64, 1), name="next_index")
    loop_index.add_incoming(next_index, phi_scan)
    builder.cbranch(meets_threshold, phi_found, phi_loop)

    builder.position_at_end(phi_found)
    builder.branch(phi_exit)

    builder.position_at_end(phi_not_found)
    builder.branch(phi_exit)

    builder.position_at_end(phi_exit)
    result = builder.phi(i64, name="result")
    result.add_incoming(current_value, phi_found)
    result.add_incoming(ir.Constant(i64, -1), phi_not_found)
    builder.ret(result)

    multi_func = ir.Function(module, fn_ty, name="find_first_ge_multi_return")
    multi_entry = multi_func.append_basic_block(name="entry")
    multi_loop = multi_func.append_basic_block(name="loop")
    multi_scan = multi_func.append_basic_block(name="scan")
    multi_found = multi_func.append_basic_block(name="found")
    multi_not_found = multi_func.append_basic_block(name="not_found")

    builder = ir.IRBuilder(multi_entry)
    builder.branch(multi_loop)

    builder.position_at_end(multi_loop)
    multi_index = builder.phi(i64, name="index")
    multi_index.add_incoming(ir.Constant(i64, 0), multi_entry)
    multi_reached_end = builder.icmp_signed(">=", multi_index, multi_func.args[1], name="reached_end")
    builder.cbranch(multi_reached_end, multi_not_found, multi_scan)

    builder.position_at_end(multi_scan)
    multi_element_ptr = builder.gep(
        multi_func.args[0], [multi_index], inbounds=True, name="element_ptr"
    )
    multi_current_value = builder.load(multi_element_ptr, name="current_value")
    multi_meets_threshold = builder.icmp_signed(
        ">=", multi_current_value, multi_func.args[2], name="meets_threshold"
    )
    multi_next_index = builder.add(multi_index, ir.Constant(i64, 1), name="next_index")
    multi_index.add_incoming(multi_next_index, multi_scan)
    builder.cbranch(multi_meets_threshold, multi_found, multi_loop)

    builder.position_at_end(multi_found)
    builder.ret(multi_current_value)

    builder.position_at_end(multi_not_found)
    builder.ret(ir.Constant(i64, -1))

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
        phi_search_addr=engine.get_function_address("find_first_ge_phi"),
        multi_return_search_addr=engine.get_function_address("find_first_ge_multi_return"),
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
    phi_search = make_search_fn(compiled.phi_search_addr)
    multi_return_search = make_search_fn(compiled.multi_return_search_addr)

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

    print("== Runtime Results ==")
    for values, needle in cases:
        array, ptr = as_i64_array(values)
        phi_result = phi_search(ptr, len(values), needle)
        multi_result = multi_return_search(ptr, len(values), needle)
        print(
            f"values={format_values(values):<18} needle={needle:>2} -> "
            f"phi={phi_result:>3} | multi_return={multi_result:>3}"
        )
    print()

    print("== What To Notice ==")
    print("The phi version keeps one exit block and one result contract for the whole search.")
    print("The multi-return version is still verifier-valid, but the meaning of 'found or -1' is split across several return blocks.")


if __name__ == "__main__":
    main()
