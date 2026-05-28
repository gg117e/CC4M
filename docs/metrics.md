# Clone Metrics

This document defines the clone metrics computed by
`src/modules/visualization/compute_clone_metrics.py`. The descriptions below
are taken directly from that implementation.

The metrics are exploratory indicators. Their goal is to show *which services
and files are most tightly coupled by clones* and *where clones are
co-modified*, so that a user can prioritize clones with a potentially higher
maintenance impact.

## Input

Every metric is computed from `enriched_fragments.csv`, which has one row per
clone fragment:

```text
clone_id, fragment_index, file_path, file_id, service,
start_line, end_line, line_count, file_type,
modified_commits, modified_count
```

`modified_commits` is a JSON array string holding the commit SHAs that modified
that fragment.

The only value taken from outside this CSV is the ROC denominator: the
per-service total LOC, read from
`services.json -> language_stats[language]["services"][service]["total_loc"]`.
`enriched_fragments.csv` contains only fragments that belong to a clone, so it
cannot provide the full LOC of a service.

## Shared definitions

**Clone set** — the set of fragments that share the same `clone_id`.

**Cross-service (inter-service) clone** — looking only at fragments with a
resolved service, a clone set is cross-service if it spans two or more services.
Fragments with `service == ""` (unresolved) are excluded from the service count.

**Co-modification commit** — within one clone set, a commit that appears in the
`modified_commits` of two or more fragments. At the clone-set granularity any
two fragments of the set count. At the service / file granularity, a
co-modification commit is counted only when a fragment of the target service or
target file actually participates in that commit.

## Service granularity (`ServiceMetrics`)

`ServiceMetrics` describes, per microservice, how much cloning it contains, how
cross-service it is, and how often it is co-modified.

| Field | Definition | Meaning |
|---|---|---|
| `service` | service name | aggregation target |
| `clone_set_count` | number of unique `clone_id`s that have a fragment in this service (intra and inter alike) | breadth of clone sets touching the service |
| `inter_clone_set_count` | of those, the clone sets spanning >= 2 services | clone sets shared with other services |
| `total_clone_line_count` | clone lines in this service after merging overlapping intervals per file (no double counting) | LOC covered by clones in the service |
| `clone_avg_line_count` | mean of the raw `line_count` over this service's fragments | typical detected fragment size |
| `clone_file_count` | number of unique `file_path`s with a clone in this service | how many files clones spread across |
| `roc` | `total_clone_line_count / service total_loc` | share of the service's LOC covered by clone lines |
| `comod_count` | number of unique co-modification commits in which this service's fragments participate | how often the service's clones were maintained together |
| `comod_other_service_count` | number of unique *other* services that participated in those same commits | other services coupled by co-modification |

`total_clone_line_count` and `roc` merge overlapping or adjacent clone intervals
within the same file (`_merge_intervals`), so a line covered by several clone
sets is counted once. By contrast `clone_avg_line_count` uses raw `line_count`:
it answers "how long is a typical detected fragment", which has a different
numerator than `total_clone_line_count`.

## Clone-set granularity (`CloneSetMetrics`)

`CloneSetMetrics` describes how far a single clone set spans services and how
much it is co-modified.

| Field | Definition | Meaning |
|---|---|---|
| `clone_id` | clone set id | aggregation target |
| `service_count` | number of unique resolved services the set spans | breadth of affected services |
| `cross_service_fragment_count` | if cross-service, the number of fragments with a resolved service; otherwise 0 | fragments participating in cross-service sharing |
| `cross_service_fragment_ratio` | `cross_service_fragment_count / total fragments` | participation ratio including unresolved fragments |
| `cross_service_line_count` | if cross-service, the sum of raw `line_count` over resolved fragments; otherwise 0 | size of the shared clone |
| `cross_service_scale` | `cross_service_fragment_count * cross_service_line_count` | ranking score that emphasizes both fragment count and size |
| `cross_service_element_count` | if cross-service, the total number of fragments; otherwise 0 | number of elements in the clone set |
| `comod_count` | number of co-modification commits | how often the set was modified together |
| `comod_fragment_count` | number of unique fragments involved in any co-modification commit | elements involved in co-modification |
| `comod_fragment_ratio` | `comod_fragment_count / total fragments` | share of the set involved in co-modification |

`cross_service_scale` is not a physical quantity; it is only a score for
sorting/highlighting large cross-service clone sets. `cross_service_element_count`
is close to `cross_service_fragment_count`; it lets a clone set that contains
unresolved-service fragments distinguish "all elements" from "service-resolved
elements".

## File granularity (`FileMetrics`)

`FileMetrics` describes, per file, its cross-service clone sharing and
co-modification.

The owning service of a file is the majority (`mode`) of the `service` values of
that file's fragments, excluding `service == ""`. If all are unresolved the
owning service is the empty string.

| Field | Definition | Meaning |
|---|---|---|
| `file_path` | file path | aggregation target |
| `service` | owning service | decided by majority vote |
| `sharing_service_count` | number of unique other services that share this file's clone sets | how many services it is clone-related to |
| `total_service_count` | total number of services in the project | denominator for ratios |
| `cross_service_clone_set_count` | of this file's clone sets, those that also appear in another service | clone sets shared with other services |
| `cross_service_clone_set_ratio` | `cross_service_clone_set_count / clone sets in the file` | sharing ratio of the file's clone sets |
| `sharing_service_ratio` | `sharing_service_count / total_service_count` | sharing partners as a fraction of all services |
| `cross_service_line_count` | for clone sets shared with other services, the sum of raw `line_count` of this file's fragments | size of shared clones in this file |
| `cross_service_comod_count` | number of co-modification commits where this file's fragments and another service's fragments participate together | how often the file was maintained together with another service |
| `comod_shared_service_count` | number of unique other services co-modified in those commits | other services coupled by co-modification |

The denominator of `sharing_service_ratio` is the total number of services
(including the file's own service), so for a file with a known owning service the
maximum is `(total_service_count - 1) / total_service_count`.

## Validity and caveats

These metrics are useful for visualization and prioritization. In particular
`roc`, `inter_clone_set_count`, `service_count`, `cross_service_clone_set_count`,
and `comod_count` make the scale, spread, and maintenance coupling of clones
easy to read. Note however:

- The metrics are line-based, not token-based (`enriched_fragments.csv` has no
  `token_count`), so they are coarse for fine-grained code-volume comparison.
- `clone_avg_line_count` and `cross_service_line_count` use raw `line_count`,
  not deduplicated LOC.
- `cross_service_scale` is a ranking score, not an absolute size.
- Fragments whose service could not be resolved have `service == ""` and are
  excluded from service counting and cross-service decisions, so service
  detection quality affects the metrics.
- Co-modification only checks "two or more fragments changed in the same
  commit"; it does not judge whether the changes were made for the same reason.

## Output

`compute_all_metrics()` returns:

```python
{
    "service": [...],     # ServiceMetrics rows
    "clone_set": [...],   # CloneSetMetrics rows
    "file": [...],        # FileMetrics rows
}
```

The pipeline saves this to `dest/clone_metrics/<project>_<language>.json`. The
visualization prefers the precomputed JSON and falls back to recomputing from
`enriched_fragments.csv` when it is missing.
