"""Tests for the pure Python + ctypes dictionary runtime prototype."""

from __future__ import annotations

import ctypes

from fythvm import dictionary


def test_aligned_name_region_size() -> None:
    assert dictionary.aligned_name_region_size(0) == 0
    assert dictionary.aligned_name_region_size(3) == 4
    assert dictionary.aligned_name_region_size(4) == 4
    assert dictionary.aligned_name_region_size(5) == 8


def test_dictionary_runtime_creates_words_and_traverses_newest_first() -> None:
    runtime = dictionary.DictionaryRuntime()
    alpha = runtime.create_word("alpha", handler_id=11, data=(101, 102))
    beta = runtime.create_word("beta", handler_id=22, immediate=True)
    gamma = runtime.create_word("gamma", handler_id=33, hidden=True, data=(303,))

    assert runtime.memory.latest == gamma.index
    assert runtime.memory.here == gamma.dfa_index + 1

    words = list(runtime.iter_words())
    assert [word.name_bytes for word in words] == [b"gamma", b"beta", b"alpha"]
    assert [word.link for word in words] == [beta.index, alpha.index, dictionary.NULL_INDEX]

    assert alpha.cfa_index == alpha.index + 1
    assert alpha.dfa_index == alpha.index + 2
    assert alpha.read_data_cells(2) == [101, 102]

    assert beta.immediate is True
    assert beta.hidden is False
    assert gamma.hidden is True
    assert gamma.read_data_cells(1) == [303]


def test_dictionary_lookup_skips_hidden_words_and_traces_visited_names() -> None:
    runtime = dictionary.DictionaryRuntime()
    runtime.create_word("dup", handler_id=1)
    runtime.create_word("secret", handler_id=2, hidden=True)
    visible = runtime.create_word("swap", handler_id=3)

    trace = runtime.trace_lookup("swap")
    assert trace.query == b"swap"
    assert trace.visited == [b"swap"]
    assert trace.found is not None
    assert trace.found.index == visible.index

    secret_trace = runtime.trace_lookup("secret")
    assert secret_trace.visited == [b"swap", b"secret", b"dup"]
    assert secret_trace.found is None

    missing_trace = runtime.trace_lookup("missing")
    assert missing_trace.visited == [b"swap", b"secret", b"dup"]
    assert missing_trace.found is None

    assert [word.name_bytes for word in runtime.visible_words()] == [b"swap", b"dup"]


def test_dictionary_runtime_uses_fixed_ctypes_prefix_layout() -> None:
    runtime = dictionary.DictionaryRuntime()
    word = runtime.create_word("emit", handler_id=9, data=(55,))
    prefix = word.prefix

    assert ctypes.sizeof(dictionary.CodeField) == dictionary.CELL_SIZE
    assert ctypes.sizeof(dictionary.WordPrefix) == dictionary.CELL_SIZE * 2
    assert prefix.link == dictionary.NULL_INDEX
    assert prefix.code_field.name_length == 4
    assert word.name_start_byte_offset == 0
    assert runtime.memory.read_bytes(0, 4) == b"emit"


def test_dictionary_runtime_name_region_has_no_physical_header_byte() -> None:
    runtime = dictionary.DictionaryRuntime()
    word = runtime.create_word("dup", handler_id=42, hidden=True, immediate=True)

    assert word.name_bytes == b"dup"
    assert word.aligned_name_bytes == 4
    assert runtime.memory.read_bytes(0, 4) == b"dup\x00"
    assert word.code_field.hidden == 1
    assert word.code_field.immediate == 1
    assert word.code_field.name_length == 3


def test_instruction_family_registry_defaults_and_overrides() -> None:
    registry = dictionary.InstructionFamilyRegistry(
        mapping={
            7: dictionary.COLON_THREAD_FAMILY,
            8: dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY,
        }
    )

    assert registry.family_for_handler_id(1) is dictionary.PRIMITIVE_EMPTY_FAMILY
    assert registry.family_for_handler_id(7) is dictionary.COLON_THREAD_FAMILY
    assert registry.family_for_handler_id(8) is dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY
    assert dictionary.family_for_handler_id(7, registry=registry) is dictionary.COLON_THREAD_FAMILY


