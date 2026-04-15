"""Demonstrate direct wiring of LLVM mem* intrinsics in llvmlite."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import binding, ir


i1 = ir.IntType(1)
i8 = ir.IntType(8)
i64 = ir.IntType(64)
i8p = i8.as_pointer()


def configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def bytes_literal(data: bytes) -> str:
    return " ".join(f"{byte:02x}" for byte in data)


def read_bytes(address: int, size: int) -> bytes:
    return ctypes.string_at(address, size)


def buffer_address(buffer: ctypes.Array[ctypes.c_char], offset: int = 0) -> int:
    return ctypes.addressof(buffer) + offset


def build_module() -> ir.Module:
    module = ir.Module(name="llvmlite_mem_intrinsics")
    module.triple = binding.get_default_triple()

    memcpy = module.declare_intrinsic("llvm.memcpy", [i8p, i8p, i64])
    memmove = module.declare_intrinsic("llvm.memmove", [i8p, i8p, i64])
    memset = module.declare_intrinsic("llvm.memset", [i8p, i64])

    copy_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), [i8p, i8p, i64]), name="copy_bytes")
    dst, src, count = copy_fn.args
    dst.name = "dst"
    src.name = "src"
    count.name = "count"
    builder = ir.IRBuilder(copy_fn.append_basic_block(name="entry"))
    builder.call(memcpy, [dst, src, count, i1(0)])
    builder.ret_void()

    move_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), [i8p, i8p, i64]), name="move_bytes")
    dst, src, count = move_fn.args
    dst.name = "dst"
    src.name = "src"
    count.name = "count"
    builder = ir.IRBuilder(move_fn.append_basic_block(name="entry"))
    builder.call(memmove, [dst, src, count, i1(0)])
    builder.ret_void()

    fill_fn = ir.Function(module, ir.FunctionType(ir.VoidType(), [i8p, i8, i64]), name="fill_bytes")
    dst, byte_value, count = fill_fn.args
    dst.name = "dst"
    byte_value.name = "byte_value"
    count.name = "count"
    builder = ir.IRBuilder(fill_fn.append_basic_block(name="entry"))
    builder.call(memset, [dst, byte_value, count, i1(0)])
    builder.ret_void()

    return module


@dataclass(frozen=True)
class CompiledModule:
    llvm_ir: str
    engine: binding.ExecutionEngine
    copy_bytes_addr: int
    move_bytes_addr: int
    fill_bytes_addr: int


def compile_module(module: ir.Module) -> CompiledModule:
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    return CompiledModule(
        llvm_ir=llvm_ir,
        engine=engine,
        copy_bytes_addr=engine.get_function_address("copy_bytes"),
        move_bytes_addr=engine.get_function_address("move_bytes"),
        fill_bytes_addr=engine.get_function_address("fill_bytes"),
    )


def call_void_p_p_i64(address: int) -> ctypes.CFUNCTYPE:
    return ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64)(address)


def call_void_p_i8_i64(address: int) -> ctypes.CFUNCTYPE:
    return ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint64)(address)


def run_memcpy_demo(compiled: CompiledModule) -> tuple[str, str]:
    copy_bytes = call_void_p_p_i64(compiled.copy_bytes_addr)
    src = ctypes.create_string_buffer(b"OpenAI!!", 8)
    dst = ctypes.create_string_buffer(b"\x00" * 8, 8)

    before = f"src={bytes_literal(read_bytes(buffer_address(src), 8))} dst={bytes_literal(read_bytes(buffer_address(dst), 8))}"
    copy_bytes(buffer_address(dst), buffer_address(src), 8)
    after = f"src={bytes_literal(read_bytes(buffer_address(src), 8))} dst={bytes_literal(read_bytes(buffer_address(dst), 8))}"
    return before, after


def run_memmove_demo(compiled: CompiledModule) -> tuple[str, str]:
    move_bytes = call_void_p_p_i64(compiled.move_bytes_addr)
    buf = ctypes.create_string_buffer(b"abcdefgh", 8)

    before = bytes_literal(read_bytes(buffer_address(buf), 8))
    move_bytes(buffer_address(buf, 2), buffer_address(buf), 6)
    after = bytes_literal(read_bytes(buffer_address(buf), 8))
    return before, after


def run_memset_demo(compiled: CompiledModule) -> tuple[str, str]:
    fill_bytes = call_void_p_i8_i64(compiled.fill_bytes_addr)
    buf = ctypes.create_string_buffer(b"........", 8)

    before = bytes_literal(read_bytes(buffer_address(buf), 8))
    fill_bytes(buffer_address(buf, 2), 0x5A, 4)
    after = bytes_literal(read_bytes(buffer_address(buf), 8))
    return before, after


def main() -> None:
    configure_llvm()
    compiled = compile_module(build_module())

    memcpy_before, memcpy_after = run_memcpy_demo(compiled)
    memmove_before, memmove_after = run_memmove_demo(compiled)
    memset_before, memset_after = run_memset_demo(compiled)

    print("== Question ==")
    print("How do you wire LLVM mem* intrinsics in llvmlite when IRBuilder does not expose memcpy/memmove/memset helpers?")
    print()

    print("== LLVM IR ==")
    print(compiled.llvm_ir.rstrip())
    print()

    print("== memcpy Demo ==")
    print("before:", memcpy_before)
    print("after: ", memcpy_after)
    print()

    print("== memmove Demo ==")
    print("before:", memmove_before)
    print("after: ", memmove_after)
    print("expected overlap-safe result:", bytes_literal(b"ababcdef"))
    print()

    print("== memset Demo ==")
    print("before:", memset_before)
    print("after: ", memset_after)
    print("expected fill result:      ", bytes_literal(b"..ZZZZ.."))
    print()

    print("== Takeaway ==")
    print("llvmlite exposes the mem* intrinsics through Module.declare_intrinsic(...), not through IRBuilder.memcpy/memmove/memset helpers.")
    print("The actual operation is still just a normal call with one extra trailing i1 isvolatile flag.")


if __name__ == "__main__":
    main()
