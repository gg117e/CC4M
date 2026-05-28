import json
import sys
import traceback
from pathlib import Path

import git


def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

from config import SELECTED_DATASET  # noqa: E402
import modules.CLAIM.dc_choice as dc_choice  # noqa: E402
import modules.CLAIM.ms_detection as ms_detection  # noqa: E402
import modules.github_linguist  # noqa: E402
import modules.map_file  # noqa: E402


def _load_dataset() -> list[dict]:
    with open(SELECTED_DATASET, "r") as f:
        return json.load(f)


def _load_target_commit(name: str) -> str | None:
    analyzed_commits_path = project_root / "dest/analyzed_commits" / f"{name}.json"
    if not analyzed_commits_path.exists():
        return None
    with open(analyzed_commits_path, "r") as f:
        commits = json.load(f)
    return commits[0] if commits else None


def _ensure_repo(url: str, workdir: Path) -> git.Repo:
    if workdir.exists():
        repo = git.Repo(workdir)
        try:
            repo.git.fetch("--all", "--tags")
        except git.exc.GitCommandError:
            pass
        return repo
    workdir.parent.mkdir(parents=True, exist_ok=True)
    return git.Repo.clone_from(url, workdir)


def _write_linguist(name: str, result: dict) -> None:
    result_dir = project_root / "dest/github_linguist"
    result_dir.mkdir(parents=True, exist_ok=True)
    result_file = result_dir / f"{name}.json"
    with open(result_file, "w") as f:
        json.dump(result, f, indent=4)


def _refresh_project(project: dict) -> None:
    url = project["URL"]
    name = url.split("/")[-2] + "." + url.split("/")[-1]
    target_commit = _load_target_commit(name)
    if not target_commit:
        print(f"[skip] analyzed commits not found: {name}")
        return

    workdir = project_root / "dest/projects" / name
    repo = _ensure_repo(url, workdir)

    if (workdir / ".git" / "shallow").exists():
        try:
            repo.git.fetch("--unshallow")
        except git.exc.GitCommandError:
            pass

    try:
        dc_choice_results = dc_choice.analyze_repo(name, str(workdir))
        dc_choice.save_results(url, dc_choice_results)
        ms_results = ms_detection.analyze_repo(name, str(workdir))
        ms_detection.save_results(url, ms_results)
    except Exception:
        print(traceback.format_exc())
        return
    finally:
        repo.git.checkout(target_commit, force=True)

    linguist_result = modules.github_linguist.run_github_linguist(str(workdir))
    _write_linguist(name, linguist_result)
    modules.map_file.map_files(url, target_commit=target_commit)


def main() -> int:
    dataset = _load_dataset()
    for project in dataset:
        _refresh_project(project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
