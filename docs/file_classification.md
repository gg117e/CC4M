# File Classification

This document describes the file-category classifier (`file_type`) used by
CC4M and how clone pairs are classified based on those categories.

The implementation lives in [src/modules/util.py](../src/modules/util.py)
(`get_file_type`) and
[src/visualize/callbacks/filter_callbacks.py](../src/visualize/callbacks/filter_callbacks.py)
(`_classify_clone_sets`).

---

## File Categories

Every fragment is tagged with one of four categories.

| Category | Meaning |
|----------|---------|
| `test` | Test code |
| `data` | Schemas, migrations, DTOs, etc. |
| `config` | Configuration files |
| `logic` | Everything else (application logic) |

Classification is based on **path and extension only** — file contents are
never read.

### Priority

Rules are evaluated in this order; the first match wins.

| Order | Category | Condition |
|-------|----------|-----------|
| 1 | `test` | Path contains any test indicator |
| 2 | `config` | File name matches a known config-file name |
| 3 | `config` | Extension is in the config set |
| 4 | `config` | Path contains a config directory |
| 5 | `data` | Path contains a data indicator |
| 6 | `data` | Extension is in the data set |
| 7 | `logic` | None of the above |

### Lookup tables

**Test indicators** (path substring)
`/test/`, `/tests/`, `/test_`, `test_`, `_test.`, `.test.`,
`/spec/`, `/specs/`, `_spec.`, `.spec.`, `/__tests__/`

**Config file names** (exact match)
`dockerfile`, `docker-compose.yml`, `docker-compose.yaml`, `makefile`, `.env`,
`tsconfig.json`, `package.json`, `setup.py`, `setup.cfg`, `pyproject.toml`,
`pom.xml`, `build.gradle`, `build.sbt`, `cargo.toml`, `go.mod`,
`.eslintrc`, `.prettierrc`, `.babelrc`,
`jest.config.js`, `webpack.config.js`, `rollup.config.js`, `vite.config.ts`,
`nginx.conf`, `requirements.txt`, `gemfile`

**Config extensions**
`.yml`, `.yaml`, `.toml`, `.ini`, `.cfg`, `.conf`

**Config directories** (path substring)
`/config/`, `/configs/`, `/.github/`, `/.circleci/`

**Data indicators** (path substring)
`/entity/`, `/entities/`, `/dto/`, `/proto/`,
`/migration/`, `/migrations/`, `/seed/`, `/seeds/`,
`/fixture/`, `/fixtures/`

**Data extensions**
`.sql`, `.graphql`, `.proto`, `.avsc`

---

## Clone-Pair Classification

Clone sets are classified by the set of `file_type` values appearing across
their fragments
(see `_classify_clone_sets` in
[filter_callbacks.py](../src/visualize/callbacks/filter_callbacks.py)).

| Clone-set category | Condition |
|--------------------|-----------|
| `test` | All fragments are `test` |
| `data` | All fragments are `data` |
| `config` | All fragments are `config` |
| `logic` | No `test` fragment, and types are a subset of `{logic, data, config}` (i.e. pure logic, or a mix of non-test categories) |
| `mixed` | At least one `test` fragment **and** at least one non-`test` fragment |

In short, `mixed` flags clone pairs that span the test / non-test boundary.
This is the category used by the visualization's *Mixed* filter.
