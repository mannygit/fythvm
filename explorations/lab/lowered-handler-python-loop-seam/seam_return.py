from __future__ import annotations

from seam_state import RETURN_STACK_CAPACITY


def return_stack_depth(state) -> int:
    return RETURN_STACK_CAPACITY - int(state.rsp)
