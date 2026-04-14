"""Demonstrate a small explicit bridge from llvmlite IR types to ctypes."""

from __future__ import annotations

import ctypes

from llvmlite import binding, ir


I32 = ir.IntType(32)
I64 = ir.IntType(64)


def ensure_llvm_initialized() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def map_ir_struct_to_ctypes(ir_struct_type: ir.LiteralStructType) -> type[ctypes.Structure]:
    fields = [
        (f"field_{index:02d}", map_ir_type_to_ctypes(field))
        for index, field in enumerate(ir_struct_type.elements)
    ]
    return type("MappedStruct", (ctypes.Structure,), {"_fields_": fields})


def map_ir_type_to_ctypes(ir_type: ir.Type):
    if isinstance(ir_type, ir.IntType):
        if ir_type.width == 8:
            return ctypes.c_byte
        if ir_type.width == 32:
            return ctypes.c_int32
        if ir_type.width == 64:
            return ctypes.c_int64
        raise ValueError(f"Unsupported integer width: {ir_type.width}")

    if isinstance(ir_type, ir.ArrayType):
        element_type = map_ir_type_to_ctypes(ir_type.element)
        return element_type * ir_type.count

    if isinstance(ir_type, ir.LiteralStructType):
        return map_ir_struct_to_ctypes(ir_type)

    if isinstance(ir_type, ir.PointerType):
        pointee = map_ir_type_to_ctypes(ir_type.pointee)
        return ctypes.POINTER(pointee)

    if isinstance(ir_type, ir.FunctionType):
        restype = map_ir_type_to_ctypes(ir_type.return_type)
        argtypes = [map_ir_type_to_ctypes(arg) for arg in ir_type.args]
        return ctypes.CFUNCTYPE(restype, *argtypes)

    if isinstance(ir_type, ir.VoidType):
        return None

    raise ValueError(f"Unsupported IR type: {ir_type}")


def describe_ctypes_type(ctype: object) -> str:
    if isinstance(ctype, type) and issubclass(ctype, ctypes.Structure):
        return f"{ctype.__name__} fields={getattr(ctype, '_fields_')}"
    if isinstance(ctype, type) and issubclass(ctype, ctypes.Array):
        return f"{ctype.__name__} length={ctype._length_} element={ctype._type_.__name__}"
    if isinstance(ctype, type) and issubclass(ctype, ctypes._Pointer):  # pyright: ignore[reportPrivateUsage]
        return f"{ctype.__name__} -> {ctype._type_.__name__}"
    if isinstance(ctype, type) and issubclass(ctype, ctypes._CFuncPtr):  # pyright: ignore[reportPrivateUsage]
        return f"{ctype.__name__} restype={ctype._restype_} argtypes={ctype._argtypes_}"
    if ctype is None:
        return "None"
    return getattr(ctype, "__name__", repr(ctype))


def build_module() -> tuple[ir.Module, ir.LiteralStructType, ir.FunctionType]:
    module = ir.Module(name="ir_to_ctypes_bridge")
    module.triple = binding.get_default_triple()

    pair_type = ir.LiteralStructType([I32, I64])
    pair_data = ir.GlobalVariable(module, pair_type, name="pair_data")
    pair_data.initializer = ir.Constant(pair_type, [I32(7), I64(11)])

    function_type = ir.FunctionType(I64, [I64, I64])
    func = ir.Function(module, function_type, name="sum_scaled")
    block = func.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    doubled = builder.mul(func.args[0], I64(2), name="doubled_left")
    tripled = builder.mul(func.args[1], I64(3), name="tripled_right")
    builder.ret(builder.add(doubled, tripled, name="result"))

    return module, pair_type, function_type


def main() -> None:
    ensure_llvm_initialized()
    module, pair_type, function_type = build_module()
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    mapped_i32 = map_ir_type_to_ctypes(I32)
    mapped_array = map_ir_type_to_ctypes(ir.ArrayType(ir.IntType(8), 4))
    mapped_struct = map_ir_type_to_ctypes(pair_type)
    mapped_func = map_ir_type_to_ctypes(function_type)

    pair_addr = engine.get_global_value_address("pair_data")
    function_addr = engine.get_function_address("sum_scaled")
    pair_view = mapped_struct.from_address(pair_addr)
    sum_scaled = mapped_func(function_addr)

    print("== Question ==")
    print("How do you turn llvmlite IR types into ctypes wrappers that work against live JIT addresses?")
    print()
    print("== Generated IR ==")
    print(llvm_ir.rstrip())
    print()
    print("== Type Map ==")
    print(f"i32 -> {describe_ctypes_type(mapped_i32)}")
    print(f"[4 x i8] -> {describe_ctypes_type(mapped_array)}")
    print(f"{{i32, i64}} -> {describe_ctypes_type(mapped_struct)}")
    print(f"i64 (i64, i64) -> {describe_ctypes_type(mapped_func)}")
    print()
    print("== Global Struct Read ==")
    print(f"pair_data address: 0x{pair_addr:x}")
    print(f"pair_data.field_00 = {pair_view.field_00}")
    print(f"pair_data.field_01 = {pair_view.field_01}")
    print()
    print("== Function Call ==")
    print(f"sum_scaled address: 0x{function_addr:x}")
    print(f"sum_scaled(5, 9) -> {sum_scaled(5, 9)}")
    print()
    print("== Takeaway ==")
    print("Keep the IR-to-ctypes bridge small, explicit, and validated against real JIT addresses.")


if __name__ == "__main__":
    main()
