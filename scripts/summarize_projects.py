"""Summarize per-project statistics from analysis results under dest/.

For every project that has a service map in dest/services_json/, this script
reports the number of services, source files, lines of code, and clone sets:

* Services    - distinct service names in the CLAIM service map.
* Files / LOC - sum of ``total_files`` / ``total_loc`` over the per-language
                ``language_stats`` entries (unresolved files are excluded,
                matching the numbers reported in the paper).
* Clone Sets  - sum of ``len(clone_set)`` over the per-language files in
                dest/clone_metrics/.

Usage:
    python scripts/summarize_projects.py            # aligned text table
    python scripts/summarize_projects.py --format markdown
    python scripts/summarize_projects.py --format latex
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEST_DIR = REPO_ROOT / "dest"


def load_project_stats(project_key: str) -> dict:
    services_json = DEST_DIR / "services_json" / f"{project_key}.json"
    data = json.loads(services_json.read_text(encoding="utf-8"))

    service_names: set[str] = set()
    for names in data.get("services", {}).values():
        service_names.update(names)

    total_files = 0
    total_loc = 0
    languages: list[str] = []
    for language, stats in sorted(data.get("language_stats", {}).items()):
        languages.append(language)
        total_files += stats.get("total_files", 0)
        total_loc += stats.get("total_loc", 0)

    clone_sets = 0
    for metrics_path in sorted(
        (DEST_DIR / "clone_metrics").glob(f"{project_key}_*.json")
    ):
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        clone_sets += len(metrics.get("clone_set", []))

    return {
        "project": project_key,
        "languages": languages,
        "services": len(service_names),
        "files": total_files,
        "loc": total_loc,
        "clone_sets": clone_sets,
    }


def collect_stats() -> list[dict]:
    project_keys = sorted(
        path.stem for path in (DEST_DIR / "services_json").glob("*.json")
    )
    return [load_project_stats(key) for key in project_keys]


def fmt(value: int) -> str:
    return f"{value:,}"


def print_text(rows: list[dict]) -> None:
    header = f"{'Project':<42} {'Services':>8} {'Files':>7} {'LOC':>9} {'Clone Sets':>10}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['project']:<42} {fmt(row['services']):>8} {fmt(row['files']):>7}"
            f" {fmt(row['loc']):>9} {fmt(row['clone_sets']):>10}"
        )


def print_markdown(rows: list[dict]) -> None:
    print("| Project | Services | Files | LOC | Clone Sets |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for row in rows:
        print(
            f"| {row['project']} | {fmt(row['services'])} | {fmt(row['files'])}"
            f" | {fmt(row['loc'])} | {fmt(row['clone_sets'])} |"
        )


def print_latex(rows: list[dict]) -> None:
    def latex_num(value: int) -> str:
        return f"{value:,}".replace(",", "{,}")

    for row in rows:
        print(
            f"{row['project']} & {latex_num(row['services'])} & {latex_num(row['files'])}"
            f" & {latex_num(row['loc'])} & {latex_num(row['clone_sets'])} \\\\"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "latex"],
        default="text",
        help="output format (default: text)",
    )
    args = parser.parse_args()

    rows = collect_stats()
    if args.format == "markdown":
        print_markdown(rows)
    elif args.format == "latex":
        print_latex(rows)
    else:
        print_text(rows)


if __name__ == "__main__":
    main()
