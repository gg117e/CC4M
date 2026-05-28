# Declaration-Line Filtering

This document describes the preprocessing step that decides which declaration
lines participate in clone analysis. The description is taken directly from the
implementation in `src/modules/source_filter.py`.

## Purpose

`import` / `package` / `require` / `include` / `use` declaration lines look
almost identical across files in a project. If left in place they produce many
spurious clone matches. Before running CCFinderSW, the `collect` step comments
out these declaration lines so they are not tokenized as clones.

The transformation **comments lines out instead of deleting them**, so every
line keeps its original line number. This is essential because the rest of the
pipeline (diffs, fragment ranges, metrics) refers to source lines by number.

The filter is applied by `apply_filter(project_dir, languages, exts)`, which
walks every file of each target language (`project_dir.rglob("*<ext>")`) and
calls `filter_imports(file_path, language)`. It is toggled by the `collect`
step's `apply_import_filter` flag (default `True`); the choice is recorded in
the visualization CSV filename as `filtered` vs `nofilter`.

## Comment Style

`# ` for Python and Ruby; `// ` for every other supported language
(C, C++, C#, Go, Java, JavaScript, Kotlin, PHP, Rust, Scala, Swift, TypeScript).

## Per-Language Rules

A line is treated as a declaration line (and commented out) when, after
stripping leading whitespace, it matches the rules for its language:

| Language | Lines commented out |
|---|---|
| Python | `import ...`; `from ... import ...`. A parenthesized `from ... import (` block is followed until its parentheses balance. |
| Go | `package ...`; `import ...`; an `import (` block is followed until the closing `)`. |
| Java / Kotlin / Scala | `package ...`; `import ...`. |
| JavaScript / TypeScript | `import ...`; `export ... from ...`; CommonJS requires: `const`/`let`/`var ... = require(...)` and bare `require(...)`. A require statement without a terminating `;` is followed until a line ends with `;`. |
| C / C++ | `#include ...` (and `import ...`). |
| Rust | `use ...` (and `import ...`). |
| PHP | `use ...`; `require ...`; `include ...` (and `import ...`). |
| Ruby | `require ...`; `load ...`. |
| Other slash-comment languages | `import ...`. |

Multi-line constructs are tracked with explicit state so that continuation lines
are also commented out:

- Go `import ( ... )` block - until the line starting with `)`.
- Python `from ... import ( ... )` - by parenthesis balance.
- JS/TS multi-line `require(...)` - until a line ending in `;`.

## Robustness

`filter_imports` reads with `errors="ignore"` and silently returns on read
failure, so a single unreadable file does not stop the run. Files are rewritten
in place under the cloned working copy in `dest/`, never under the user's repo.
