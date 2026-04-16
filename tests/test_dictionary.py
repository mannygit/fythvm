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
    alpha = runtime.create_word("alpha", instruction=11, data=(101, 102))
    beta = runtime.create_word("beta", instruction=22, immediate=True)
    gamma = runtime.create_word("gamma", instruction=33, hidden=True, data=(303,))

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
    runtime.create_word("dup", instruction=1)
    runtime.create_word("secret", instruction=2, hidden=True)
    visible = runtime.create_word("swap", instruction=3)

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
    word = runtime.create_word("emit", instruction=9, compiling=True, data=(55,))
    prefix = word.prefix

    assert ctypes.sizeof(dictionary.CodeField) == dictionary.CELL_SIZE
    assert ctypes.sizeof(dictionary.WordPrefix) == dictionary.CELL_SIZE * 2
    assert prefix.link == dictionary.NULL_INDEX
    assert prefix.code.name_length == 4
    assert prefix.code.compiling == 1
    assert word.name_start_byte_offset == 0
    assert runtime.memory.read_bytes(0, 4) == b"emit"


def test_dictionary_runtime_name_region_has_no_physical_header_byte() -> None:
    runtime = dictionary.DictionaryRuntime()
    word = runtime.create_word("dup", instruction=42, hidden=True, immediate=True, compiling=True)

    assert word.name_bytes == b"dup"
    assert word.aligned_name_bytes == 4
    assert runtime.memory.read_bytes(0, 4) == b"dup\x00"
    assert word.code.hidden == 1
    assert word.code.immediate == 1
    assert word.code.name_length == 3


def test_dictionary_runtime_raises_when_memory_is_exhausted() -> None:
    memory = dictionary.DictionaryMemory()
    runtime = dictionary.DictionaryRuntime(memory)

    while True:
        try:
            runtime.create_word("x" * 8, data=(1, 2, 3))
        except MemoryError:
            break

    assert runtime.memory.here <= runtime.memory.capacity_cells
