import csv
import json
from pathlib import Path
import sys

def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


# プロジェクトのルートディレクトリを設定
project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

from config import BASED_DATASET, SELECTED_DATASET_CANDIDATES


def check_project(url: str) -> tuple[bool, dict]:
    """
    指定されたURLのプロジェクトが条件を満たすかチェックします。
    複数の言語でマイクロサービスが実装されているプロジェクトを特定します。
    
    Args:
        url: GitHubリポジトリのURL
        
    Returns:
        (bool, dict): 条件を満たすかどうかのブール値と、言語ごとのマイクロサービス情報を含む辞書
    """
    # URLからリポジトリ名を抽出
    name = url.split('/')[-2] + '.' + url.split('/')[-1]
    # マッピングファイルのパス
    target_map_file = project_root / "dest/map" / f"{name}.json"
    # GitHubのリポジトリが存在しない場合，mapファイルが存在しないのでFalseを返す
    if not target_map_file.exists():
        return False, {}
    # マッピングファイルを読み込む
    with open(target_map_file, "r") as f:
        map_data = json.load(f)
        # 各マイクロサービスのコンテキストと言語のペアを収集
        srcs = set()
        for name in map_data.keys():
            service = map_data[name]
            # コンテナはスキップ
            if service["type"] == "container":
                continue
            # ファイルがない場合はスキップ
            if len(service["files"].keys()) == 0:
                continue
            # ビルド情報がない場合はスキップ
            if service["build"] is None:
                continue
            # コンテキストを取得
            context = service["build"]["context"]
            # 各言語のファイルを処理
            for language in service["files"].keys():
                srcs.add((context, language))
        # 言語ごとのマイクロサービス数をカウント
        count_services = {}
        for src in srcs:
            context, language = src
            if language not in count_services:
                count_services[language] = 0
            count_services[language] += 1
        # 2つ以上のマイクロサービスがある言語を特定
        target_languages = []
        for language in count_services.keys():
            if count_services[language] >= 2:
                target_languages.append(language)
        # 条件を満たす言語がない場合はFalseを返す
        if len(target_languages) == 0:
            return False, {}
        # 結果の構造を作成
        result = {"languages": {}}
        for language in target_languages:
            result["languages"][language] = {}
            # 各マイクロサービスを処理
            for name in map_data.keys():
                service = map_data[name]
                # ビルド情報がない場合はスキップ
                if service["build"] is None:
                    continue
                # コンテナはスキップ
                if service["type"] == "container":
                    continue
                # ファイルがない場合はスキップ
                if len(service["files"].keys()) == 0:
                    continue
                # コンテキストを取得
                context = service["build"]["context"]
                # 各言語のファイルを処理
                for l in service["files"].keys():
                    # 対象言語の場合のみ処理
                    if l == language:
                        if context not in result["languages"][language]:
                            result["languages"][language][context] = []
                        result["languages"][language][context].append(name)
        return True, result
                    

def main():
    """
    メイン関数。
    Filtered.csvファイルからリポジトリのURLを読み込み、
    条件を満たすプロジェクトを選択し、結果をJSONファイルとして保存します。
    """
    # データセットファイルを開く
    dataset_file = BASED_DATASET
    count = 0
    output = []
    # 各行（リポジトリ）を処理
    with open(dataset_file, "r") as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            url = row["URL"]
            # プロジェクトをチェック
            is_ok, result = check_project(url)            
            # 条件を満たす場合
            if is_ok:
                count += 1
                result["URL"] = url
                output.append(result)
    # 結果をJSONファイルとして保存
    Path(SELECTED_DATASET_CANDIDATES).parent.mkdir(parents=True, exist_ok=True)
    with open(SELECTED_DATASET_CANDIDATES, "w") as f:
        json.dump(output, f, indent=4)


if __name__ == "__main__":
    main()
