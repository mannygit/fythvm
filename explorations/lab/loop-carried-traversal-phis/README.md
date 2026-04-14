# Loop Carried Traversal Phis

## Question

How do you carry a traversal cursor and a derived count through a linked-list loop
without confusing the two?

## Setup

This lab builds a tiny recursive `Node` struct in llvmlite and emits two functions:

- `count_nodes`, which walks a list with a loop-carried cursor phi and a loop-carried
  count phi
- `index_of_value`, which uses the same traversal shape but exits early with a result
  phi when the current node value matches the target

The example is intentionally small and explicit. It is the linked-list traversal shape
that showed up in `~/fyth` when the code learned to keep cursor state and derived state
separate.

## How to Run

```bash
uv run python explorations/lab/loop-carried-traversal-phis/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/loop-carried-traversal-phis/run.py
```

## What It Shows

The output prints:

- the linked list shape built in Python
- the generated IR for both traversal functions
- a short phi summary that highlights the loop header cursor and count values
- runtime results for:
  - counting the whole list
  - finding the first element
  - finding a middle element
  - searching for a missing value
- a verifier failure for a malformed loop that omits the backedge incoming count

The key result is that the cursor phi and the count phi are different pieces of state.
The cursor moves through the linked structure; the count tracks how many nodes have
already been seen. The early-exit path then returns the derived count as the answer.

## Pattern / Takeaway

Use one phi for the traversal cursor and a separate phi for derived loop state.
Treat the cursor as the thing that decides where the next iteration goes, and treat
the count or accumulator as the thing that records what the loop has learned so far.

For search-style loops, return the derived result through a separate exit phi rather
than trying to smuggle it through the cursor variable.

## Non-Obvious Failure Modes

The first mistake is to think the cursor and the accumulator are interchangeable.
They are not. A node pointer tells you where to load next; a count tells you how many
nodes you have already processed.

The second mistake is to add phi incoming values to the wrong predecessor. In a loop,
the header phi must receive the initial value from the entry block and the updated
value from the actual backedge block. If you pair the value with the wrong block, or
omit the backedge incoming entirely, the verifier rejects the module.

The third mistake is to return the traversal cursor when you really want the derived
state. A successful search can return the count or index, but that is a separate value
from the cursor that got you there.

## Apply When

Use this pattern when:

- traversing linked lists, trees, or other pointer-chained structures
- carrying both a cursor and a derived state through a loop
- lowering `count`, `nth`, or `find` style operations into SSA form
- you want an early-exit search that still preserves the loop-carried count

## Avoid When

Do not use this pattern when the data is already available in straight-line form.
If the logic is just a simple branch between precomputed values, `select` or a normal
`if` may be cleaner.

Do not collapse the traversal cursor into the accumulator unless the traversal state
is genuinely one and the same. That makes the IR harder to read and usually hides the
real dataflow.

## Next Questions

- How does the same traversal shape look when the loop carries a pointer plus a more
  complex derived payload than a simple count?
- When is it better to return a struct of traversal results instead of an index or
  sentinel?
- What helper patterns make loop-heavy llvmlite IR easier to generate without hiding
  the actual backedges?
