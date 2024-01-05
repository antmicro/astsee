# `astsee`

Copyright (c) 2023-2024 [Antmicro](https://www.antmicro.com)

A suite of tools for pretty printing, diffing, and exploring abstract syntax
trees. You can use the generic `astsee` tool that accepts mostly arbitrary
tree-like structures in JSON format, or a variant for a specific AST type.
Currently, only [Verilator](https://github.com/verilator/verilator) JSON trees
are supported via `astsee_verilator`.

## Usage

Given two JSON files, `a.json`:

<!-- name="a.json" -->
```json
{
  "type": "TEST", "addr": "0x55b700efa000", "editNum": 1, "file": "<built-in>:0:0", "name": "$root",
  "op1": [
    {
      "type": "MODULE", "addr": "0x55b700f366c0", "editNum": 2361, "file": "test.v:16:8", "name": "__024root",
      "op2": [
        { "type": "CELL", "addr": "0x55b700f50280", "editNum": 2364, "file": "test.v:16:8", "name": "t" }
      ]
    }
  ], "op4": [
      { "type": "CELL", "addr": "0x55b700f50280", "editNum": 2364, "file": "test.v:16:8", "name": "t" },
      { "type": "CELL", "addr": "0x55b700f50280", "editNum": 2364, "file": "test.v:16:8", "name": "t" },
      { "type": "CELL", "addr": "0x55b700f50280", "editNum": 2364, "file": "test.v:16:8", "name": "t" },
      { "type": "CELL", "addr": "0x55b700f50280", "editNum": 2364, "file": "test.v:16:8", "name": "t" }
  ]
}
```

and `b.json`:

<!-- name="b.json" -->
```json
{
  "type": "TEST", "addr": "0x55b700efa000", "editNum": 1, "file": "<built-in>:0:0", "name": "$root",
  "op1": [
    {
      "type": "EXTMODULE", "addr": "0x55b700f36620", "editNum": 2362, "file": "test.v:16:8", "name": "__024root",
      "op3": [
        { "type": "CELL", "addr": "0x55b700f50280", "editNum": 2364, "file": "test.v:16:8", "name": "t" }
      ]
    }
  ], "op4": [
      { "type": "CELL", "addr": "0x55b700f50280", "editNum": 2364, "file": "test.v:16:8", "name": "t" },
      { "type": "CELL", "addr": "0x55b700f50280", "editNum": 2364, "file": "test.v:16:8", "name": "t" },
      { "type": "CELL", "addr": "0x55b700f50280", "editNum": 2364, "file": "test.v:16:8", "name": "t" },
      { "type": "CELL", "addr": "0x55b700f50280", "editNum": 2364, "file": "test.v:16:8", "name": "t" }
  ]
}
```

Run:

<!-- name="pretty-print" -->
```sh
astsee a.json
```

to pretty print it in a concise format:

<!-- name="pretty-print-output" -->
```
addr:0x55b700efa000, editNum:1, file:<built-in>:0:0, name:$root, type:TEST
 op1:
   addr:0x55b700f366c0, editNum:2361, file:test.v:16:8, name:__024root, type:MODULE
    op2:
      addr:0x55b700f50280, editNum:2364, file:test.v:16:8, name:t, type:CELL
 op4:
   addr:0x55b700f50280, editNum:2364, file:test.v:16:8, name:t, type:CELL
   addr:0x55b700f50280, editNum:2364, file:test.v:16:8, name:t, type:CELL
   addr:0x55b700f50280, editNum:2364, file:test.v:16:8, name:t, type:CELL
   addr:0x55b700f50280, editNum:2364, file:test.v:16:8, name:t, type:CELL
```

To produce a diff:

<!-- name="produce-diff" -->
```sh
astsee a.json b.json
```

![astsee a.json b.json](img/generic_diff_ab.png)

To see all available options:

```sh
astsee --help
```

## Installation and usage

To install, run:

```sh
pipx install git+https://github.com/antmicro/astsee
```

Or clone the repository, `cd` to it, and run:

<!-- name="install" -->
```sh
pipx install .
```

## Dev install

To install project in editable mode (so changes are immediately reflected in executable), with extra dependencies meant for development only (like test framework):

clone repo, `cd` to it, and run:
```sh
pip install -e '.[dev]'
```

## Tests

To run tests, invoke:

<!-- name="test" -->
```sh
pytest
```

in project root. To update tests:

```sh
pytest --golden
```

## Known limitations/bugs

- Arrays of scalars or arrays of array work only in `--basic` mode
- Diff doesn't support direct replacement of root node
- `astsee_verilator --html` tests are unstable due to usage of Python's `set`
