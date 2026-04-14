"""A minimal end-to-end llvmlite JIT exploration."""

from __future__ import annotations

import ctypes

from llvmlite import binding, ir


def build_add_module() -> ir.Module:
    """Build the smallest useful function for a baseline JIT example."""
    i64 = ir.IntType(64)
    fn_ty = ir.FunctionType(i64, [i64, i64])
    module = ir.Module(name="exploration_jit_add")
    module.triple = binding.get_default_triple()
    func = ir.Function(module, fn_ty, name="add")
    block = func.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    result = builder.add(func.args[0], func.args[1], name="res")
    builder.ret(result)
    return module


def compile_and_get_address(
    module: ir.Module,
) -> tuple[str, binding.ExecutionEngine, int]:
    """Verify the module and return the IR plus a live engine and callable address."""
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()

    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()
    address = engine.get_function_address("add")
    return llvm_ir, engine, address


def main() -> None:
    module = build_add_module()
    # Keep the engine alive for as long as any derived function pointer is used.
    llvm_ir, _engine, address = compile_and_get_address(module)

    print("== Question ==")
    print("What is the smallest complete llvmlite JIT pipeline?")
    print()
    print("== Target Triple ==")
    print(binding.get_default_triple())
    print()
    print("== Generated IR ==")
    print(llvm_ir.rstrip())
    print()
    print("== Execution ==")
    print(f"function address: 0x{address:x}")

    cfunc = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64, ctypes.c_int64)(address)
    samples = [(3, 4), (-1, 1)]
    for left, right in samples:
        result = cfunc(left, right)
        print(f"add({left}, {right}) -> {result}")

    print()
    print("== Takeaway ==")
    print("Use this as a baseline when you want to vary one llvmlite concern at a time.")


if __name__ == "__main__":
    main()
