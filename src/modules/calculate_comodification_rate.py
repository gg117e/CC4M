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

from modules.util import get_codeclones_classified_by_type


def analyze_repo(project):
    languages = project["languages"]
    result = {}
    for language in languages:
        clonesets = get_codeclones_classified_by_type(project, language)
        result_lang = {}
        for mode in clonesets.keys(): 
            result_lang.setdefault(mode, {"count": 0, "comodification_count": 0})
            for clone_id, fragments in clonesets[mode].items():
                result_lang[mode]["count"] += 1
                modifications = {}
                for fragment in fragments:
                    m_list = json.loads(fragment["modification"])
                    for m in m_list:
                        modifications.setdefault(m["commit"], [])
                        modifications[m["commit"]].append(m["type"])
                for commit, types in modifications.items():
                    if types.count("modified") >= 2:
                        result_lang[mode]["comodification_count"] += 1
                        break
        result[language] = result_lang
    return result
