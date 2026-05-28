# 必要なライブラリをインポート
from pathlib import Path
import os
import git
import shutil


def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


# プロジェクトのルートディレクトリを取得
project_root = _find_repo_root(Path(__file__).resolve())


def clone_repo(url: str):
    """
    指定されたURLからGitリポジトリをクローンする関数
    
    Args:
        url (str): クローンするGitリポジトリのURL
    """
    # リポジトリ名をURLから抽出（owner/repo形式）
    name = url.split('/')[-2] + '.' + url.split('/')[-1]
    print(f"Cloning {url}...")
    # クローン先のディレクトリを作成
    os.makedirs(project_root / "dest/projects", exist_ok=True)
    # リポジトリをクローン
    shutil.rmtree(project_root / "dest/projects" / name, ignore_errors=True)
    git.Repo.clone_from(url, project_root / "dest/projects" / name)
