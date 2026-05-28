import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

from config import SELECTED_DATASET  # noqa: E402
from modules.util import calculate_loc  # noqa: E402

MODES = [
    "within-testing",
    "within-production",
    "within-mixed",
    "inter-testing",
    "inter-production",
    "inter-mixed",
]


def load_dataset() -> List[dict]:
    with open(SELECTED_DATASET, "r") as f:
        return json.load(f)


def classify_clones(rows_by_clone: Dict[str, List[dict]], codebases: dict) -> dict:
    """Split clone sets by detection range and code type."""
    clonesets = {
        "within-testing": {},
        "within-production": {},
        "within-mixed": {},
        "inter-testing": {},
        "inter-production": {},
        "inter-mixed": {},
    }

    for clone_id, fragments in rows_by_clone.items():
        is_testing = any("test" in frag["file_path"].lower() for frag in fragments)
        is_production = any("test" not in frag["file_path"].lower() for frag in fragments)

        service_set = set()
        service_fragments = []
        for fragment in fragments:
            for codebase in codebases:
                if fragment["file_path"].startswith(codebase):
                    service_set.add(codebase)
                    service_fragments.append(fragment)
                    break

        if len(service_fragments) <= 1:
            continue

        if len(service_set) == 1:
            range_name = "within"
        elif len(service_set) >= 2:
            range_name = "inter"
        else:
            continue

        if is_testing and not is_production:
            code_type = "testing"
        elif is_production and not is_testing:
            code_type = "production"
        else:
            code_type = "mixed"

        key = f"{range_name}-{code_type}"
        clonesets[key][clone_id] = service_fragments

    return clonesets


def compute_clone_ratios(clonesets: dict, workdir: Path) -> tuple[Dict[str, Optional[float]], Optional[float]]:
    """Calculate clone ratios per mode and overall using fragment line ranges."""
    ratios: dict[str, float] = {}
    loc_cache: dict[str, int] = {}
    overall_line_flags_by_file: Dict[str, List[bool]] = {}

    for mode, clone_map in clonesets.items():
        line_flags_by_file: Dict[str, List[bool]] = {}
        for fragments in clone_map.values():
            for fragment in fragments:
                file_path = fragment["file_path"]
                abs_path = workdir / file_path
                if not abs_path.exists():
                    continue

                if file_path not in loc_cache:
                    try:
                        loc_cache[file_path] = calculate_loc(str(abs_path))
                    except OSError:
                        continue

                if file_path not in line_flags_by_file:
                    line_flags_by_file[file_path] = [False] * loc_cache[file_path]
                if file_path not in overall_line_flags_by_file:
                    overall_line_flags_by_file[file_path] = [False] * loc_cache[file_path]

                start = max(int(fragment["start_line"]) - 1, 0)
                end = min(int(fragment["end_line"]), loc_cache[file_path])
                for idx in range(start, end):
                    line_flags_by_file[file_path][idx] = True
                    overall_line_flags_by_file[file_path][idx] = True

        if not line_flags_by_file:
            ratios[mode] = None
            continue

        total = sum(len(flags) for flags in line_flags_by_file.values())
        clones = sum(sum(flags) for flags in line_flags_by_file.values())
        ratios[mode] = clones / total if total else None

    overall_ratio: Optional[float]
    if not overall_line_flags_by_file:
        overall_ratio = None
    else:
        total = sum(len(flags) for flags in overall_line_flags_by_file.values())
        clones = sum(sum(flags) for flags in overall_line_flags_by_file.values())
        overall_ratio = clones / total if total else None

    return ratios, overall_ratio


def compute_comodification(clonesets: dict) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """Calculate comodification counts per mode and overall."""
    comodification: dict[str, dict[str, int]] = {}
    overall = {"count": 0, "comodification_count": 0}
    for mode, clone_map in clonesets.items():
        count = 0
        comodified = 0
        for fragments in clone_map.values():
            count += 1
            overall["count"] += 1
            modifications = defaultdict(list)
            for fragment in fragments:
                for entry in json.loads(fragment["modification"]):
                    modifications[entry.get("commit")].append(entry.get("type"))
            if any(types.count("modified") >= 2 for types in modifications.values()):
                comodified += 1
                overall["comodification_count"] += 1
        comodification[mode] = {"count": count, "comodification_count": comodified}
    return comodification, overall


