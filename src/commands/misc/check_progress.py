import argparse
import json
import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

from config import SELECTED_DATASET


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check run-all-steps progress.")
    parser.add_argument(
        "--dataset",
        default=SELECTED_DATASET,
        help="Dataset JSON path (default: config.SELECTED_DATASET).",
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Show per-project status details.",
    )
    return parser.parse_args()


def _project_name(url: str) -> str:
    parts = url.rstrip("/").split("/")
    return parts[-2] + "." + parts[-1]


def main() -> int:
    args = _parse_args()
    with open(args.dataset, "r") as f:
        dataset = json.load(f)

    results = []
    for idx, project in enumerate(dataset):
        name = _project_name(project["URL"])
        languages = list(project["languages"].keys())
        csv_dir = project_root / "dest/csv" / name
        missing_csv = [lang for lang in languages if not (csv_dir / f"{lang}.csv").exists()]

        missing_prereq = []
        if not (project_root / "dest/projects" / name).exists():
            missing_prereq.append("repo")
        if not (project_root / "dest/analyzed_commits" / f"{name}.json").exists():
            missing_prereq.append("analyzed_commits")

        results.append(
            {
                "index": idx,
                "name": name,
                "completed": len(missing_csv) == 0,
                "missing_csv": missing_csv,
                "missing_prereq": missing_prereq,
            }
        )

    last_contiguous = -1
    for result in results:
        if result["completed"]:
            last_contiguous = result["index"]
        else:
            break

    last_any = max((r["index"] for r in results if r["completed"]), default=-1)

    print(f"projects: {len(results)}")
    if last_contiguous >= 0:
        name = results[last_contiguous]["name"]
        print(f"last_contiguous_complete: {last_contiguous + 1} {name}")
    else:
        print("last_contiguous_complete: none")

    if last_contiguous + 1 < len(results):
        first_incomplete = results[last_contiguous + 1]
        print(f"first_incomplete: {first_incomplete['index'] + 1} {first_incomplete['name']}")
    else:
        print("first_incomplete: none")

    if last_any >= 0:
        name = results[last_any]["name"]
        print(f"last_complete_anywhere: {last_any + 1} {name}")
    else:
        print("last_complete_anywhere: none")

    if args.detail:
        for result in results:
            missing_csv = ",".join(result["missing_csv"]) or "-"
            missing_prereq = ",".join(result["missing_prereq"]) or "-"
            status = "complete" if result["completed"] else "incomplete"
            print(
                f"{result['index'] + 1:03d} {status} {result['name']} "
                f"missing_csv=[{missing_csv}] missing_prereq=[{missing_prereq}]"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
