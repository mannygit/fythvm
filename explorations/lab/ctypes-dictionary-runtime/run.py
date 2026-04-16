"""Demonstrate the integrated pure Python + ctypes dictionary runtime."""

from __future__ import annotations

import inspect

from fythvm import dictionary


def render_lookup(runtime: dictionary.DictionaryRuntime, query: str) -> str:
    trace = runtime.trace_lookup(query)
    walked = " -> ".join(name.decode("ascii") for name in trace.visited) or "(empty)"
    if trace.found is None:
        return f"{query!r}: walked {walked} | not found"
    return (
        f"{query!r}: walked {walked} | found {trace.found.name_bytes.decode('ascii')!r} "
        f"at word={trace.found.index} cfa={trace.found.cfa_index} dfa={trace.found.dfa_index}"
    )


def main() -> None:
    runtime = dictionary.DictionaryRuntime()
    runtime.create_word("dup", handler_id=1, data=(10,))
    runtime.create_word("swap", handler_id=2, immediate=True, data=(20, 21))
    runtime.create_word("secret", handler_id=3, hidden=True, data=(30,))
    runtime.create_word("emit", handler_id=4, compiling=True, data=(40, 41, 42))

    print("== Question ==")
    print("What does a pure Python + ctypes dictionary runtime look like once the fixed records and variable word-entry protocol are combined?")
    print()

    print("== Real Python Types ==")
    for obj in (
        dictionary.Registers,
        dictionary.CodeField,
        dictionary.WordPrefix,
        dictionary.DictionaryMemory,
        dictionary.DictionaryRuntime,
    ):
        print(inspect.getsource(obj).rstrip())
        print()

    print("== Runtime State ==")
    print(f"here={runtime.memory.here} latest={runtime.memory.latest}")
    print(f"capacity_cells={runtime.memory.capacity_cells}")
    print()

    print("== Word Traversal ==")
    for word in runtime.iter_words():
        print(runtime.render_word(word))
    print()

    print("== Visible Lookup ==")
    for query in ["emit", "secret", "swap", "missing"]:
        print(render_lookup(runtime, query))
    print()

    print("== Debug Snapshot ==")
    for line in runtime.debug_lines():
        print(line)
    print()

    print("== Takeaway ==")
    print("A pure Python + ctypes dictionary is good enough to debug the real layout, offsets, and lookup rules before there is any word-execution machinery on top.")


if __name__ == "__main__":
    main()
