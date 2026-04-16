"""Small byte-region helpers for llvmlite code generation."""

from __future__ import annotations

from llvmlite import ir

from .loops import ParamLoop


def compare_aligned_i32_regions(
    builder: ir.IRBuilder,
    left_ptr: ir.Value,
    right_ptr: ir.Value,
    byte_length: ir.Value,
    *,
    name: str = "regions_equal",
) -> ir.Value:
    """Compare two 4-byte-aligned, 4-byte-sized byte regions word at a time.

    This is the small primitive we will need for IR-side dictionary search: the
    caller is responsible for ensuring both pointers are aligned and that
    ``byte_length`` is a multiple of 4 bytes, typically by comparing padded name
    regions rather than raw unaligned names.
    """

    if not isinstance(byte_length.type, ir.IntType):
        raise TypeError(f"byte_length must be an integer IR value, got {byte_length.type!r}")

    index_type = byte_length.type
    i32_ptr = ir.IntType(32).as_pointer()
    left_words = builder.bitcast(left_ptr, i32_ptr, name=f"{name}_left_words")
    right_words = builder.bitcast(right_ptr, i32_ptr, name=f"{name}_right_words")
    word_count = builder.lshr(byte_length, index_type(2), name=f"{name}_word_count")

    loop = ParamLoop(builder, name, [("i", index_type)])
    mismatch_block = builder.append_basic_block(f"{name}.mismatch")
    equal_block = builder.append_basic_block(f"{name}.equal")
    loop.begin(index_type(0))

    with loop.head() as (i,):
        active = builder.icmp_unsigned("<", i, word_count, name=f"{name}_active")
        builder.cbranch(active, loop.body_block, equal_block)

    with loop.body():
        left_word_ptr = builder.gep(left_words, [i], inbounds=True, name=f"{name}_left_word_ptr")
        right_word_ptr = builder.gep(right_words, [i], inbounds=True, name=f"{name}_right_word_ptr")
        left_word = builder.load(left_word_ptr, name=f"{name}_left_word")
        right_word = builder.load(right_word_ptr, name=f"{name}_right_word")
        same_word = builder.icmp_unsigned("==", left_word, right_word, name=f"{name}_same_word")
        next_i = builder.add(i, index_type(1), name=f"{name}_next_i")
        builder.cbranch(same_word, loop.head_block, mismatch_block)
        loop._join.add_incoming(builder.basic_block, next_i)

    with builder.goto_block(mismatch_block):
        builder.branch(loop.exit_block)

    with builder.goto_block(equal_block):
        builder.branch(loop.exit_block)

    with loop.exit():
        result = builder.phi(ir.IntType(1), name=name)
        result.add_incoming(ir.IntType(1)(0), mismatch_block)
        result.add_incoming(ir.IntType(1)(1), equal_block)
        return result
