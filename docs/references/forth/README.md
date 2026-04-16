# Forth References

Reference captures pulled from `Forth_Links.txt`.

## Captured Sources

- [JonesForth](./jonesforth/README.md)
  Source files:
  - `Jonesforth.S.txt`
  - `Jonesforth.f.txt`
  Includes:
  - implementation report with line-referenced explanation of the assembly kernel and
    self-hosted Forth layer
  - primitive inventory with line-referenced `defcode` word list and `fythvm` family
    reading
- [Moving Forth: Part 1](./moving1.md)
  Source: <https://www.bradrodriguez.com/papers/moving1.htm>
- [Moving Forth: Part 2](./moving2.md)
  Source: <https://www.bradrodriguez.com/papers/moving2.htm>
- [Moving Forth: Part 3](./moving3.md)
  Source: <https://www.bradrodriguez.com/papers/moving3.htm>
- [Moving Forth: Part 4](./moving4.md)
  Source: <https://www.bradrodriguez.com/papers/moving4.htm>
  Includes:
  - [implementation report](./moving-forth-implementation-report.md)
- [Fitting a Forth in 512 bytes](./miniforth.md)
  Source: <https://compilercrim.es/bootstrap/miniforth/>

## Synthesis Reports

- [JonesForth vs Moving Forth Alignment Report](./forth-implementation-alignment-report.md)
  Includes:
  - shared implementation invariants
  - concrete deviations
  - decision guidance for `fythvm`
- [Primitive Family Synthesis](./primitive-family-synthesis.md)
  Includes:
  - synthesis of JonesForth's concrete primitive inventory with Moving Forth's
    code-field / parameter-field theory
  - recommended first family set for `fythvm`

## Notes

- These are readable markdown captures, not fidelity-preserving archival snapshots.
- Diagram/image-heavy content was preserved as text where possible, not as embedded
  graphics.
- Some footer/navigation text from the original pages may remain where it was part of
  the source HTML flow.
