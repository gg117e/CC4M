# Definitions

Terms used throughout CC4M. They reflect the current implementation.

## Clone fragment

A single contiguous code region reported by CCFinderSW, identified by
`(file_path, start_line, end_line)`. One row of `enriched_fragments.csv`.

## Clone set

The set of fragments that share the same `clone_id`. CCFinderSW groups
mutually-cloned fragments into one clone set (a clone class). CC4M detects
Type-1 and Type-2 clones.

## Service (microservice)

A code region owned by one microservice, defined by a *context* path detected
from the project's Docker Compose / build configuration via CLAIM. A file is
assigned to the service whose context is the longest matching prefix of its
repo-relative path. A fragment whose service cannot be resolved has
`service == ""` (unresolved). See
[file_classification.md](file_classification.md).

## Inter-service vs within-service clone

Considering only fragments with a resolved service:

- **Inter-service (cross-service) clone** - a clone set spanning two or more
  services (`service_count >= 2`).
- **Within-service (intra-service) clone** - a clone set contained in a single
  service.

In the scatter plot the same distinction appears per clone pair as the
`relation` field: `inter` (different services) or `intra` (same service).

## File category (`file_type`)

Each fragment is tagged with one category, derived from its file path and
extension only:

- `test` - test/spec files and directories.
- `data` - schemas, entities, DTOs, migrations, fixtures, and data-format files.
- `config` - build/config/CI files and config-format files.
- `logic` - everything else (the default).

The exact rules and ordering are in
[file_classification.md](file_classification.md).

## Co-modification

Within one clone set, a commit that modified two or more fragments is a
*co-modification commit*. A clone set that has at least one such commit was
co-modified: changes to one cloned region were accompanied by changes to another
in the same commit, which is the signal CC4M uses for "changes propagate across
the clone". The scatter plot marks co-modified clone pairs separately.

## ROC (Ratio of Clones)

Per service, the fraction of the service's lines covered by clone lines:
`total_clone_line_count / service total_loc`, where the clone lines are
deduplicated by merging overlapping intervals per file. See
[metrics.md](metrics.md).

## Analyzed commits

The subset of a repository's history that the pipeline analyzes. The selection
strategy (merge commits, tags, or fixed frequency) is configurable. See
[dataset.md](dataset.md).
