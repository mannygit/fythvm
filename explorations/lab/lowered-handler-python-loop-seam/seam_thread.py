from __future__ import annotations

import ctypes


def materialize_thread_buffer(thread: tuple[int, ...]) -> ctypes.Array[ctypes.c_int32]:
    return (ctypes.c_int32 * len(thread))(*thread)
