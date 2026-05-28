import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.pyplot as plt

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

MODE_LABELS = {
    "within-testing": "Within Testing",
    "within-production": "Within Production",
    "within-mixed": "Within Mixed",
    "inter-testing": "Inter Testing",
    "inter-production": "Inter Production",
    "inter-mixed": "Inter Mixed",
}

INTER_MODES = [
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


def compute_clone_ratios(clonesets: dict, workdir: Path) -> Dict[str, Optional[float]]:
    """Calculate clone ratios per mode using fragment line ranges."""
    ratios: dict[str, Optional[float]] = {}
    loc_cache: dict[str, int] = {}

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

                start = max(int(fragment["start_line"]) - 1, 0)
                end = min(int(fragment["end_line"]), loc_cache[file_path])
                for idx in range(start, end):
                    line_flags_by_file[file_path][idx] = True

        if not line_flags_by_file:
            ratios[mode] = None
            continue

        total = sum(len(flags) for flags in line_flags_by_file.values())
        clones = sum(sum(flags) for flags in line_flags_by_file.values())
        ratios[mode] = clones / total if total else None

    return ratios


def collect_clone_ratios(dataset: List[dict]) -> tuple[Dict[str, List[float]], List[str]]:
    """Collect clone ratios per mode for every project-language entry."""
    ratios_by_mode: Dict[str, List[float]] = {mode: [] for mode in MODES}
    missing_csv: List[str] = []

    for project in dataset:
        url = project["URL"]
        name = url.split("/")[-2] + "." + url.split("/")[-1]
        workdir = project_root / "dest/projects" / name

        for language in project["languages"]:
            csv_path = project_root / "dest/csv" / name / f"{language}.csv"
            if not csv_path.exists():
                missing_csv.append(str(csv_path))
                continue

            rows_by_clone: dict[str, list[dict]] = defaultdict(list)
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    clone_id = row["clone_id"]
                    rows_by_clone[clone_id].append(row)

            clonesets = classify_clones(rows_by_clone, project["languages"][language])
            mode_clone_ratios = compute_clone_ratios(clonesets, workdir)

            for mode, value in mode_clone_ratios.items():
                if value is not None:
                    ratios_by_mode[mode].append(value)

    return ratios_by_mode, missing_csv


def save_boxplot(values: List[float], mode: str, output_dir: Path) -> Path:
    """Save a boxplot for the given mode clone ratios."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = "DejaVu Sans"

    fig, ax = plt.subplots(figsize=(4, 6))
    ax.boxplot(
        values,
        patch_artist=True,
        boxprops=dict(facecolor="white", edgecolor="black"),
        medianprops=dict(color="black"),
        whiskerprops=dict(color="black"),
        capprops=dict(color="black"),
        flierprops=dict(marker="o", markerfacecolor="white", markeredgecolor="black", markersize=4),
    )
    ax.set_ylim(0, 1)
    ax.grid(True, axis="y", alpha=0.3)

    output_path = output_dir / f"clone_ratio_boxplot_{mode}.pdf"
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def save_inter_service_panel(ratios_by_mode: dict[str, List[float]], output_dir: Path) -> Optional[Path]:
    """Save a side-by-side boxplot of inter-service clone ratios."""
    inter_values = []
    for mode in INTER_MODES:
        values = ratios_by_mode.get(mode, [])
        if not values:
            print(f"[skip] No inter-service clone ratio data for {mode}")
            return None
        inter_values.append(values)

    output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = "DejaVu Sans"

    fig, axes = plt.subplots(1, 3, figsize=(6.0, 3.0), sharey=True, constrained_layout=True)
    for ax, mode, values in zip(axes, INTER_MODES, inter_values):
        ax.boxplot(
            values,
            patch_artist=True,
            boxprops=dict(facecolor="white", edgecolor="black"),
            medianprops=dict(color="black"),
            whiskerprops=dict(color="black"),
            capprops=dict(color="black"),
            flierprops=dict(marker="o", markerfacecolor="white", markeredgecolor="black", markersize=4),
        )
        ax.set_title(MODE_LABELS[mode], fontsize=11)
        ax.set_ylim(0, 1)
        ax.grid(True, axis="y", alpha=0.3)
        ax.set_xticks([])

    output_path = output_dir / "clone_ratio_boxplot_inter_services.pdf"
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate clone ratio boxplots by category.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "dest" / "figures",
        help="Directory to write PDF files (default: dest/figures)",
    )
    args = parser.parse_args()

    dataset = load_dataset()
    ratios_by_mode, missing_csv = collect_clone_ratios(dataset)

    generated = []
    for mode in MODES:
        values = ratios_by_mode.get(mode, [])
        if not values:
            print(f"[skip] No clone ratio data for {mode}")
            continue
        output_path = save_boxplot(values, mode, args.output_dir)
        generated.append(output_path)
        print(f"[ok] Saved: {output_path}")

    panel_path = save_inter_service_panel(ratios_by_mode, args.output_dir)
    if panel_path:
        generated.append(panel_path)
        print(f"[ok] Saved inter-service panel: {panel_path}")

    if missing_csv:
        print("\n[warn] Missing CSV files:")
        for path in missing_csv:
            print(f"- {path}")

    if not generated:
        print("No plots were generated.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
