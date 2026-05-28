import subprocess
import json
import os
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
from config import TARGET_PROGRAMING_LANGUAGES


def run_github_linguist(target: str) -> dict:
    """
    GitHub Linguistを使用して指定されたディレクトリの言語構成を分析します．

    Args:
        target (str): 分析対象のディレクトリパス

    Returns:
        dict: 言語ごとの使用量を含むJSONデータ
    """
    # コマンドは環境によって書き換えてください．
    cmd = ["github-linguist", target, "--json", "--breakdown"]
    output = str(subprocess.run(cmd, capture_output=True, text=True).stdout).replace("\\n", "")
    return json.loads(output)


def get_exts(workdir: Path) -> dict:
    result = {}
    github_linguist_result = run_github_linguist(str(workdir))
    for language in github_linguist_result.keys():
        if language not in TARGET_PROGRAMING_LANGUAGES:
            continue
        exts = set()
        for file in github_linguist_result[language]["files"]:
            ext = os.path.splitext(file)[1].replace(".", "")
            if ext != "":
                exts.add(ext)
        result[language] = tuple(exts)
    return result
