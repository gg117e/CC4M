import json
import logging
import sys
from pathlib import Path

import git

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())

sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))
from modules.util import FileMapper


def _load_ccfsw(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def _initialize_latest_clones(
    head_ccfsw: dict, file_map: FileMapper
) -> tuple[dict, dict]:
    """初期コミットのクローン情報を準備する。"""
    latest_codeclones: dict[int, dict[int, dict]] = {}
    mapping: dict[tuple[int, int], tuple[int, int]] = {}

    for clone_set in head_ccfsw["clone_sets"]:
        clone_id = clone_set["clone_id"]
        latest_codeclones[clone_id] = {}
        for index, fragment in enumerate(clone_set["fragments"]):
            latest_codeclones[clone_id][index] = {
                "file_path": file_map.get_file_path(fragment["file_id"]),
                "start_line": fragment["start_line"],
                "end_line": fragment["end_line"],
                "start_col": fragment["start_col"],
                "end_col": fragment["end_col"],
                "modification": [],
            }
            mapping[(clone_id, index)] = (clone_id, index)
    return latest_codeclones, mapping


def _record_modification(
    latest_codeclones: dict,
    latest_clone_id: int,
    latest_index: int,
    mod_type: str,
    commit_hash: str,
):
    """最新のクローンに変更情報を追加する。"""
    if latest_clone_id is None or latest_index is None:
        return
    latest_codeclones[latest_clone_id][latest_index]["modification"].append(
        {
            "type": mod_type,
            "commit": commit_hash,
        }
    )


def analyze_repo(project: dict):
    """指定プロジェクトのクローン変更履歴を集計する。"""
    url = project["URL"]
    name = url.split("/")[-2] + "." + url.split("/")[-1]
    workdir = project_root / "dest/projects" / name
    git_repo = git.Repo(workdir)
    analyzed_commits_path = project_root / "dest/analyzed_commits" / f"{name}.json"
    logger.info("analyze_modification: %s", name)

    with open(analyzed_commits_path, "r") as f:
        analyzed_commit_hashes = json.load(f)
    head_commit = git_repo.commit(analyzed_commit_hashes[0])

    for language in project["languages"]:
        logger.info("  language: %s", language)
        head_ccfsw_file = (
            project_root
            / "dest/clones_json"
            / name
            / head_commit.hexsha
            / f"{language}.json"
        )
        head_ccfsw = _load_ccfsw(head_ccfsw_file)
        latest_file_map = FileMapper(head_ccfsw["file_data"], str(workdir))

        latest_codeclones, head_mapping = _initialize_latest_clones(
            head_ccfsw, latest_file_map
        )
        prev_mapping_by_commit: dict[
            str, dict[tuple[int, int], tuple[int, int] | tuple[None, None]]
        ] = {head_commit.hexsha: head_mapping}

        prev_commit = head_commit
        total_commits = len(analyzed_commit_hashes) - 1
        commit_idx = 0
        for commit_hash in analyzed_commit_hashes:
            if commit_hash == head_commit.hexsha:
                continue

            commit_idx += 1
            commit = git_repo.commit(commit_hash)
            if commit_idx == 1 or commit_idx % 10 == 0 or commit_idx == total_commits:
                logger.info("  commit progress: %d/%d", commit_idx, total_commits)
            modified_clones_file = (
                project_root
                / "dest/modified_clones"
                / name
                / f"{commit.hexsha}-{prev_commit.hexsha}"
                / f"{language}.json"
            )

            if not modified_clones_file.exists():
                prev_mapping_by_commit[commit.hexsha] = prev_mapping_by_commit[
                    prev_commit.hexsha
                ]
                prev_commit = commit
                continue

            modified_clones = _load_ccfsw(modified_clones_file)
            prev_mapping_by_commit[commit.hexsha] = {}

            for modified_clone in modified_clones:
                for fragment in modified_clone["fragments"]:
                    child_key = (
                        int(fragment["child"]["clone_id"]),
                        int(fragment["child"]["index"]),
                    )
                    if child_key not in prev_mapping_by_commit[prev_commit.hexsha]:
                        continue

                    # 親フラグメントへの対応を更新（added 以外）
                    if fragment["type"] != "added":
                        parent_key = (
                            int(fragment["parent"]["clone_id"]),
                            int(fragment["parent"]["index"]),
                        )
                        prev_mapping_by_commit[commit.hexsha].setdefault(
                            parent_key, (None, None)
                        )
                        prev_mapping_by_commit[commit.hexsha][parent_key] = (
                            prev_mapping_by_commit[prev_commit.hexsha][child_key]
                        )

                    if fragment["type"] == "modified":
                        parent_key = (
                            int(fragment["parent"]["clone_id"]),
                            int(fragment["parent"]["index"]),
                        )
                        latest_clone_id, latest_index = prev_mapping_by_commit[
                            commit.hexsha
                        ][parent_key]
                        _record_modification(
                            latest_codeclones,
                            latest_clone_id,
                            latest_index,
                            "modified",
                            prev_commit.hexsha,
                        )
                    elif fragment["type"] == "added":
                        latest_clone_id, latest_index = prev_mapping_by_commit[
                            prev_commit.hexsha
                        ][child_key]
                        _record_modification(
                            latest_codeclones,
                            latest_clone_id,
                            latest_index,
                            "added",
                            commit.hexsha,
                        )

            prev_commit = commit

        dest_dir = project_root / "dest/csv" / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        with open(dest_dir / f"{language}.csv", "w") as f:
            f.write(
                "clone_id;index;file_path;start_line;end_line;start_column;end_column;modification\n"
            )
            for clone_id, fragments in latest_codeclones.items():
                for index, fragment in fragments.items():
                    modification_str = json.dumps(fragment["modification"])
                    f.write(
                        f"{clone_id};{index};{fragment['file_path']};"
                        f"{fragment['start_line']};{fragment['end_line']};"
                        f"{fragment['start_col']};{fragment['end_col']};{modification_str}\n"
                    )
