"""Demonstrate explicit host symbol exposure to llvmlite JIT code."""

from __future__ import annotations

import ctypes

from llvmlite import binding, ir


I64 = ir.IntType(64)
HOST_SYMBOL_NAME = "fythvm_host_scale_and_record"


def ensure_llvm_initialized() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def build_module() -> ir.Module:
    module = ir.Module(name="host_symbol_exposure")
    module.triple = binding.get_default_triple()

    host_scale = ir.Function(
        module,
        ir.FunctionType(I64, [I64]),
        name=HOST_SYMBOL_NAME,
    )

    func = ir.Function(
        module,
        ir.FunctionType(I64, [I64]),
        name="exercise_host_symbol",
    )
    block = func.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    first = builder.call(host_scale, [func.args[0]], name="first")
    second_arg = builder.add(func.args[0], I64(1), name="next_input")
    second = builder.call(host_scale, [second_arg], name="second")
    builder.ret(builder.add(first, second, name="combined_result"))

    return module


def main() -> None:
    ensure_llvm_initialized()
    call_log: list[int] = []

    @ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)
    def host_scale_and_record(value: int) -> int:
        call_log.append(int(value))
        return value * 10

    symbol_addr = ctypes.cast(host_scale_and_record, ctypes.c_void_p).value
    assert symbol_addr is not None
    binding.add_symbol(HOST_SYMBOL_NAME, symbol_addr)

    module = build_module()
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    func_addr = engine.get_function_address("exercise_host_symbol")
    exercise_host_symbol = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)(func_addr)
    result = exercise_host_symbol(7)

    print("== Question ==")
    print("How do you expose a host-owned Python callback to JITed llvmlite code?")
    print()
    print("== Generated IR ==")
    print(llvm_ir.rstrip())
    print()
    print("== Registered Host Symbol ==")
    print(f"name: {HOST_SYMBOL_NAME}")
    print(f"address: 0x{symbol_addr:x}")
    print()
    print("== JIT Call ==")
    print(f"exercise_host_symbol address: 0x{func_addr:x}")
    print(f"exercise_host_symbol(7) -> {result}")
    print()
    print("== Host Call Log ==")
    print(call_log)
    print()
    print("== Takeaway ==")
    print("Expose host callbacks explicitly with llvm.add_symbol and keep the callback object alive.")


if __name__ == "__main__":
    main()
