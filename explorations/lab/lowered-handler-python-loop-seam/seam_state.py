from __future__ import annotations

import ctypes

from fythvm.codegen import BoundStructView, StructField, StructHandle


STATE_HALT_REQUESTED = 0x01
STACK_CAPACITY = 8


class LoweredLoopState(ctypes.Structure):
    _fields_ = [
        ("state_flags", ctypes.c_int32),
        ("ip", ctypes.c_int32),
        ("current_xt", ctypes.c_int32),
        ("stack_depth", ctypes.c_int32),
        ("data_stack", ctypes.c_int32 * STACK_CAPACITY),
    ]


class LoweredLoopStateView(BoundStructView):
    state_flags = StructField(0)
    ip = StructField(1)
    current_xt = StructField(2)
    stack_depth = StructField(3)
    data_stack = StructField(4)


STATE_HANDLE = StructHandle.from_ctypes(
    "lowered loop state",
    LoweredLoopState,
    view_type=LoweredLoopStateView,
)
