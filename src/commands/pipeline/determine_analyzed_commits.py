import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import git

def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

from config import (
    SELECTED_DATASET,
    SELECTED_DATASET_CANDIDATES,
    ANALYSIS_FREQUENCY,
    SEARCH_DEPTH,
    ANALYSIS_METHOD,
    ANALYSIS_UNTIL,
    MAX_ANALYZED_COMMITS,
)
import modules.clone_repo


JST = timezone(timedelta(hours=9))


def _parse_cutoff_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=JST)
        return parsed.astimezone(JST)
    except ValueError:
        raise ValueError("ANALYSIS_UNTIL must be ISO-like, e.g. '2024-03-31 23:59:59'")


def _is_before_cutoff(commit: git.Commit, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    committed_jst = commit.committed_datetime.astimezone(JST)
    return committed_jst <= cutoff


def _get_remote_default_ref(git_repo: git.Repo, remote_name: str = "origin") -> git.Reference | None:
    """Return the remote default branch ref (e.g. origin/main)."""
    if remote_name not in git_repo.remotes:
        return None
    try:
        head_ref = git_repo.refs[f"{remote_name}/HEAD"]
        return head_ref.reference
    except (IndexError, AttributeError, KeyError):
        return None


def _apply_max_commits(commits: list[str]) -> list[str]:
    if MAX_ANALYZED_COMMITS is None or MAX_ANALYZED_COMMITS == -1:
        return commits
    return commits[:MAX_ANALYZED_COMMITS]


def determine_by_frequency(workdir: Path) -> list[str]:
    """Pick commits at a fixed frequency from the remote default branch."""
    git_repo = git.Repo(str(workdir))
    target_commits: list[str] = []
    cutoff = _parse_cutoff_datetime(ANALYSIS_UNTIL)
    target_ref = _get_remote_default_ref(git_repo)
    commits = list(git_repo.iter_commits(target_ref)) if target_ref else list(git_repo.iter_commits())
    filtered_commits = [commit for commit in commits if _is_before_cutoff(commit, cutoff)]
    for count, commit in enumerate(filtered_commits):
        if SEARCH_DEPTH != -1 and count > SEARCH_DEPTH:
            break
        if count % ANALYSIS_FREQUENCY == 0:
            target_commits.append(commit.hexsha)
    return _apply_max_commits(target_commits)


def determine_by_tag(workdir: Path) -> list[str]:
    """Pick commits corresponding to the newest tags."""
    git_repo = git.Repo(str(workdir))
    cutoff = _parse_cutoff_datetime(ANALYSIS_UNTIL)
    tags = git_repo.tags
    tag_list = [
        {
            "tag": tag.name,
            "sha": tag.commit.hexsha,
            "date": tag.commit.committed_datetime,
            "commit": tag.commit,
        }
        for tag in tags
    ]
    tag_list = [tag for tag in tag_list if _is_before_cutoff(tag["commit"], cutoff)]
    tag_list.sort(key=lambda tag: tag["date"], reverse=True)

    target_commits: list[str] = []
    for count, tag in enumerate(tag_list):
        if count >= SEARCH_DEPTH:
            break
        target_commits.append(tag["sha"])
    return _apply_max_commits(target_commits)


def determine_analyzed_commits_by_mergecommits(workdir: Path) -> list[str]:
    """Pick newest merge commits from the remote default branch."""
    git_repo = git.Repo(str(workdir))
    cutoff = _parse_cutoff_datetime(ANALYSIS_UNTIL)
    try:
        target = _get_remote_default_ref(git_repo)
        if target is None:
            return []
        merge_commits_newest_first = [
            commit for commit in git_repo.iter_commits(target)
            if len(commit.parents) >= 2 and _is_before_cutoff(commit, cutoff)
        ]
        if SEARCH_DEPTH != -1:
            merge_commits_newest_first = merge_commits_newest_first[:SEARCH_DEPTH]
        return _apply_max_commits([commit.hexsha for commit in merge_commits_newest_first])
    except (IndexError, AttributeError, KeyError):
        return []


if __name__ == "__main__":
    with open(SELECTED_DATASET_CANDIDATES, "r") as f:
        dataset = json.load(f)
    analyzed_commits_dir = project_root / "dest/analyzed_commits"
    analyzed_commits_dir.mkdir(parents=True, exist_ok=True)
    target_projects = []
    for project in dataset:
        url = project["URL"]
        name = url.split("/")[-2] + "." + url.split("/")[-1]
        workdir = project_root / "dest/projects" / name
        modules.clone_repo.clone_repo(url)
        if ANALYSIS_METHOD == "frequency":
            target_commits = determine_by_frequency(workdir)
        elif ANALYSIS_METHOD == "tag":
            target_commits = determine_by_tag(workdir)
        elif ANALYSIS_METHOD == "merge_commit":
            target_commits = determine_analyzed_commits_by_mergecommits(workdir)
        # Drop projects that have no target commits (e.g., default branch not found).
        if not target_commits:
            continue
        target_projects.append(project)
        with open(analyzed_commits_dir / f"{name}.json", "w") as f:
            json.dump(target_commits, f)

    Path(SELECTED_DATASET).parent.mkdir(parents=True, exist_ok=True)
    with open(SELECTED_DATASET, "w") as f:
        json.dump(target_projects, f)
    print(f"選択されたプロジェクト数: {len(target_projects)}")
