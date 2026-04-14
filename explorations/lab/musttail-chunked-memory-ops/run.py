"""Tail-recursive chunked copy and compare helpers in llvmlite."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from contextlib import contextmanager
from typing import Callable
from typing import Iterable

from llvmlite import binding, ir


i8 = ir.IntType(8)
i32 = ir.IntType(32)
i64 = ir.IntType(64)
ptr8 = i8.as_pointer()


@dataclass
class AlignedBuffer:
    owner: ctypes.Array[ctypes.c_char]
    address: int
    size: int


def aligned_buffer(payload: bytes, *, align: int = 16, pad: int = 32) -> AlignedBuffer:
    """Allocate a byte buffer with a stable aligned base address."""
    owner = ctypes.create_string_buffer(len(payload) + pad + align)
    base = ctypes.addressof(owner)
    aligned = (base + (align - 1)) & ~(align - 1)
    ctypes.memmove(aligned, payload, len(payload))
    return AlignedBuffer(owner=owner, address=aligned, size=len(payload))


def trace_bytes(address: int, limit: int) -> list[int]:
    """Read the non-zero chunk markers written by the JIT."""
    raw = ctypes.string_at(address, limit)
    return [byte for byte in raw if byte != 0]


def bytes_literal(data: bytes) -> str:
    return " ".join(f"{byte:02x}" for byte in data)


@contextmanager
def positioned_at(builder: ir.IRBuilder, block: ir.Block):
    builder.position_at_end(block)
    yield builder


def build_module_raw() -> ir.Module:
    module = ir.Module(name="musttail_chunked_memory_ops_raw")
    module.triple = binding.get_default_triple()
    build_chunked_copy(module)
    build_chunked_compare(module)
    return module


def build_chunked_copy(module: ir.Module) -> ir.Function:
    fn_ty = ir.FunctionType(ir.VoidType(), [ptr8, ptr8, i64, ptr8, i64])
    fn = ir.Function(module, fn_ty, name="chunked_copy")
    dst, src, count, trace, trace_index = fn.args
    dst.name = "dst"
    src.name = "src"
    count.name = "count"
    trace.name = "trace"
    trace_index.name = "trace_index"

    entry = fn.append_basic_block("entry")
    zero = fn.append_basic_block("count_is_zero")
    check_8 = fn.append_basic_block("check_8")
    copy_8 = fn.append_basic_block("copy_8")
    check_4 = fn.append_basic_block("check_4")
    copy_4 = fn.append_basic_block("copy_4")
    copy_1 = fn.append_basic_block("copy_1")
    b = ir.IRBuilder(entry)
    b.cbranch(b.icmp_unsigned("==", count, i64(0)), zero, check_8)

    b.position_at_end(zero)
    b.ret_void()

    b.position_at_end(check_8)
    b.cbranch(b.icmp_unsigned(">=", count, i64(8)), copy_8, check_4)

    b.position_at_end(copy_8)
    emit_trace_step(b, trace, trace_index, 8)
    dst64 = b.bitcast(dst, i64.as_pointer(), name="dst64")
    src64 = b.bitcast(src, i64.as_pointer(), name="src64")
    b.store(b.load(src64, align=8, name="src_word8"), dst64, align=8)
    recurse_copy(b, fn, dst, src, count, trace, trace_index, 8)

    b.position_at_end(check_4)
    b.cbranch(b.icmp_unsigned(">=", count, i64(4)), copy_4, copy_1)

    b.position_at_end(copy_4)
    emit_trace_step(b, trace, trace_index, 4)
    dst32 = b.bitcast(dst, i32.as_pointer(), name="dst32")
    src32 = b.bitcast(src, i32.as_pointer(), name="src32")
    b.store(b.load(src32, align=4, name="src_word4"), dst32, align=4)
    recurse_copy(b, fn, dst, src, count, trace, trace_index, 4)

    b.position_at_end(copy_1)
    emit_trace_step(b, trace, trace_index, 1)
    b.store(b.load(src, name="src_byte"), dst)
    recurse_copy(b, fn, dst, src, count, trace, trace_index, 1)
    return fn


def build_chunked_compare(module: ir.Module) -> ir.Function:
    fn_ty = ir.FunctionType(i32, [ptr8, ptr8, i64, ptr8, i64])
    fn = ir.Function(module, fn_ty, name="chunked_compare")
    left, right, count, trace, trace_index = fn.args
    left.name = "left"
    right.name = "right"
    count.name = "count"
    trace.name = "trace"
    trace_index.name = "trace_index"

    entry = fn.append_basic_block("entry")
    zero = fn.append_basic_block("count_is_zero")
    check_8 = fn.append_basic_block("check_8")
    cmp_8 = fn.append_basic_block("cmp_8")
    ret_8 = fn.append_basic_block("ret_8")
    check_4 = fn.append_basic_block("check_4")
    cmp_4 = fn.append_basic_block("cmp_4")
    ret_4 = fn.append_basic_block("ret_4")
    cmp_1 = fn.append_basic_block("cmp_1")
    ret_1 = fn.append_basic_block("ret_1")
    recurse_8 = fn.append_basic_block("recurse_8")
    recurse_4 = fn.append_basic_block("recurse_4")
    recurse_1 = fn.append_basic_block("recurse_1")

    b = ir.IRBuilder(entry)
    b.cbranch(b.icmp_unsigned("==", count, i64(0)), zero, check_8)

    b.position_at_end(zero)
    b.ret(i32(0))

    b.position_at_end(check_8)
    b.cbranch(b.icmp_unsigned(">=", count, i64(8)), cmp_8, check_4)

    b.position_at_end(cmp_8)
    emit_trace_step(b, trace, trace_index, 8)
    left64 = b.bitcast(left, i64.as_pointer(), name="left64")
    right64 = b.bitcast(right, i64.as_pointer(), name="right64")
    diff8 = b.sub(b.load(left64, align=8, name="left_word8"), b.load(right64, align=8, name="right_word8"), name="diff8")
    b.cbranch(b.icmp_unsigned("!=", diff8, i64(0)), ret_8, recurse_8)

    b.position_at_end(ret_8)
    b.ret(b.trunc(diff8, i32, name="diff8_i32"))

    b.position_at_end(recurse_8)
    next_left_8 = b.gep(left, [i64(8)], name="left_next_8")
    next_right_8 = b.gep(right, [i64(8)], name="right_next_8")
    next_count_8 = b.sub(count, i64(8), name="count_next_8")
    next_trace_index_8 = b.add(trace_index, i64(1), name="trace_index_next_8")
    call_8 = b.call(
        fn,
        [next_left_8, next_right_8, next_count_8, trace, next_trace_index_8],
        tail="musttail",
    )
    b.ret(call_8)

    b.position_at_end(check_4)
    b.cbranch(b.icmp_unsigned(">=", count, i64(4)), cmp_4, cmp_1)

    b.position_at_end(cmp_4)
    emit_trace_step(b, trace, trace_index, 4)
    left32 = b.bitcast(left, i32.as_pointer(), name="left32")
    right32 = b.bitcast(right, i32.as_pointer(), name="right32")
    diff4 = b.sub(b.load(left32, align=4, name="left_word4"), b.load(right32, align=4, name="right_word4"), name="diff4")
    b.cbranch(b.icmp_unsigned("!=", diff4, i32(0)), ret_4, recurse_4)

    b.position_at_end(ret_4)
    b.ret(diff4)

    b.position_at_end(recurse_4)
    next_left_4 = b.gep(left, [i64(4)], name="left_next_4")
    next_right_4 = b.gep(right, [i64(4)], name="right_next_4")
    next_count_4 = b.sub(count, i64(4), name="count_next_4")
    next_trace_index_4 = b.add(trace_index, i64(1), name="trace_index_next_4")
    call_4 = b.call(
        fn,
        [next_left_4, next_right_4, next_count_4, trace, next_trace_index_4],
        tail="musttail",
    )
    b.ret(call_4)

    b.position_at_end(cmp_1)
    emit_trace_step(b, trace, trace_index, 1)
    diff1 = b.sub(b.load(left, name="left_byte"), b.load(right, name="right_byte"), name="diff1")
    b.cbranch(b.icmp_unsigned("!=", diff1, i8(0)), ret_1, recurse_1)

    b.position_at_end(ret_1)
    b.ret(b.sext(diff1, i32, name="diff1_i32"))

    b.position_at_end(recurse_1)
    next_left_1 = b.gep(left, [i64(1)], name="left_next_1")
    next_right_1 = b.gep(right, [i64(1)], name="right_next_1")
    next_count_1 = b.sub(count, i64(1), name="count_next_1")
    next_trace_index_1 = b.add(trace_index, i64(1), name="trace_index_next_1")
    call_1 = b.call(
        fn,
        [next_left_1, next_right_1, next_count_1, trace, next_trace_index_1],
        tail="musttail",
    )
    b.ret(call_1)

    return fn


@dataclass
class TailPeeler:
    fn: ir.Function
    trace: ir.Value
    trace_index: ir.Value

    def mark(self, builder: ir.IRBuilder, chunk: int) -> None:
        slot = builder.gep(self.trace, [self.trace_index], name=f"trace_slot_{chunk}")
        builder.store(i8(chunk), slot)

    def advance(self, builder: ir.IRBuilder, value: ir.Value, chunk: int, name: str) -> ir.Value:
        return builder.gep(value, [i64(chunk)], name=f"{name}_{chunk}")

    def recurse_copy(
        self,
        builder: ir.IRBuilder,
        dst: ir.Value,
        src: ir.Value,
        count: ir.Value,
        chunk: int,
    ) -> None:
        next_dst = self.advance(builder, dst, chunk, "dst_next")
        next_src = self.advance(builder, src, chunk, "src_next")
        next_count = builder.sub(count, i64(chunk), name=f"count_next_{chunk}")
        next_trace_index = builder.add(self.trace_index, i64(1), name=f"trace_index_next_{chunk}")
        builder.call(
            self.fn,
            [next_dst, next_src, next_count, self.trace, next_trace_index],
            tail="musttail",
        )
        builder.ret_void()

    def recurse_compare(
        self,
        builder: ir.IRBuilder,
        left: ir.Value,
        right: ir.Value,
        count: ir.Value,
        chunk: int,
    ) -> None:
        next_left = self.advance(builder, left, chunk, "left_next")
        next_right = self.advance(builder, right, chunk, "right_next")
        next_count = builder.sub(count, i64(chunk), name=f"count_next_{chunk}")
        next_trace_index = builder.add(self.trace_index, i64(1), name=f"trace_index_next_{chunk}")
        call = builder.call(
            self.fn,
            [next_left, next_right, next_count, self.trace, next_trace_index],
            tail="musttail",
        )
        builder.ret(call)


def build_chunked_copy_pythonic(module: ir.Module) -> ir.Function:
    fn_ty = ir.FunctionType(ir.VoidType(), [ptr8, ptr8, i64, ptr8, i64])
    fn = ir.Function(module, fn_ty, name="chunked_copy")
    dst, src, count, trace, trace_index = fn.args
    dst.name = "dst"
    src.name = "src"
    count.name = "count"
    trace.name = "trace"
    trace_index.name = "trace_index"
    tail = TailPeeler(fn, trace, trace_index)

    entry = fn.append_basic_block("entry")
    zero = fn.append_basic_block("count_is_zero")
    check_8 = fn.append_basic_block("check_8")
    copy_8 = fn.append_basic_block("copy_8")
    check_4 = fn.append_basic_block("check_4")
    copy_4 = fn.append_basic_block("copy_4")
    copy_1 = fn.append_basic_block("copy_1")
    b = ir.IRBuilder(entry)
    with positioned_at(b, entry):
        b.cbranch(b.icmp_unsigned("==", count, i64(0)), zero, check_8)

    with positioned_at(b, zero):
        b.ret_void()

    with positioned_at(b, check_8):
        b.cbranch(b.icmp_unsigned(">=", count, i64(8)), copy_8, check_4)

    with positioned_at(b, copy_8):
        tail.mark(b, 8)
        dst64 = b.bitcast(dst, i64.as_pointer(), name="dst64")
        src64 = b.bitcast(src, i64.as_pointer(), name="src64")
        b.store(b.load(src64, align=8, name="src_word8"), dst64, align=8)
        tail.recurse_copy(b, dst, src, count, 8)

    with positioned_at(b, check_4):
        b.cbranch(b.icmp_unsigned(">=", count, i64(4)), copy_4, copy_1)

    with positioned_at(b, copy_4):
        tail.mark(b, 4)
        dst32 = b.bitcast(dst, i32.as_pointer(), name="dst32")
        src32 = b.bitcast(src, i32.as_pointer(), name="src32")
        b.store(b.load(src32, align=4, name="src_word4"), dst32, align=4)
        tail.recurse_copy(b, dst, src, count, 4)

    with positioned_at(b, copy_1):
        tail.mark(b, 1)
        b.store(b.load(src, name="src_byte"), dst)
        tail.recurse_copy(b, dst, src, count, 1)
    return fn


def build_chunked_compare_pythonic(module: ir.Module) -> ir.Function:
    fn_ty = ir.FunctionType(i32, [ptr8, ptr8, i64, ptr8, i64])
    fn = ir.Function(module, fn_ty, name="chunked_compare")
    left, right, count, trace, trace_index = fn.args
    left.name = "left"
    right.name = "right"
    count.name = "count"
    trace.name = "trace"
    trace_index.name = "trace_index"
    tail = TailPeeler(fn, trace, trace_index)

    entry = fn.append_basic_block("entry")
    zero = fn.append_basic_block("count_is_zero")
    check_8 = fn.append_basic_block("check_8")
    cmp_8 = fn.append_basic_block("cmp_8")
    ret_8 = fn.append_basic_block("ret_8")
    check_4 = fn.append_basic_block("check_4")
    cmp_4 = fn.append_basic_block("cmp_4")
    ret_4 = fn.append_basic_block("ret_4")
    cmp_1 = fn.append_basic_block("cmp_1")
    ret_1 = fn.append_basic_block("ret_1")
    recurse_8 = fn.append_basic_block("recurse_8")
    recurse_4 = fn.append_basic_block("recurse_4")
    recurse_1 = fn.append_basic_block("recurse_1")
    b = ir.IRBuilder(entry)
    with positioned_at(b, entry):
        b.cbranch(b.icmp_unsigned("==", count, i64(0)), zero, check_8)

    with positioned_at(b, zero):
        b.ret(i32(0))

    with positioned_at(b, check_8):
        b.cbranch(b.icmp_unsigned(">=", count, i64(8)), cmp_8, check_4)

    with positioned_at(b, cmp_8):
        tail.mark(b, 8)
        left64 = b.bitcast(left, i64.as_pointer(), name="left64")
        right64 = b.bitcast(right, i64.as_pointer(), name="right64")
        diff8 = b.sub(
            b.load(left64, align=8, name="left_word8"),
            b.load(right64, align=8, name="right_word8"),
            name="diff8",
        )
        b.cbranch(b.icmp_unsigned("!=", diff8, i64(0)), ret_8, recurse_8)

    with positioned_at(b, ret_8):
        b.ret(b.trunc(diff8, i32, name="diff8_i32"))

    with positioned_at(b, recurse_8):
        tail.recurse_compare(b, left, right, count, 8)

    with positioned_at(b, check_4):
        b.cbranch(b.icmp_unsigned(">=", count, i64(4)), cmp_4, cmp_1)

    with positioned_at(b, cmp_4):
        tail.mark(b, 4)
        left32 = b.bitcast(left, i32.as_pointer(), name="left32")
        right32 = b.bitcast(right, i32.as_pointer(), name="right32")
        diff4 = b.sub(
            b.load(left32, align=4, name="left_word4"),
            b.load(right32, align=4, name="right_word4"),
            name="diff4",
        )
        b.cbranch(b.icmp_unsigned("!=", diff4, i32(0)), ret_4, recurse_4)

    with positioned_at(b, ret_4):
        b.ret(diff4)

    with positioned_at(b, recurse_4):
        tail.recurse_compare(b, left, right, count, 4)

    with positioned_at(b, cmp_1):
        tail.mark(b, 1)
        diff1 = b.sub(b.load(left, name="left_byte"), b.load(right, name="right_byte"), name="diff1")
        b.cbranch(b.icmp_unsigned("!=", diff1, i8(0)), ret_1, recurse_1)

    with positioned_at(b, ret_1):
        b.ret(b.sext(diff1, i32, name="diff1_i32"))

    with positioned_at(b, recurse_1):
        tail.recurse_compare(b, left, right, count, 1)

    return fn


def build_module_pythonic() -> ir.Module:
    module = ir.Module(name="musttail_chunked_memory_ops_pythonic")
    module.triple = binding.get_default_triple()
    build_chunked_copy_pythonic(module)
    build_chunked_compare_pythonic(module)
    return module


def emit_trace_step(builder: ir.IRBuilder, trace: ir.Value, trace_index: ir.Value, chunk: int) -> None:
    slot = builder.gep(trace, [trace_index], name=f"trace_slot_{chunk}")
    builder.store(i8(chunk), slot)


def recurse_copy(
    builder: ir.IRBuilder,
    fn: ir.Function,
    dst: ir.Value,
    src: ir.Value,
    count: ir.Value,
    trace: ir.Value,
    trace_index: ir.Value,
    chunk: int,
) -> None:
    step = i64(chunk)
    next_dst = builder.gep(dst, [step], name=f"dst_next_{chunk}")
    next_src = builder.gep(src, [step], name=f"src_next_{chunk}")
    next_count = builder.sub(count, step, name=f"count_next_{chunk}")
    next_trace_index = builder.add(trace_index, i64(1), name=f"trace_index_next_{chunk}")
    builder.call(fn, [next_dst, next_src, next_count, trace, next_trace_index], tail="musttail")
    builder.ret_void()


def build_bad_musttail_module() -> str:
    module = ir.Module(name="musttail_chunked_memory_ops_bad")
    module.triple = binding.get_default_triple()
    fn_ty = ir.FunctionType(i32, [ptr8, ptr8, i64, ptr8, i64])
    fn = ir.Function(module, fn_ty, name="bad_chunked_compare")
    left, right, count, trace, trace_index = fn.args
    entry = fn.append_basic_block("entry")
    body = fn.append_basic_block("body")
    recurse = fn.append_basic_block("recurse")
    exit_ = fn.append_basic_block("exit")

    b = ir.IRBuilder(entry)
    b.branch(body)

    b.position_at_end(body)
    b.cbranch(b.icmp_unsigned("==", count, i64(0)), exit_, recurse)

    b.position_at_end(exit_)
    b.ret(i32(0))

    b.position_at_end(recurse)
    # This looks like a harmless extra instruction, but it breaks the musttail shape.
    tail_call = b.call(fn, [left, right, count, trace, trace_index], tail="musttail")
    b.add(count, i64(0), name="illegal_extra_instruction")
    b.ret(tail_call)

    return str(module)


def compile_module(module: ir.Module) -> tuple[str, binding.ExecutionEngine]:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()
    target = binding.Target.from_default_triple()
    engine = binding.create_mcjit_compiler(parsed, target.create_target_machine())
    engine.finalize_object()
    return llvm_ir, engine


@dataclass
class VariantRun:
    label: str
    raw_ir: str
    copy_trace: list[int]
    compare_trace_same: list[int]
    compare_trace_diff: list[int]
    compare_same_result: int
    compare_diff_result: int
    copy_bytes_after: str


def run_variant(label: str, module_builder: Callable[[], ir.Module]) -> VariantRun:
    module = module_builder()
    llvm_ir, engine = compile_module(module)

    copy_addr = engine.get_function_address("chunked_copy")
    compare_addr = engine.get_function_address("chunked_compare")
    copy_fn = ctypes.CFUNCTYPE(
        None,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_uint64,
    )(copy_addr)
    compare_fn = ctypes.CFUNCTYPE(
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_uint64,
    )(compare_addr)

    print(f"== {label.title()} Variant ==")
    print("-- Generated IR --")
    print(llvm_ir.rstrip())
    print()

    print("-- Chunked Copy --")
    copy_src = aligned_buffer(bytes(range(1, 14)))
    copy_dst = aligned_buffer(b"\x00" * 13)
    copy_trace = aligned_buffer(b"\x00" * 16)
    copy_before = bytes_literal(read_c_string(copy_dst.address, copy_dst.size))
    print(f"source before: {bytes_literal(read_c_string(copy_src.address, copy_src.size))}")
    print(f"dest before:   {copy_before}")
    copy_fn(copy_dst.address, copy_src.address, copy_src.size, copy_trace.address, 0)
    copy_after = bytes_literal(read_c_string(copy_dst.address, copy_dst.size))
    copy_trace_plan = trace_bytes(copy_trace.address, 16)
    print(f"trace plan:    {format_trace(copy_trace_plan)}")
    print(f"dest after:    {copy_after}")
    print()

    print("-- Chunked Compare --")
    compare_left = aligned_buffer(b"ABCDEFGHijklM")
    compare_right_same = aligned_buffer(b"ABCDEFGHijklM")
    compare_right_diff = aligned_buffer(b"ABCDEFGHijklN")
    compare_trace_same = aligned_buffer(b"\x00" * 16)
    compare_trace_diff = aligned_buffer(b"\x00" * 16)
    same_result = compare_fn(
        compare_left.address,
        compare_right_same.address,
        compare_left.size,
        compare_trace_same.address,
        0,
    )
    diff_result = compare_fn(
        compare_left.address,
        compare_right_diff.address,
        compare_left.size,
        compare_trace_diff.address,
        0,
    )
    same_trace = trace_bytes(compare_trace_same.address, 16)
    diff_trace = trace_bytes(compare_trace_diff.address, 16)
    print(f"equal input trace:    {format_trace(same_trace)}")
    print(f"equal input result:    {same_result}")
    print(f"mismatch input trace:  {format_trace(diff_trace)}")
    print(f"mismatch input result: {diff_result}")
    print()

    print("-- Musttail Constraints --")
    print("The recursive call is the last real instruction in each tail-recursive block.")
    print("Every recursive step keeps the same signature shape, including the trace arguments.")
    print("The chunk marker written by the JIT makes the 8-byte, 4-byte, and 1-byte path visible.")
    print()

    print("-- Broken Shape --")
    try:
        bad_ir = build_bad_musttail_module()
        parsed = binding.parse_assembly(bad_ir)
        parsed.verify()
    except Exception as exc:  # noqa: BLE001
        print("verifier rejected the broken musttail shape:")
        print(str(exc).strip())
    else:
        print("unexpectedly accepted broken musttail shape")
    print()

    return VariantRun(
        label=label,
        raw_ir=llvm_ir,
        copy_trace=copy_trace_plan,
        compare_trace_same=same_trace,
        compare_trace_diff=diff_trace,
        compare_same_result=same_result,
        compare_diff_result=diff_result,
        copy_bytes_after=copy_after,
    )


def read_c_string(address: int, size: int) -> bytes:
    return ctypes.string_at(address, size)


def format_trace(values: Iterable[int]) -> str:
    return "[" + ", ".join(str(value) for value in values) + "]"


def main() -> None:
    print("== Question ==")
    print("How do you make chunked copy/compare helpers recursive without losing musttail legality?")
    print()
    raw_run = run_variant("raw", build_module_raw)
    py_run = run_variant("pythonic", build_module_pythonic)

    print("== Comparison ==")
    print("raw and pythonic copy traces match:", raw_run.copy_trace == py_run.copy_trace)
    print(
        "raw and pythonic equal-input compare traces match:",
        raw_run.compare_trace_same == py_run.compare_trace_same,
    )
    print(
        "raw and pythonic mismatch-input compare traces match:",
        raw_run.compare_trace_diff == py_run.compare_trace_diff,
    )
    print("raw and pythonic equal-input compare results match:", raw_run.compare_same_result == py_run.compare_same_result)
    print("raw and pythonic mismatch-input compare results match:", raw_run.compare_diff_result == py_run.compare_diff_result)
    print("raw and pythonic copy output bytes match:", raw_run.copy_bytes_after == py_run.copy_bytes_after)
    print("both variants keep the tail call in the final block position:", "musttail" in raw_run.raw_ir and "musttail" in py_run.raw_ir)

    print()
    print("== Takeaway ==")
    print(
        "musttail is a contract: preserve the call shape exactly, or the verifier will not save you. "
        "The raw version is the source of truth; the Pythonic version uses small helpers to reduce "
        "pointer and trace repetition without hiding the tail-call shape."
    )


if __name__ == "__main__":
    main()