def test_word_record_family_uses_registry_mapping() -> None:
    runtime = dictionary.DictionaryRuntime()
    thread_word = runtime.create_word("threaded", handler_id=7, data=(11, 22))
    literal_word = runtime.create_word("literal", handler_id=8, data=(33,))
    plain_word = runtime.create_word("dup", handler_id=1)
    registry = dictionary.InstructionFamilyRegistry(
        mapping={
            7: dictionary.COLON_THREAD_FAMILY,
            8: dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY,
        }
    )

    assert plain_word.family() is dictionary.PRIMITIVE_EMPTY_FAMILY
    assert thread_word.family(registry) is dictionary.COLON_THREAD_FAMILY
    assert literal_word.family(registry) is dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY
    assert thread_word.family(registry).has_payload is True
    assert plain_word.family(registry).has_payload is False


def test_instruction_registry_returns_category_for_primitive_empty_instruction() -> None:
    descriptor = dictionary.instruction_descriptor_for_handler_id(dictionary.PrimitiveInstruction.DUP)

    assert descriptor is not None
    assert descriptor.handler_id == int(dictionary.PrimitiveInstruction.DUP)
    assert descriptor.key == "DUP"
    assert descriptor.family is dictionary.PRIMITIVE_EMPTY_FAMILY
    assert descriptor.category is dictionary.InstructionCategory.STACK
    assert descriptor.associated_data_source is dictionary.AssociatedDataSource.NONE
    assert descriptor.requirements.min_data_stack_in == 1
    assert descriptor.requirements.min_data_stack_out_space == 2
    assert descriptor.requirements.needs_error_exit is True
    assert descriptor.requirements.kernel == "dup"


def test_instruction_registry_exposes_return_stack_requirements() -> None:
    descriptor = dictionary.instruction_descriptor_for_handler_id(dictionary.PrimitiveInstruction.EXIT)

    assert descriptor is not None
    assert descriptor.requirements.needs_return_stack is True
    assert descriptor.requirements.min_return_stack_in == 1
    assert descriptor.requirements.kernel == "exit"


def test_instruction_registry_exposes_compiler_and_input_requirements() -> None:
    create_descriptor = dictionary.instruction_descriptor_for_handler_id(dictionary.PrimitiveInstruction.CREATE)
    tick_descriptor = dictionary.instruction_descriptor_for_handler_id(dictionary.PrimitiveInstruction.TICK)

    assert create_descriptor is not None
    assert create_descriptor.requirements.needs_input_source is True
    assert create_descriptor.requirements.needs_dictionary is True
    assert create_descriptor.requirements.needs_here is True
    assert create_descriptor.requirements.kernel == "create_word"

    assert tick_descriptor is not None
    assert tick_descriptor.requirements.needs_input_source is True
    assert tick_descriptor.requirements.needs_dictionary is True
    assert tick_descriptor.requirements.min_data_stack_out_space == 1
    assert tick_descriptor.requirements.kernel == "tick"


def test_instruction_registry_exposes_lit_inline_operand_metadata() -> None:
    descriptor = dictionary.instruction_descriptor_for_handler_id(dictionary.PrimitiveInstruction.LIT)

    assert descriptor is not None
    assert descriptor.family is dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY
    assert descriptor.associated_data_source is dictionary.AssociatedDataSource.INLINE_THREAD
    assert descriptor.requirements.min_data_stack_in == 0
    assert descriptor.requirements.min_data_stack_out_space == 1
    assert descriptor.requirements.needs_ip is True
    assert descriptor.requirements.needs_error_exit is True
    assert descriptor.requirements.kernel == "inline_literal"
    assert dictionary.family_for_handler_id(int(dictionary.PrimitiveInstruction.LIT)) is dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY


def test_instruction_registry_exposes_branch_inline_operand_metadata() -> None:
    descriptor = dictionary.instruction_descriptor_for_handler_id(dictionary.PrimitiveInstruction.BRANCH)

    assert descriptor is not None
    assert descriptor.family is dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY
    assert descriptor.associated_data_source is dictionary.AssociatedDataSource.INLINE_THREAD
    assert descriptor.requirements.min_data_stack_in == 0
    assert descriptor.requirements.needs_ip is True
    assert descriptor.requirements.needs_error_exit is True
    assert descriptor.requirements.kernel == "inline_branch"
    assert dictionary.family_for_handler_id(int(dictionary.PrimitiveInstruction.BRANCH)) is dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY


