# JonesForth Reference

This folder preserves two local JonesForth source files as reference material and adds
an implementation report describing how this particular Forth works.

## Sources

- [Jonesforth.S.txt](./Jonesforth.S.txt)
  - The literate i386/Linux assembly source.
  - Covers the threading model, dictionary layout, built-in primitives, interpreter,
    compiler bootstrap, Linux syscall bridge, and early runtime setup.
- [Jonesforth.f.txt](./Jonesforth.f.txt)
  - The self-hosted Forth layer loaded after the assembly kernel is running.
  - Builds the higher-level compiler words, control structures, strings, variables and
    values, exceptions, decompiler, and a small assembler extension on top of the core.

## Companion Report

- [implementation-report.md](./implementation-report.md)
  - A structured explanation of how JonesForth is implemented and what is likely most
    relevant to `fythvm`.
- [primitive-inventory.md](./primitive-inventory.md)
  - Inventory of the assembly-defined `defcode` primitive words.
  - Includes:
    - full word list with source line numbers
    - a reduced `fythvm`-relevant slice
    - a family-oriented reading of what the primitive set suggests

## Why It Matters Here

JonesForth is useful reference material for this repo because it is:

- extremely explicit about the threaded execution model
- honest about the dictionary memory layout
- bootstrapped in the same spirit as the `~/fyth` code we have been mining
- written as a literate implementation, making it good architectural reference rather
  than just code to skim

## Notes

- These are preserved local copies of the original source files, not re-rendered
  markdown conversions.
- The implementation report references these exact local copies by line number, so the
  report and the source snapshots stay aligned.
