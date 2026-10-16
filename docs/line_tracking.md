# Line Tracking Between Analyzed Commits

This document describes how CC4M decides which lines changed between two
analyzed commits and how clone fragments are tracked across them. It is the
input to co-modification analysis (see [definitions.md](definitions.md)).
The implementation lives in `src/modules/moving_lines.py` and
`src/modules/analyze_cc.py`.

> **History:** before 2026-10-16 this step had three bugs that corrupted the
> co-modification signal (only the first hunk of each file was parsed, line
> numbers were shifted by +1, and the diff direction was reversed). Results
> produced before that date must be regenerated. See
> [PROGRESS.md](PROGRESS.md) for the full record.

## Terminology

The analyzed commits are ordered newest first. For each adjacent pair:

- **parent** = the older commit,
- **child** = the newer commit.

## Step 1: moving lines (`collect` step)

`compute_moving_lines(parent_commit, child_commit)` runs
`parent_commit.diff(child_commit, create_patch=True)` and parses **every hunk**
of every file with `parse_unified_diff`. For each file it records:

| Field | Coordinates | Meaning |
|---|---|---|
| `inserted_lines` | child | lines that exist only in the child |
| `deleted_lines` | parent | lines that exist only in the parent |
| `modified_lines` | child | replaced lines (child side) |
| `modified_parent_lines` | parent | replaced lines (parent side); `modified_parent_lines[i]` pairs with `modified_lines[i]` |

Parsing rules:

- Line counters start from the numbers in each `@@ -a,b +c,d @@` header. Text
  after the closing `@@` (function context) is ignored.
- A run of `-` lines followed by `+` lines is a replacement block. The first
  `min(#deleted, #inserted)` lines are paired as modified; the rest are pure
  deletions or insertions.
- `\ No newline at end of file` markers are ignored.

Results are saved to `dest/moving_lines/<project>/<parent>-<child>.json` as
`{"format_version": 2, "hunks": [...]}`. Files in the old list-only format are
treated as missing and recomputed.

## Step 2: line correspondence (`analyze-cc` step)

`CorrespondedLines` builds, for every changed file, a map from child line to
parent line by walking both files and skipping inserted (child) and deleted
(parent) lines. Paired modified lines correspond one-to-one. Files without
hunks map every line to itself.

## Step 3: fragment classification

Each child clone fragment is matched to a parent fragment in the same file
(endpoints mapped by the line correspondence). It is then classified as:

- `added` - no matching parent fragment (the lineage ends here),
- `modified` - any child line in the fragment was inserted or replaced, or any
  parent line in the matched fragment was deleted or replaced,
- `stable` - otherwise. A fragment that only moved because lines were inserted
  or deleted elsewhere in the file is `stable`.

Only `modified` counts as a modification for co-modification analysis.

## Known limitations

- Renamed or moved files are not followed (`child_path` must equal
  `parent_path`); their fragments become `added`.
- A fragment whose clone boundaries change without a matching endpoint case is
  treated as `added`.
- Tracking starts from the newest analyzed commit and walks back, so only
  clones that still exist in the newest commit are covered.
