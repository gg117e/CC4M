from pathlib import Path
import ast
import csv
import json
import sys
import os

import git

def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


# プロジェクトのルートディレクトリを設定
project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))
from config import TARGET_PROGRAMING_LANGUAGES, BASED_DATASET
import modules.claim_parser


def _find_commit_index(workdir: Path, target_commit: str) -> int | None:
    git_repo = git.Repo(workdir)
    for index, commit in enumerate(git_repo.iter_commits(), start=1):
        if commit.hexsha == target_commit:
            return index
    return None


def _select_chunk(rows: list[dict], target_commit: str | None, workdir: Path) -> dict:
    if not rows:
        raise FileNotFoundError("dest/ms_detection に有効な行がありません。")
    if target_commit is None:
        return rows[0]

    target_index = _find_commit_index(workdir, target_commit)
    if target_index is None:
        print(f"[warn] commit not found in repo history: {target_commit}")
        return rows[0]

    for row in rows:
        try:
            chunks = ast.literal_eval(row["CHUNKS_N"])
        except (SyntaxError, ValueError):
            continue
        for start, end in chunks:
            if start <= target_index <= end:
                return row

    print(f"[warn] commit not covered by chunks: {target_commit}")
    return rows[0]


def map_files(url: str, target_commit: str | None = None) -> dict:
    """
    指定されたURLに対応するリポジトリのファイルマッピングを作成します。
    マイクロサービスとコンテナの情報を解析し、各マイクロサービスに関連するファイルを言語ごとに分類します。
    target_commit が指定されている場合は、そのコミットに対応する結果を利用します。
    
    Args:
        url: GitHubリポジトリのURL
        
    Returns:
        マイクロサービスとコンテナの情報を含む辞書。
        各マイクロサービスには、ビルド情報、信頼度、関連するファイル（言語ごとに分類）が含まれます。
        各コンテナには、イメージ名とビルド情報が含まれます。
        
    Raises:
        FileNotFoundError: 必要なファイルが見つからない場合
    """
    # URLからリポジトリ名を抽出
    name = url.split('/')[-2] + '.' + url.split('/')[-1]
    workdir = project_root / "dest/projects" / name
    if target_commit is not None and not workdir.exists():
        raise FileNotFoundError(f"Repository not found: {workdir}")
    # マイクロサービス検出結果のファイルパス
    target = project_root / "dest/ms_detection" / f"{name}.csv"

    try:
        # マイクロサービスとコンテナの情報を読み込む
        with open(target, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            row = _select_chunk(rows, target_commit, workdir)
            uSs = modules.claim_parser.parse_uSs(row["uSs"])
            containers = modules.claim_parser.parse_containers(row["CONTAINERS"])

        # GitHub Linguistの結果を読み込む
        target = project_root / "dest/github_linguist" / f"{name}.json"
        with open(target, "r") as f:
            linguist_result = json.load(f)
        os.remove(target)

        result = {}
        # マイクロサービスの情報を処理
        if uSs is not None:
            for uS in uSs:
                result[uS["name"]] = {
                    "type": "microservice",
                    "build": uS["build"],
                    "confidence": uS["confidence"],
                    "files": {}
                }

        # 言語ごとのファイルをマイクロサービスに割り当てる
        for language in linguist_result.keys():
            # 対象外の言語はスキップ
            if language not in TARGET_PROGRAMING_LANGUAGES:
                continue
            # 各ファイルを処理
            for file in linguist_result[language]["files"]:
                # 各マイクロサービスに対して処理
                for microservice in result.keys():
                    context = result[microservice]["build"]["context"]
                    # コンテキストが無効な場合はスキップ
                    if context is None or context == ".":
                        continue
                    # ファイルがマイクロサービスのコンテキスト内にある場合
                    if file.startswith(context):
                        # 言語ごとのファイルリストを初期化（必要に応じて）
                        if language not in result[microservice]["files"].keys():
                            result[microservice]["files"][language] = []
                        # ファイルを追加
                        result[microservice]["files"][language].append(file)
        
        # コンテナの情報を追加
        if containers is not None:
            for container in containers:
                result[container["container_name"]] = {
                    "type": "container",
                    "image": container["image"],
                    "build": container["build"],
                }

        return result
        
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {target}")


def main():
    """
    メイン関数。
    Filtered.csvファイルからリポジトリのURLを読み込み、
    各リポジトリに対してファイルマッピングを作成し、結果をJSONファイルとして保存します。
    """
    # データセットファイルを開く
    dataset_file = BASED_DATASET
    with open(dataset_file, "r") as f:
        reader = csv.DictReader(f, delimiter=';')
        # 各行（リポジトリ）を処理
        for row in reader:
            try:
                # ファイルマッピングを作成
                result = map_files(row["URL"])
                # リポジトリ名を抽出
                name = row["URL"].split('/')[-2] + '.' + row["URL"].split('/')[-1]
                # 結果をJSONファイルとして保存
                dest_dir = project_root / "dest/map"
                dest_dir.mkdir(parents=True, exist_ok=True)
                with open(dest_dir / f"{name}.json", "w") as f:
                    json.dump(result, f, indent=4)
            except FileNotFoundError:
                # ファイルが見つからない場合はエラーメッセージを表示して続行
                print(f"File not found: {row['URL']}")
                continue


if __name__ == "__main__":
    main()
