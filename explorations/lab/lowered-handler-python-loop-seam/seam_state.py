from __future__ import annotations

import ctypes

from fythvm import dictionary
from fythvm.codegen import BoundStructView, StructHandle


STATE_HALT_REQUESTED = 0x01
STACK_CAPACITY = 8
RETURN_STACK_CAPACITY = 8


class LoweredLoopState(ctypes.Structure):
    _fields_ = [
        ("halt_requested", ctypes.c_uint32, 1),
        ("exact_ip_requested", ctypes.c_uint32, 1),
        ("_reserved_flags", ctypes.c_uint32, 30),
        ("dictionary_memory", ctypes.POINTER(dictionary.DictionaryMemory)),
        ("ip", ctypes.c_int32),
        ("current_xt", ctypes.c_int32),
        ("thread_cells", ctypes.POINTER(ctypes.c_int32)),
        ("thread_length", ctypes.c_int32),
        ("current_word_thread_length", ctypes.c_int32),
        ("stack", ctypes.c_int32 * STACK_CAPACITY),
        ("sp", ctypes.c_int32),
        ("return_thread_cells", ctypes.POINTER(ctypes.c_int32) * RETURN_STACK_CAPACITY),
        ("return_thread_length", ctypes.c_int32 * RETURN_STACK_CAPACITY),
        ("return_ip", ctypes.c_int32 * RETURN_STACK_CAPACITY),
        ("rsp", ctypes.c_int32),
    ]

STATE_HANDLE = StructHandle.from_ctypes(
    "lowered loop state",
    LoweredLoopState,
)

LoweredLoopStateView = STATE_HANDLE.view_type
assert issubclass(LoweredLoopStateView, BoundStructView)


def state_flags_value(state: LoweredLoopState) -> int:
    return STATE_HALT_REQUESTED if int(state.halt_requested) else 0
