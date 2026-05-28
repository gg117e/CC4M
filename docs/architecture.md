# Architecture

CC4M clones a microservice repository, detects code clones across analyzed
commits with CCFinderSW, enriches the clones with service-boundary,
co-modification, file-category and metric information, and serves an
interactive Dash visualization behind a FastAPI web UI.

## Top-level layout

```text
main.py                  CLI launcher; dispatches subcommands into src/commands/
config.py                Path constants for dest/* and CCFinderSW settings
src/commands/            CLI subcommand entry scripts
  pipeline/                generate_dataset, determine_analyzed_commits, refresh_service_map
  csv_build/               run_all_step (orchestrator), generate_visualization_csv
  csv_analysis/            generate_report, generate_figure
  misc/                    check_progress
src/modules/             Core analysis logic
  CLAIM/                   Docker-Compose / microservice detection helpers
  visualization/           Build scatter / enriched_fragments / clone_metrics
src/visualize/           Dash app (scatter, drill-down, components, callbacks)
src/web/                 FastAPI app: mounts the Dash app, exposes /api/run and /ws/logs
lib/CCFinderSW-1.0/      Bundled clone-detection JAR
lib/CLAIM/               Bundled microservice-detection tool
dataset/                 Input dataset (download separately)
dest/                    Generated artifacts; includes the bundled review demo
```

## Data pipeline (per project)

`run-all-steps` iterates the dataset and runs three steps per project; each step
writes into `dest/*` and the next reads it.

1. **collect** (`modules.collect_datas`) - clone the repo, optionally apply
   declaration-line filtering, run CCFinderSW per analyzed commit, and capture
   git diffs. Outputs: `dest/clones_json/`, `dest/moving_lines/`, `dest/csv/`.
2. **analyze-cc** (`modules.analyze_cc`) - correspond clone fragments across
   adjacent commits and classify each as added / modified / stable. Output:
   `dest/modified_clones/`.
3. **analyze-modification** (`modules.analyze_modification`) - aggregate the
   per-commit modification history onto the latest clones. Output: `dest/csv/`.

Declaration-line filtering is described in
[declaration_line_filtering.md](declaration_line_filtering.md). File-path,
service, and file-type handling are described in
[file_classification.md](file_classification.md).

## Visualization data build

`src/modules/visualization/` turns the raw pipeline output into the four
artifacts the Dash app reads:

- `build_scatter_dataset` -> `dest/scatter/` - clone pairs (O(n^2)) for the
  scatter plot, with `relation` (intra/inter), `comodified`, `file_type`.
- `build_enriched_fragments` -> `dest/enriched_fragments/` - one row per
  fragment (O(n)), optimized for metric computation.
- `enrich_services` -> `dest/services_json/` - adds `language_stats`
  (per-service file count and total LOC) used as the ROC denominator.
- `compute_clone_metrics` -> `dest/clone_metrics/` - the three-granularity
  metrics described in [metrics.md](metrics.md).

The Dash app reads only these four directories. It prefers the precomputed
`clone_metrics` JSON and falls back to recomputing from `enriched_fragments.csv`.

## Web stack

`src/web/app.py` is the FastAPI entry point. It:

- mounts the Dash app via `WSGIMiddleware` at `/visualize`
  (`scatter.create_dash_app`),
- serves a settings UI at `/` and skips to `/visualize/` when started with
  `--visualize-only`,
- runs pipeline jobs in background threads (`pipeline_runner.run_job`) and
  streams their logs over `/ws/logs/{job_id}`.

`scripts/run_web.*` and `make web` serve `/visualize/` from existing `dest/`
artifacts. `docker compose up --build web-ui` adds the full clone-detection
pipeline.

## Path conventions and sys.path

All output paths live under `dest/` and are exposed as constants in `config.py`
(`DEST_SCATTER`, `DEST_SERVICES_JSON`, `DEST_ENRICHED_FRAGMENTS`,
`DEST_CLONE_METRICS`, ...). Modules import these constants instead of hardcoding
paths. Entry scripts walk up to the directory containing `pyproject.toml` and
prepend both that root and its `src/` to `sys.path`, so modules can be imported
as `modules.foo` and `src.web.bar` interchangeably.

For a function-level map of `src/`, see the inline docstrings; this document is
the architecture overview.
