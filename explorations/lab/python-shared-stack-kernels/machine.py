"""Pure Python substrate for the shared-stack-kernel lab."""

from __future__ import annotations

from dataclasses import dataclass, field


MASK32 = 0xFFFFFFFF
SIGN_BIT32 = 0x80000000
CELL_BYTES = 4
DEFAULT_STACK_SIZE = 8
DEFAULT_MEMORY_SIZE = 64


class MachineError(RuntimeError):
    """Base class for lab-local machine failures."""


class StackUnderflow(MachineError):
    """Raised when an operation needs more stack items than are available."""


class StackOverflow(MachineError):
    """Raised when an operation pushes past the stack capacity."""


class MemoryBoundsError(MachineError):
    """Raised when an operation addresses memory outside the bytearray."""


def to_u32(value: int) -> int:
    """Normalize a Python int into one unsigned 32-bit cell."""

    return value & MASK32


def to_cell(value: int) -> int:
    """Normalize a Python int into one signed-looking 32-bit Forth cell."""

    value = to_u32(value)
    return value if value < SIGN_BIT32 else value - (MASK32 + 1)


def bool_cell(flag: bool) -> int:
    """Return JonesForth-style boolean cells."""

    return 1 if flag else 0


def trunc_divmod(dividend: int, divisor: int) -> tuple[int, int]:
    """Match x86/JonesForth signed division semantics."""

    if divisor == 0:
        raise ZeroDivisionError("division by zero")
    quotient = abs(dividend) // abs(divisor)
    if (dividend < 0) ^ (divisor < 0):
        quotient = -quotient
    remainder = dividend - quotient * divisor
    return to_cell(remainder), to_cell(quotient)


@dataclass(frozen=True)
class MachineSnapshot:
    """Stable representation of the whole lab-visible machine state."""

    dsp: int
    rsp: int
    data_stack: tuple[int, ...]
    return_stack: tuple[int, ...]
    memory: bytes


