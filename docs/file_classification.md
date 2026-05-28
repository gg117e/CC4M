# File Classification and Service Mapping

This document describes how CC4M interprets a fragment's file path: repo-relative
normalization, service-boundary resolution, and the file-category classifier
used as `file_type`. The descriptions are taken directly from
`src/modules/util.py` and `src/modules/visualization/service_mapping.py`.

## Repo-Relative Paths

Inside `FileMapper` (`src/modules/util.py`) each CCFinderSW `file_path` is made
repo-relative by stripping the `project_dir + "/"` prefix. All downstream paths
(`enriched_fragments.csv`, scatter CSV, metrics) use this repo-relative form.

## Service-Boundary Resolution

`service_mapping.py` resolves the owning microservice of a file path:

- `normalize_repo_relative_path(path)` normalizes a path to a `/`-separated
  repo-relative string.
- Service contexts come from CLAIM (`load_claim_service_contexts_for_repo`,
  reading `dest/ms_detection/<repo>.csv`) or from a cached
  `dest/services_json/<repo>.json` (`load_service_contexts_from_json`). Each is a
  `ServiceContext(service_name, context, source)` where `context` is the
  repo-relative directory that defines the service boundary.
- `resolve_service_for_file_path` / `choose_longest_prefix_match` assign a file
  to the service whose `context` is the **longest prefix** of the file path.
- If no context matches, the fragment's `service` becomes `""` (unresolved).
  Unresolved fragments are excluded from service counting and cross-service
  decisions in the metrics (see [metrics.md](metrics.md)).

This longest-prefix matching is what turns a clone pair into an *inter-service*
or *within-service* clone (see [definitions.md](definitions.md)).

## File-Category Classifier (`file_type`)

`get_file_type(file_path, *, language=None)` in `src/modules/util.py` tags each
fragment with one of four categories: `test`, `data`, `config`, `logic`. The
classifier is **path- and extension-based only** (it does not read file
contents). It runs in two stages.

**Stage 1 - path signal** (`_get_file_type_from_path`), first match wins, in
this order:

1. `test` - path contains any test indicator:
   `/test/`, `/tests/`, `/test_`, `test_`, `_test.`, `.test.`, `/spec/`,
   `/specs/`, `_spec.`, `.spec.`, `/__tests__/`.
2. `config` - file name is a known config name
   (e.g. `dockerfile`, `docker-compose.yml`, `makefile`, `.env`,
   `package.json`, `tsconfig.json`, `setup.py`, `pyproject.toml`, `pom.xml`,
   `build.gradle`, `cargo.toml`, `go.mod`, `requirements.txt`, `gemfile`, and
   the common JS tool configs).
3. `config` - extension in `.yml`, `.yaml`, `.toml`, `.ini`, `.cfg`, `.conf`.
4. `config` - path contains a config directory: `/config/`, `/configs/`,
   `/.github/`, `/.circleci/`.
5. `data` - path contains a data indicator: `/entity/`, `/entities/`, `/dto/`,
   `/proto/`, `/migration/`, `/migrations/`, `/seed/`, `/seeds/`, `/fixture/`,
   `/fixtures/`.
6. `data` - extension in `.sql`, `.graphql`, `.proto`, `.avsc`.
7. Otherwise `logic`.

**Stage 2 - extension fallback** (only when stage 1 returns `logic`): extension
in the config set returns `config`, extension in the data set returns `data`,
otherwise `logic`.

The `language` argument is currently accepted but unused; it is kept so that
language-specific rules can be added without changing call sites.

`file_type` is attached to every row of `enriched_fragments.csv` and to the
scatter dataset, and is used as a categorical filter in the visualization.