def summarize(values: List[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {"n": 0, "mean": None, "variance": None, "median": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "variance": statistics.pvariance(values) if len(values) >= 2 else 0.0,
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def main():
    dataset = load_dataset()
    total_project_languages = sum(len(project["languages"]) for project in dataset)
    total_projects = len(dataset)
    projects_by_language: dict[str, set[str]] = defaultdict(set)

    project_languages_with_clones = set()
    project_languages_with_inter = set()
    project_languages_with_inter_modified = set()
    project_languages_with_inter_comodification = set()
    project_languages_with_within = set()
    project_languages_with_within_modified = set()
    project_languages_with_within_comodification = set()
    missing_csv = []

    fragment_total = 0
    fragment_modified = 0

    cloneset_total = 0
    cloneset_with_modified = 0

    clone_ratio_values = []
    clone_ratio_values_by_mode = {mode: [] for mode in MODES}
    comodification_rates = []
    comodification_rates_by_mode = {mode: [] for mode in MODES}

    for project in dataset:
        url = project["URL"]
        name = url.split("/")[-2] + "." + url.split("/")[-1]
        workdir = project_root / "dest/projects" / name
        for language in project["languages"]:
            projects_by_language[language].add(name)

        for language in project["languages"]:
            csv_path = project_root / "dest/csv" / name / f"{language}.csv"
            if not csv_path.exists():
                missing_csv.append(str(csv_path))
                continue

            rows_by_clone: dict[str, list[dict]] = defaultdict(list)
            modified_clone_ids = set()
            project_language_key = f"{name}-{language}"

            with open(csv_path, "r") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    fragment_total += 1
                    clone_id = row["clone_id"]
                    rows_by_clone[clone_id].append(row)

                    modifications = json.loads(row["modification"])
                    if any(m.get("type") == "modified" for m in modifications):
                        fragment_modified += 1
                        modified_clone_ids.add(clone_id)

            if rows_by_clone:
                project_languages_with_clones.add(project_language_key)

            cloneset_total += len(rows_by_clone)
            cloneset_with_modified += len(modified_clone_ids)

            clonesets = classify_clones(rows_by_clone, project["languages"][language])
            if any(clonesets[key] for key in ("within-testing", "within-production", "within-mixed")):
                project_languages_with_within.add(project_language_key)
            if any(clonesets[key] for key in ("inter-testing", "inter-production", "inter-mixed")):
                project_languages_with_inter.add(project_language_key)
            within_clone_ids = set()
            for key in ("within-testing", "within-production", "within-mixed"):
                within_clone_ids.update(clonesets[key].keys())
            inter_clone_ids = set()
            for key in ("inter-testing", "inter-production", "inter-mixed"):
                inter_clone_ids.update(clonesets[key].keys())
            if within_clone_ids & modified_clone_ids:
                project_languages_with_within_modified.add(project_language_key)
            if inter_clone_ids & modified_clone_ids:
                project_languages_with_inter_modified.add(project_language_key)

            mode_clone_ratios, overall_clone_ratio = compute_clone_ratios(clonesets, workdir)
            if overall_clone_ratio is not None:
                clone_ratio_values.append(overall_clone_ratio)
            for mode, value in mode_clone_ratios.items():
                if value is not None:
                    clone_ratio_values_by_mode.setdefault(mode, []).append(value)

            comodification_by_mode, overall_comodification = compute_comodification(clonesets)
            if overall_comodification["count"] > 0:
                comodification_rates.append(
                    overall_comodification["comodification_count"] / overall_comodification["count"]
                )
            for mode, data in comodification_by_mode.items():
                if data["count"] > 0:
                    rate = data["comodification_count"] / data["count"]
                    comodification_rates_by_mode.setdefault(mode, []).append(rate)
                if mode.startswith("within-") and data["comodification_count"] > 0:
                    project_languages_with_within_comodification.add(project_language_key)
                if mode.startswith("inter-") and data["comodification_count"] > 0:
                    project_languages_with_inter_comodification.add(project_language_key)

    clone_ratio_stats = summarize(clone_ratio_values)
    clone_ratio_stats_by_mode = {mode: summarize(values) for mode, values in clone_ratio_values_by_mode.items()}
    comodification_stats = summarize(comodification_rates)
    comodification_stats_by_mode = {
        mode: summarize(values) for mode, values in comodification_rates_by_mode.items()
    }

    print("# Report")
    print(f"- Total project-language entries: {total_project_languages}")
    print(
        f"- Project-language entries with clones: {len(project_languages_with_clones)} "
        f"({(len(project_languages_with_clones) / total_project_languages * 100) if total_project_languages else 0:.2f}%)"
    )
    print(
        f"- Project-language entries with within-service clones: {len(project_languages_with_within)} "
        f"({(len(project_languages_with_within) / total_project_languages * 100) if total_project_languages else 0:.2f}%)"
    )
    print(
        f"- Project-language entries with inter-service clones: {len(project_languages_with_inter)} "
        f"({(len(project_languages_with_inter) / total_project_languages * 100) if total_project_languages else 0:.2f}%)"
    )
    print(
        f"- Project-language entries with modified within-service clone sets: {len(project_languages_with_within_modified)} "
        f"({(len(project_languages_with_within_modified) / total_project_languages * 100) if total_project_languages else 0:.2f}%)"
    )
    print(
        f"- Project-language entries with modified inter-service clone sets: {len(project_languages_with_inter_modified)} "
        f"({(len(project_languages_with_inter_modified) / total_project_languages * 100) if total_project_languages else 0:.2f}%)"
    )
    print(
        f"- Project-language entries with co-modified within-service clone sets: {len(project_languages_with_within_comodification)} "
        f"({(len(project_languages_with_within_comodification) / total_project_languages * 100) if total_project_languages else 0:.2f}%)"
    )
    print(
        f"- Project-language entries with co-modified inter-service clone sets: {len(project_languages_with_inter_comodification)} "
        f"({(len(project_languages_with_inter_comodification) / total_project_languages * 100) if total_project_languages else 0:.2f}%)"
    )
    print("- Aggregation unit for clone metrics: clone sets (clone_id groups)")
    print(f"- Clone fragments: {fragment_total:,}; modified fragments: {fragment_modified:,} ({(fragment_modified / fragment_total * 100) if fragment_total else 0:.2f}%)")
    print(f"- Clone sets: {cloneset_total:,}; sets with modified fragments: {cloneset_with_modified:,} ({(cloneset_with_modified / cloneset_total * 100) if cloneset_total else 0:.2f}%)")
    print()
    print("## Clone ratio stats")
    print(f"- count: {clone_ratio_stats['n']}")
    print(f"- mean: {clone_ratio_stats['mean']}")
    print(f"- variance: {clone_ratio_stats['variance']}")
    print(f"- median: {clone_ratio_stats['median']}")
    print(f"- min: {clone_ratio_stats['min']}")
    print(f"- max: {clone_ratio_stats['max']}")
    print()
    print("## Clone ratio stats by category")
    for mode in MODES:
        stats = clone_ratio_stats_by_mode.get(mode, {"n": 0, "mean": None, "variance": None, "median": None, "min": None, "max": None})
        print(f"- {mode}: count={stats['n']}, mean={stats['mean']}, variance={stats['variance']}, median={stats['median']}, min={stats['min']}, max={stats['max']}")
    print()
    print("## Comodification rate stats")
    print(f"- count: {comodification_stats['n']}")
    print(f"- mean: {comodification_stats['mean']}")
    print(f"- variance: {comodification_stats['variance']}")
    print(f"- median: {comodification_stats['median']}")
    print(f"- min: {comodification_stats['min']}")
    print(f"- max: {comodification_stats['max']}")
    print()
    print("## Comodification rate stats by category")
    for mode in MODES:
        stats = comodification_stats_by_mode.get(mode, {"n": 0, "mean": None, "variance": None, "median": None, "min": None, "max": None})
        print(f"- {mode}: count={stats['n']}, mean={stats['mean']}, variance={stats['variance']}, median={stats['median']}, min={stats['min']}, max={stats['max']}")

    if missing_csv:
        print("\n## Missing CSV files")
        for path in missing_csv:
            print(f"- {path}")

    print("\n## Projects per language in dataset")
    print(f"- total projects: {total_projects}")
    for language, projects in sorted(projects_by_language.items(), key=lambda x: (-len(x[1]), x[0].lower())):
        print(f"- {language}: {len(projects)}")


if __name__ == "__main__":
    main()
