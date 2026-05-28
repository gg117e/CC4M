from pathlib import Path
import sys


def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

import modules.identify_microservice
import modules.map_file
import modules.select_project


if __name__ == "__main__":
    modules.identify_microservice.analyze_dataset()
    modules.map_file.main()
    modules.select_project.main()