@dataclass
class MachineState:
    """Downward-growing data/return stacks over pure Python storage."""

    stack_size: int = DEFAULT_STACK_SIZE
    memory_size: int = DEFAULT_MEMORY_SIZE
    data_stack: list[int] = field(init=False)
    return_stack: list[int] = field(init=False)
    dsp: int = field(init=False)
    rsp: int = field(init=False)
    memory: bytearray = field(init=False)

    def __post_init__(self) -> None:
        self.data_stack = [0] * self.stack_size
        self.return_stack = [0] * self.stack_size
        self.dsp = self.stack_size
        self.rsp = self.stack_size
        self.memory = bytearray(self.memory_size)

    def clone(self) -> MachineState:
        """Return a deep copy suitable for parity runs."""

        other = MachineState(stack_size=self.stack_size, memory_size=self.memory_size)
        other.data_stack[:] = self.data_stack
        other.return_stack[:] = self.return_stack
        other.dsp = self.dsp
        other.rsp = self.rsp
        other.memory[:] = self.memory
        return other

    def snapshot(self) -> MachineSnapshot:
        """Capture raw arrays, pointers, and memory bytes."""

        return MachineSnapshot(
            dsp=self.dsp,
            rsp=self.rsp,
            data_stack=tuple(self.data_stack),
            return_stack=tuple(self.return_stack),
            memory=bytes(self.memory),
        )

    def seed_data(self, *values: int) -> MachineState:
        """Push values so the last value becomes the top of stack."""

        for value in values:
            self.push_data(value)
        return self

    def seed_return(self, *values: int) -> MachineState:
        """Push values so the last value becomes the top of return stack."""

        for value in values:
            self.push_return(value)
        return self

    def logical_data_stack(self) -> list[int]:
        """Render data stack in Forth order from deeper item to top."""

        return list(reversed(self.data_stack[self.dsp : self.stack_size]))

    def logical_return_stack(self) -> list[int]:
        """Render return stack in Forth order from deeper item to top."""

        return list(reversed(self.return_stack[self.rsp : self.stack_size]))

    def memory_slice(self, start: int, length: int) -> bytes:
        """Return one visible slice of memory."""

        self._check_memory(start, length)
        return bytes(self.memory[start : start + length])

    def push_data(self, value: int) -> None:
        """Push one cell onto the downward-growing data stack."""

        if self.dsp == 0:
            raise StackOverflow("data stack overflow")
        self.dsp -= 1
        self.data_stack[self.dsp] = to_cell(value)

    def pop_data(self) -> int:
        """Pop one cell from the data stack."""

        if self.dsp == self.stack_size:
            raise StackUnderflow("data stack underflow")
        value = self.data_stack[self.dsp]
        self.dsp += 1
        return value

    def peek_data(self, depth: int = 0) -> int:
        """Read one cell from the data stack without consuming it."""

        index = self.dsp + depth
        if index >= self.stack_size:
            raise StackUnderflow("data stack underflow")
        return self.data_stack[index]

    def data_window(self, width: int) -> list[int]:
        """Return the top stack window in Forth order from deeper item to top."""

        if self.dsp + width > self.stack_size:
            raise StackUnderflow("data stack underflow")
        return list(reversed(self.data_stack[self.dsp : self.dsp + width]))

    def replace_data_window(self, width: int, values: list[int]) -> None:
        """Overwrite the top stack window using Forth-order values."""

        if len(values) != width:
            raise ValueError("replacement width mismatch")
        if self.dsp + width > self.stack_size:
            raise StackUnderflow("data stack underflow")
        self.data_stack[self.dsp : self.dsp + width] = [
            to_cell(v) for v in reversed(values)
        ]

    def set_dsp(self, pointer: int) -> None:
        """Install a new data-stack pointer."""

        if not 0 <= pointer <= self.stack_size:
            raise StackOverflow(f"invalid data-stack pointer {pointer}")
        self.dsp = pointer

    def push_return(self, value: int) -> None:
        """Push one cell onto the downward-growing return stack."""

        if self.rsp == 0:
            raise StackOverflow("return stack overflow")
        self.rsp -= 1
        self.return_stack[self.rsp] = to_cell(value)

    def pop_return(self) -> int:
        """Pop one cell from the return stack."""

        if self.rsp == self.stack_size:
            raise StackUnderflow("return stack underflow")
        value = self.return_stack[self.rsp]
        self.rsp += 1
        return value

    def peek_return(self, depth: int = 0) -> int:
        """Read one cell from the return stack without consuming it."""

        index = self.rsp + depth
        if index >= self.stack_size:
            raise StackUnderflow("return stack underflow")
        return self.return_stack[index]

    def set_rsp(self, pointer: int) -> None:
        """Install a new return-stack pointer."""

        if not 0 <= pointer <= self.stack_size:
            raise StackOverflow(f"invalid return-stack pointer {pointer}")
        self.rsp = pointer

    def read_cell(self, address: int) -> int:
        """Read one little-endian cell from memory."""

        self._check_memory(address, CELL_BYTES)
        raw = int.from_bytes(
            self.memory[address : address + CELL_BYTES], "little", signed=False
        )
        return to_cell(raw)

    def write_cell(self, address: int, value: int) -> None:
        """Write one little-endian cell into memory."""

        self._check_memory(address, CELL_BYTES)
        self.memory[address : address + CELL_BYTES] = to_u32(value).to_bytes(
            CELL_BYTES, "little"
        )

    def read_byte(self, address: int) -> int:
        """Read one zero-extended byte from memory."""

        self._check_memory(address, 1)
        return self.memory[address]

    def write_byte(self, address: int, value: int) -> None:
        """Write the low byte of one cell into memory."""

        self._check_memory(address, 1)
        self.memory[address] = to_u32(value) & 0xFF

    def copy_byte(self, src: int, dst: int) -> None:
        """Copy one byte through memory."""

        value = self.read_byte(src)
        self.write_byte(dst, value)

    def copy_bytes(self, src: int, dst: int, length: int) -> None:
        """Copy one block of bytes through memory."""

        self._check_memory(src, length)
        self._check_memory(dst, length)
        self.memory[dst : dst + length] = self.memory[src : src + length]

    def describe(self) -> str:
        """Render the machine state for the demo output."""

        return (
            f"dsp={self.dsp} rsp={self.rsp} "
            f"data={self.logical_data_stack()} "
            f"return={self.logical_return_stack()}"
        )

    def _check_memory(self, address: int, length: int) -> None:
        if address < 0 or length < 0 or address + length > self.memory_size:
            raise MemoryBoundsError(
                f"invalid memory range [{address}, {address + length})"
            )


__all__ = [
    "CELL_BYTES",
    "DEFAULT_MEMORY_SIZE",
    "DEFAULT_STACK_SIZE",
    "MASK32",
    "MachineError",
    "MachineSnapshot",
    "MachineState",
    "MemoryBoundsError",
    "StackOverflow",
    "StackUnderflow",
    "bool_cell",
    "to_cell",
    "to_u32",
    "trunc_divmod",
]
