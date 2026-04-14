"""Smoke tests for llvmlite integration."""

from llvmlite import ir, binding


def test_llvmlite_import() -> None:
    """Verify llvmlite can be imported and provides a valid target triple."""
    triple = binding.get_default_triple()
    assert isinstance(triple, str)
    assert len(triple) > 0


def test_llvmlite_jit_add() -> None:
    """Build a trivial add(a, b) function and JIT-execute it."""
    # -- IR generation --
    i64 = ir.IntType(64)
    fn_ty = ir.FunctionType(i64, [i64, i64])
    module = ir.Module(name="test_module")
    func = ir.Function(module, fn_ty, name="add")
    block = func.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    result = builder.add(func.args[0], func.args[1], name="res")
    builder.ret(result)

    # -- JIT compilation --
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()

    llvm_ir = str(module)
    mod = binding.parse_assembly(llvm_ir)
    mod.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(mod, target_machine)

    import ctypes

    func_ptr = engine.get_function_address("add")
    assert func_ptr != 0

    cfunc = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64, ctypes.c_int64)(func_ptr)
    assert cfunc(3, 4) == 7
    assert cfunc(-1, 1) == 0
