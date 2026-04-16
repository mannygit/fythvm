"""Local schema used by the generated-layout-wrapper-convention lab."""

from __future__ import annotations

import ctypes


class CodeField(ctypes.Structure):
    __ir_name__ = "LabCodeField"
    __ir_label__ = "lab code field"

    _fields_ = [
        ("handler_id", ctypes.c_uint16, 7),
        ("hidden", ctypes.c_uint16, 1),
        ("immediate", ctypes.c_uint16, 1),
        ("name_length", ctypes.c_uint16, 5),
        ("unused", ctypes.c_uint16, 2),
    ]