def test_instruction_registry_exposes_zero_branch_inline_operand_metadata() -> None:
    descriptor = dictionary.instruction_descriptor_for_handler_id(dictionary.PrimitiveInstruction.ZBRANCH)

    assert descriptor is not None
    assert descriptor.key == "0BRANCH"
    assert descriptor.family is dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY
    assert descriptor.associated_data_source is dictionary.AssociatedDataSource.INLINE_THREAD
    assert descriptor.requirements.min_data_stack_in == 1
    assert descriptor.requirements.needs_ip is True
    assert descriptor.requirements.needs_error_exit is True
    assert descriptor.requirements.kernel == "inline_zero_branch"
    assert dictionary.family_for_handler_id(int(dictionary.PrimitiveInstruction.ZBRANCH)) is dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY


def test_instruction_registry_exposes_litstring_inline_operand_metadata() -> None:
    descriptor = dictionary.instruction_descriptor_for_handler_id(dictionary.PrimitiveInstruction.LITSTRING)

    assert descriptor is not None
    assert descriptor.family is dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY
    assert descriptor.associated_data_source is dictionary.AssociatedDataSource.INLINE_THREAD
    assert descriptor.requirements.min_data_stack_out_space == 2
    assert descriptor.requirements.needs_ip is True
    assert descriptor.requirements.needs_error_exit is True
    assert descriptor.requirements.kernel == "inline_string_literal"
    assert dictionary.family_for_handler_id(int(dictionary.PrimitiveInstruction.LITSTRING)) is dictionary.PRIMITIVE_INLINE_OPERAND_FAMILY


def test_instruction_registry_exposes_docol_word_local_thread_metadata() -> None:
    descriptor = dictionary.instruction_descriptor_for_handler_id(dictionary.PrimitiveInstruction.DOCOL)

    assert descriptor is not None
    assert descriptor.family is dictionary.COLON_THREAD_FAMILY
    assert descriptor.associated_data_source is dictionary.AssociatedDataSource.WORD_LOCAL_DFA
    assert descriptor.requirements.min_return_stack_out_space == 1
    assert descriptor.requirements.needs_current_xt is True
    assert descriptor.requirements.needs_return_stack is True
    assert descriptor.requirements.needs_error_exit is True
    assert descriptor.requirements.kernel == "enter_thread"
    assert dictionary.family_for_handler_id(int(dictionary.PrimitiveInstruction.DOCOL)) is dictionary.COLON_THREAD_FAMILY


def test_instruction_registry_leaves_unregistered_instruction_without_descriptor() -> None:
    assert dictionary.instruction_descriptor_for_handler_id(120) is None


def test_instruction_descriptor_is_separate_from_family_mapping() -> None:
    runtime = dictionary.DictionaryRuntime()
    word = runtime.create_word("dup", handler_id=int(dictionary.PrimitiveInstruction.DUP))
    family_registry = dictionary.InstructionFamilyRegistry(
        mapping={
            int(dictionary.PrimitiveInstruction.DUP): dictionary.COLON_THREAD_FAMILY,
        }
    )

    descriptor = word.instruction_descriptor()
    assert descriptor is not None
    assert descriptor.category is dictionary.InstructionCategory.STACK
    assert descriptor.family is dictionary.PRIMITIVE_EMPTY_FAMILY
    assert word.family(family_registry) is dictionary.COLON_THREAD_FAMILY
    assert word.instruction_descriptor() is descriptor


def test_dictionary_runtime_raises_when_memory_is_exhausted() -> None:
    memory = dictionary.DictionaryMemory()
    runtime = dictionary.DictionaryRuntime(memory)

    while True:
        try:
            runtime.create_word("x" * 8, data=(1, 2, 3))
        except MemoryError:
            break

    assert runtime.memory.here <= runtime.memory.capacity_cells
