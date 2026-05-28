"""可視化モジュール用パス解決ユーティリティ.

config.py で定義されたパス定数を使用し、ハードコードを排除する。
プロジェクト/言語に応じた各種データファイルのパスを提供する。
"""

from pathlib import Path

# config.py からパス定数をインポート
import sys
_config_path = Path(__file__).resolve().parents[2]
if str(_config_path) not in sys.path:
    sys.path.insert(0, str(_config_path))

from config import (
    DEST_ROOT,
    DEST_CSV,
    DEST_SERVICES_JSON,
    DEST_ENRICHED_FRAGMENTS,
    DEST_SCATTER,
    DEST_CLONE_METRICS,
    DEST_PROJECTS,
    DEST_ANALYSIS_PARAMS,
    DEST_TEMP,
    DEST_TEMP_STATIC,
    DEST_TEMP_NO_IMPORTS,
    DEST_CLONE_ANALYSIS,
)

__all__ = [
    # パス定数（再エクスポート）
    "DEST_ROOT",
    "DEST_CSV",
    "DEST_SERVICES_JSON",
    "DEST_ENRICHED_FRAGMENTS",
    "DEST_SCATTER",
    "DEST_CLONE_METRICS",
    "DEST_PROJECTS",
    "DEST_ANALYSIS_PARAMS",
    "DEST_TEMP",
    "DEST_TEMP_STATIC",
    "DEST_TEMP_NO_IMPORTS",
    "DEST_CLONE_ANALYSIS",
    # 関数
    "get_scatter_csv_dir",
    "get_services_json_path",
    "get_enriched_csv_dir",
    "get_clone_metrics_path",
    "get_project_source_root",
    "get_analysis_params_path",
]


def get_scatter_csv_dir(project: str) -> Path:
    """プロジェクトの scatter CSV ディレクトリパスを取得する.

    Args:
        project: プロジェクト名 (owner.repo 形式).

    Returns:
        dest/scatter/{project}/csv のパス.
    """
    return DEST_SCATTER / project / "csv"


def get_services_json_path(project: str) -> Path:
    """プロジェクトの services.json パスを取得する.

    Args:
        project: プロジェクト名 (owner.repo 形式).

    Returns:
        dest/services_json/{project}.json のパス.
    """
    return DEST_SERVICES_JSON / f"{project}.json"


def get_enriched_csv_dir(project: str) -> Path:
    """プロジェクトの enriched_fragments ディレクトリパスを取得する.

    Args:
        project: プロジェクト名 (owner.repo 形式).

    Returns:
        dest/enriched_fragments/{project} のパス.
    """
    return DEST_ENRICHED_FRAGMENTS / project


def get_clone_metrics_path(project: str, language: str) -> Path:
    """プロジェクト/言語のクローンメトリクスJSONパスを取得する.

    Args:
        project: プロジェクト名 (owner.repo 形式).
        language: 言語名.

    Returns:
        dest/clone_metrics/{project}_{language}.json のパス.
    """
    return DEST_CLONE_METRICS / f"{project}_{language}.json"


def get_analysis_params_path(project: str) -> Path:
    """プロジェクトの分析パラメータJSONパスを取得する.

    Args:
        project: プロジェクト名 (owner.repo 形式).

    Returns:
        dest/analysis_params/{project}.json のパス.
    """
    return DEST_ANALYSIS_PARAMS / f"{project}.json"


def get_project_source_root(project: str) -> Path:
    """プロジェクトのソースコードルートディレクトリを取得する.

    以下の順序でディレクトリを探索し、最初に存在するものを返す:
    1. dest/temp/no_imports/{project} (TKS/import filterデータ)
    2. dest/temp/static/{project} (従来の静的データ)
    3. dest/clone_analysis/{project}/repo (レガシー構造)
    4. dest/projects/{project} (現在の標準的な場所)

    Args:
        project: プロジェクト名 (owner.repo 形式).

    Returns:
        存在するソースルートパス。どれも存在しない場合は no_imports パス。
    """
    # 優先順位に従って探索
    candidates = [
        DEST_TEMP_NO_IMPORTS / project,
        DEST_TEMP_STATIC / project,
        DEST_CLONE_ANALYSIS / project / "repo",
        DEST_PROJECTS / project,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # どれも存在しない場合は、no_imports を優先して返す
    return candidates[0]
