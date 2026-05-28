import json
from pathlib import Path
import sys
import git

def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

from modules.util import get_codeclones_classified_by_type
from modules.util import calculate_loc
from modules.util import FileMapper
import modules.github_linguist


def analyze_repo(project: dict):
    url = project["URL"]
    name = url.split("/")[-2] + "." + url.split("/")[-1]
    workdir = project_root / "dest/projects" / name
    git_repo = git.Repo(workdir)
    hcommit = git_repo.head.commit.hexsha
    try:
        with open(project_root / "dest/analyzed_commits" / f"{name}.json", "r") as f:
            analyzed_commits = json.load(f)
        first_commit = analyzed_commits[0]
        languages = project["languages"]
        result = {}
        for language in languages:
            first_commit_ccfsw_file = project_root / "dest/clones_json" / name / first_commit / f"{language}.json"
            with open(first_commit_ccfsw_file, "r") as f:
                project_ccfsw_data = json.load(f)
            file_mapper = FileMapper(project_ccfsw_data["file_data"], str(workdir))
            clonesets = get_codeclones_classified_by_type(project, language)
            codebases = project["languages"][language].keys()
            file_dict = {}
            # calculate_loc の結果をキャッシュして同一ファイルへの重複 I/O を回避
            _loc_cache: dict[str, int] = {}
            for file_data in project_ccfsw_data["file_data"]:
                file_path = file_mapper.get_file_path(file_data["file_id"])
                for codebase in codebases:
                    if file_path.startswith(codebase):
                        break
                else:
                    continue
                abs_path = str(workdir / file_path)
                if abs_path not in _loc_cache:
                    _loc_cache[abs_path] = calculate_loc(abs_path)
                loc = _loc_cache[abs_path]
                if "test" in file_path.lower():
                    for mode in ("within-testing", "across-testing", "within-utility", "across-utility"):
                        file_dict.setdefault(mode, {})
                        file_dict[mode][file_path] = [False] * loc
                else:
                    for mode in ("within-production", "across-production", "within-utility", "across-utility"):
                        file_dict.setdefault(mode, {})
                        file_dict[mode][file_path] = [False] * loc
            result_lang = {}
            for mode in clonesets.keys():
                for _clone_id, fragments in clonesets[mode].items():
                    for fragment in fragments:
                        file_path = fragment["file_path"]
                        for line in range(int(fragment["start_line"])-1, int(fragment["end_line"])):
                            file_dict[mode][file_path][line] = True

                total = 0
                clone = 0
                for file_path, line_flags in file_dict.get(mode, {}).items():
                    total += len(line_flags)
                    clone += sum(line_flags)
                result_lang[mode] = clone / total if total > 0 else 0
            result[language] = result_lang
        return result
    finally:
        git_repo.git.checkout(hcommit)
