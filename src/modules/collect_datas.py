from pathlib import Path
import sys
import subprocess
import git
import traceback
import json
import logging
import time
from typing import Optional, Tuple


def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))
from modules.github_linguist import get_exts
from modules.source_filter import apply_filter
from config import (
    ANTLR_LANGUAGE,
    CCFINDERSW_JAR,
    CCFINDERSWPARSER,
    CCFINDERSW_JAVA_XMX,
    CCFINDERSW_JAVA_XSS,
    APPLY_IMPORT_FILTER,
)

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _format_elapsed(seconds: float) -> str:
    """CLIに表示する所要時間を短く整形する。"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining_seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {remaining_seconds:.1f}s"
    hours, remaining_minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(remaining_minutes)}m {remaining_seconds:.1f}s"


def _write_status(message: str, log=None) -> None:
    """Web UIログがある場合はそこへ、CLI実行時はloggerへ進捗を出す。"""
    if log is not None:
        log.write(message + "\n")
    else:
        logger.info(message)


def parse_diff_str(diff: str) -> Optional[Tuple[list[str], int, int]]:
    """diff 文字列からハンク行と開始行番号を抽出する。"""
    diff_at_split = diff.split("@@")
    if len(diff_at_split) < 3:
        return None
    try:
        hunk_range_split = diff_at_split[1].replace("+", "").replace("-", "").split(" ")
        hunk_range_old = hunk_range_split[1]
        hunk_range_new = hunk_range_split[2]
        old_line_count = int(hunk_range_old.split(",")[0])
        new_line_count = int(hunk_range_new.split(",")[0])
    except (IndexError, ValueError):
        return None
    hunk_lines = diff_at_split[2].split("\n")
    return hunk_lines, old_line_count, new_line_count


def find_moving_lines(commit: git.Commit, prev: git.Commit, name: str):
    """2 つのコミット間で追加・削除・変更された行を収集して保存する。"""
    diff_hunks = prev.diff(commit, create_patch=True)
    output_result = []
    for diff_hunk in diff_hunks:
        if diff_hunk.diff:
            child_path = diff_hunk.b_path
            parent_path = diff_hunk.a_path
            try:
                result = parse_diff_str(diff_hunk.diff.decode("utf-8"))
                if result is None:
                    continue
            except UnicodeDecodeError:
                logger.warning("diff.diff.decode('utf-8')のデコードに失敗しました．")
                logger.warning(str(diff_hunk.diff))
                continue
            hunk, old_file_line_count, new_file_line_count = result
            potential_inserted_lines: list[int] = []
            potential_deleted_lines: list[int] = []
            for line in hunk:
                if line.startswith("+"):
                    potential_inserted_lines.append(new_file_line_count)
                    new_file_line_count += 1
                elif line.startswith("-"):
                    potential_deleted_lines.append(old_file_line_count)
                    old_file_line_count += 1
                else:
                    old_file_line_count += 1
                    new_file_line_count += 1
            inserted_lines = []
            deleted_lines = []
            modified_lines = []
            for inserted_line in potential_inserted_lines:
                if inserted_line not in potential_deleted_lines:
                    inserted_lines.append(inserted_line)
                else:
                    modified_lines.append(inserted_line)
            for deleted_line in potential_deleted_lines:
                if deleted_line not in potential_inserted_lines:
                    deleted_lines.append(deleted_line)
            output_result.append(
                {
                    "child_path": child_path,
                    "parent_path": parent_path,
                    "inserted_lines": inserted_lines,
                    "deleted_lines": deleted_lines,
                    "modified_lines": modified_lines,
                }
            )
    if output_result:
        dest_dir = project_root / "dest/moving_lines" / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{commit.hexsha}-{prev.hexsha}.json"
        with open(dest_file, "w") as f:
            json.dump(output_result, f)


def convert_language_for_ccfindersw(language: str) -> str:
    match language:
        case "C++":
            return "cpp"
        case "C#":
            return "csharp"
        case _:
            return language.lower()


def detect_cc(
    project: Path,
    name: str,
    language: str,
    commit_hash: str,
    exts: tuple[str],
    min_tokens: int = 50,
    log=None,
) -> float:
    """対象言語とコミットで CC-Finder SW を実行し、結果を保存する。"""
    start_time = time.perf_counter()
    try:
        dest_dir = project_root / "dest/temp/ccfswtxt" / name / commit_hash
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / language
        language_arg = convert_language_for_ccfindersw(language)
        base_cmd = [
            "java",
            f"-Xmx{CCFINDERSW_JAVA_XMX}",
            f"-Xss{CCFINDERSW_JAVA_XSS}",
            "-jar",
            str(CCFINDERSW_JAR),
            "D",
            "-d",
            str(project),
            "-l",
            language_arg,
            "-o",
            str(dest_file),
        ]
        token_str = str(min_tokens)
        if language in ANTLR_LANGUAGE:
            cmd = [
                *base_cmd,
                "-antlr",
                "|".join(exts),
                "-w",
                "2",
                "-t",
                token_str,
                "-ccfsw",
                "set",
            ]
        else:
            cmd = [*base_cmd, "-w", "2", "-t", token_str, "-ccfsw", "set"]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if log is not None:
            if result.stdout:
                log.write(result.stdout)
            if result.stderr:
                log.write(result.stderr)

        json_dest_dir = project_root / "dest/clones_json" / name / commit_hash
        json_dest_dir.mkdir(parents=True, exist_ok=True)
        json_dest_file = json_dest_dir / f"{language}.json"
        cmd = [
            str(CCFINDERSWPARSER),
            "-i",
            str(f"{dest_file}_ccfsw.txt"),
            "-o",
            str(json_dest_file),
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if log is not None:
            if result.stdout:
                log.write(result.stdout)
            if result.stderr:
                log.write(result.stderr)
        elapsed = time.perf_counter() - start_time
        _write_status(
            "  Clone detection finished: "
            f"commit={commit_hash[:7]} language={language} "
            f"elapsed={_format_elapsed(elapsed)}",
            log=log,
        )
        return elapsed
    except Exception as e:
        if log is not None and hasattr(e, "stdout") and e.stdout:
            log.write(e.stdout)
        if log is not None and hasattr(e, "stderr") and e.stderr:
            log.write(e.stderr)
        logger.exception("CCFinderの実行に失敗しました．")
        raise RuntimeError(
            f"CCFinderSW failed for {name} {commit_hash} {language}"
        ) from e


def collect_datas_of_repo(
    project: dict,
    apply_import_filter: bool = APPLY_IMPORT_FILTER,
    min_tokens: int = 50,
    log=None,
) -> None:
    """対象コミットに対してコードクローンと変更行情報を収集する。"""
    url = project["URL"]
    # リポジトリの識別子とプロジェクトディレクトリの設定
    name = url.split("/")[-2] + "." + url.split("/")[-1]
    logger.info("--------------------------------")
    logger.info(name)
    logger.info("--------------------------------")
    project_dir = project_root / "dest/projects" / name
    analyzed_commits_path = project_root / "dest/analyzed_commits" / f"{name}.json"

    # 言語ごとの拡張子一覧の取得
    exts = get_exts(project_dir)
    languages = project["languages"].keys()
    # GitPythonのインスタンスの作成(分析に便利!)
    git_repo = git.Repo(str(project_dir))
    with open(analyzed_commits_path, "r") as f:
        analyzed_commit_hashes = json.load(f)
    hcommit = git_repo.commit(analyzed_commit_hashes[0])
    total_commits = len(analyzed_commit_hashes)
    try:
        prev_commit = hcommit
        detection_count = 0
        detection_elapsed_total = 0.0
        for commit_idx, commit_hash in enumerate(analyzed_commit_hashes, 1):
            missing_languages = []
            for language in languages:
                clones_json = (
                    project_root
                    / "dest/clones_json"
                    / name
                    / commit_hash
                    / f"{language}.json"
                )
                if not clones_json.exists():
                    missing_languages.append(language)
            if missing_languages:
                if (
                    commit_idx == 1
                    or commit_idx % 10 == 0
                    or commit_idx == total_commits
                ):
                    logger.info(
                        "  commit progress: %d/%d (checkout %s...)",
                        commit_idx,
                        total_commits,
                        commit_hash[:7],
                    )
                git_repo.git.checkout("-f", commit_hash)

                if apply_import_filter:
                    # import行フィルタの適用
                    apply_filter(project_dir, languages, exts)

                for language in missing_languages:
                    detection_elapsed_total += detect_cc(
                        project_dir,
                        name,
                        language,
                        commit_hash,
                        exts[language],
                        min_tokens=min_tokens,
                        log=log,
                    )
                    detection_count += 1
            else:
                if (
                    commit_idx == 1
                    or commit_idx % 10 == 0
                    or commit_idx == total_commits
                ):
                    logger.info(
                        "  commit progress: %d/%d (skip %s, already detected)",
                        commit_idx,
                        total_commits,
                        commit_hash[:7],
                    )
            if commit_hash == hcommit.hexsha:
                continue
            commit = git_repo.commit(commit_hash)
            moving_lines_file = (
                project_root
                / "dest/moving_lines"
                / name
                / f"{commit.hexsha}-{prev_commit.hexsha}.json"
            )
            if not moving_lines_file.exists():
                # 修正を保存
                find_moving_lines(commit, prev_commit, name)
            prev_commit = commit
        if detection_count:
            _write_status(
                "  Clone detection total time: "
                f"{_format_elapsed(detection_elapsed_total)} "
                f"({detection_count} runs)",
                log=log,
            )
        else:
            _write_status(
                "  Clone detection total time: 0.0s (all results already cached)",
                log=log,
            )
    except Exception as e:
        logger.exception("collect_datas_of_repo failed for %s", name)
        raise RuntimeError(f"collect_datas_of_repo failed for {name}") from e
    finally:
        logger.info("checkout to latest commit...")
        git_repo.git.checkout("-f", hcommit.hexsha)
