import sys
from pathlib import Path
import json

def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

import modules.github_linguist
import modules.util

if __name__ == "__main__":
    dataset_file = project_root / "dataset/selected_projects.json"
    with open(dataset_file, "r") as f:
        dataset = json.load(f)
    production_languages_total_loc = {}
    testing_languages_total_loc = {}
    languages_total_service_count = {}
    for project in dataset:
        url = project["URL"]
        name = url.split("/")[-2] + "." + url.split("/")[-1]
        workdir = project_root / "dest/projects" / name
        languages = project["languages"].keys()
        github_linguist_result = modules.github_linguist.run_github_linguist(workdir)
        print("--------------------------------")
        print(name)
        print("--------------------------------")
        for language in languages:
            production_result = {"total_loc": 0}
            testing_result = {"total_loc": 0}
            for service in project["languages"][language]: 
                production_result[service] = 0
                testing_result[service] = 0
            for file in github_linguist_result[language]["files"]:
                if "test" in file.lower():
                    for service in project["languages"][language]:
                        if file.startswith(service):
                            testing_result["total_loc"] += modules.util.calculate_loc(workdir / file)
                            testing_result[service] += modules.util.calculate_loc(workdir / file)
                else:
                    for service in project["languages"][language]:
                        if file.startswith(service):
                            production_result["total_loc"] += modules.util.calculate_loc(workdir / file)
                            production_result[service] += modules.util.calculate_loc(workdir / file)
            if language not in production_languages_total_loc:
                production_languages_total_loc[language] = 0
            if language not in testing_languages_total_loc:
                testing_languages_total_loc[language] = 0
            if language not in languages_total_service_count:
                languages_total_service_count[language] = 0
            production_languages_total_loc[language] += production_result["total_loc"]
            testing_languages_total_loc[language] += testing_result["total_loc"]
            languages_total_service_count[language] += len(project["languages"][language])
            print(f"[{language} - production] {production_result['total_loc']}")
            for service in production_result:
                print(f"| {service} | {production_result[service]} |")
            print(f"[{language} - testing] {testing_result['total_loc']}")
            for service in testing_result:
                print(f"| {service} | {testing_result[service]} |")
    print(f"production_languages_total_loc: {production_languages_total_loc}")
    print(f"testing_languages_total_loc: {testing_languages_total_loc}")
    print(f"languages_total_service_count: {languages_total_service_count}")
