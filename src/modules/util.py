import sys
import csv
import logging
import re
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

logger = logging.getLogger(__name__)


class FileMapper:
    def __init__(self, files: list, project_dir: str) -> None:
        self.id_to_path = {}
        self.path_to_id = {}
        self.file_loc = {}
        for file in files:
            file_id = int(file["file_id"])
            path = str(file["file_path"]).replace(project_dir + "/", "")
            self.id_to_path[file_id] = path
            self.path_to_id[path] = file_id
            self.file_loc[path] = int(file["loc"])

    def get_file_id(self, path: str) -> int:
        return self.path_to_id[path]

    def get_file_path(self, file_id: int) -> str:
        return self.id_to_path[file_id]

    def get_file_loc(self, path: str) -> int:
        if path not in self.file_loc.keys():
            return -1
        return self.file_loc[path]


_TEST_PATH_INDICATORS = (
    "/test/",
    "/tests/",
    "/test_",
    "test_",
    "_test.",
    ".test.",
    "/spec/",
    "/specs/",
    "_spec.",
    ".spec.",
    "/__tests__/",
)

_CONFIG_NAMES = {
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "makefile",
    ".env",
    "tsconfig.json",
    "package.json",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "pom.xml",
    "build.gradle",
    "build.sbt",
    "cargo.toml",
    "go.mod",
    ".eslintrc",
    ".prettierrc",
    ".babelrc",
    "jest.config.js",
    "webpack.config.js",
    "rollup.config.js",
    "vite.config.ts",
    "nginx.conf",
    "requirements.txt",
    "gemfile",
}

_CONFIG_EXTENSIONS = {".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf"}
_CONFIG_DIRS = ("/config/", "/configs/", "/.github/", "/.circleci/")

_DATA_PATH_INDICATORS = (
    "/entity/",
    "/entities/",
    "/dto/",
    "/proto/",
    "/migration/",
    "/migrations/",
    "/seed/",
    "/seeds/",
    "/fixture/",
    "/fixtures/",
)

_DATA_EXTENSIONS = {".sql", ".graphql", ".proto", ".avsc"}

def _extract_extension(name: str) -> str:
    return "." + name.rsplit(".", 1)[-1] if "." in name else ""

def _get_file_type_from_path(file_path: str) -> str:
    lower = file_path.lower().replace("\\", "/")
    name = lower.rsplit("/", 1)[-1] if "/" in lower else lower

    if any(ind in lower for ind in _TEST_PATH_INDICATORS):
        return "test"

    if name in _CONFIG_NAMES:
        return "config"

    ext = _extract_extension(name)
    if ext in _CONFIG_EXTENSIONS:
        return "config"

    if any(d in lower for d in _CONFIG_DIRS):
        return "config"

    if any(ind in lower for ind in _DATA_PATH_INDICATORS):
        return "data"

    if ext in _DATA_EXTENSIONS:
        return "data"

    return "logic"

def get_file_type(
    file_path: str,
    *,
    language: str | None = None,
) -> str:
    """Classify file type with staged rules: path, then extension."""
    path = str(file_path or "")

    # Stage 1: strong path signal
    path_type = _get_file_type_from_path(path)
    if path_type != "logic":
        return path_type

    # Stage 2: extension fallback
    _ = language

    lower_name = path.lower().replace("\\", "/").rsplit("/", 1)[-1]
    ext = _extract_extension(lower_name)

    if ext in _CONFIG_EXTENSIONS:
        return "config"
    if ext in _DATA_EXTENSIONS:
        return "data"

    return "logic"


def calculate_loc(file_path: str) -> int:
    with open(file_path, "r") as f:
        return len(f.readlines())


def get_codeclones_classified_by_type(project: dict, language: str) -> dict:
    """
    クローンをコード種別・配置関係ごとに分類して返す
    """
    name = project["URL"].split("/")[-2] + "." + project["URL"].split("/")[-1]
    temp = {}
    with open(project_root / "dest/csv" / name / f"{language}.csv", "r") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            clone_id = row["clone_id"]
            temp.setdefault(clone_id, [])
            temp[clone_id].append(row)

    clonesets = {
        "within-testing": {},
        "within-production": {},
        "within-utility": {},
        "across-testing": {},
        "across-production": {},
        "across-utility": {},
    }

    codebases = project["languages"][language]
    for clone_id, fragments in temp.items():
        is_testing = False
        is_production = False
        for row in fragments:
            path = row["file_path"]
            if "test" in path.lower():
                is_testing = True
            else:
                is_production = True
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
            range_name = "across"
        else:
            continue

        if is_testing and not is_production:
            code_type = "testing"
        elif is_production and not is_testing:
            code_type = "production"
        else:
            code_type = "utility"

        key = f"{range_name}-{code_type}"
        clonesets[key][clone_id] = service_fragments

    return clonesets
