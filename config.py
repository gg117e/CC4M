# プロジェクトルートのPathを作成する．
# 設定ファイルではないので触らない．
from pathlib import Path

project_root = Path(__file__).parent

# =============================================================================
# データディレクトリ設定
# =============================================================================
# dest/ 配下のサブディレクトリパス定数
# 全モジュールはこれらの定数を使用し、ハードコードパスを避ける

DEST_ROOT = project_root / "dest"

# クローン検出結果（CCFinderSW出力をパースしたCSV）
DEST_CSV = DEST_ROOT / "csv"

# サービス情報（JSON形式のマイクロサービスマッピング）
DEST_SERVICES_JSON = DEST_ROOT / "services_json"

# メタデータ付与済みフラグメント
DEST_ENRICHED_FRAGMENTS = DEST_ROOT / "enriched_fragments"

# 可視化用散布図データ（ペア展開済み）
DEST_SCATTER = DEST_ROOT / "scatter"

# クローンメトリクス（サービス/クローンセット/ファイル単位の統計）
DEST_CLONE_METRICS = DEST_ROOT / "clone_metrics"

# プロジェクトリポジトリ（cloneしたソースコード）
DEST_PROJECTS = DEST_ROOT / "projects"

# 分析パラメータ（検出設定の記録）
DEST_ANALYSIS_PARAMS = DEST_ROOT / "analysis_params"

# 一時ディレクトリ（静的ファイル、no_importsフィルタ結果等）
DEST_TEMP = DEST_ROOT / "temp"
DEST_TEMP_STATIC = DEST_TEMP / "static"
DEST_TEMP_NO_IMPORTS = DEST_TEMP / "no_imports"

# レガシー互換: clone_analysis/repo 構造
DEST_CLONE_ANALYSIS = DEST_ROOT / "clone_analysis"

# =============================================================================
# データセット設定
# =============================================================================

"""
    元のデータセット：
        選別前のデータセットのパスを記入してください．
        ヘッダーが存在しており，"URL"列にGitHubのURLが記載されている,';'区切りのCSVファイルに対応しています．
"""
BASED_DATASET = project_root / "dataset/Filtered.csv"

"""
    選別後のデータセット（コミット条件適用前）：
        コードベースを持つサービスが複数あるプロジェクトのみを選別したデータセットに対応しています．
        identify_microservice -> map_file -> select_projectの順番で実行することでも作成できます．
"""
SELECTED_DATASET_CANDIDATES = project_root / "dest/selected_projects_candidates.json"

"""
    コミット条件を適用した最終データセット：
        determine_analyzed_commits で SELECTED_DATASET_CANDIDATES からフィルタした結果を保存します．
"""
SELECTED_DATASET = project_root / "dataset/selected_projects.json"

# CCFinderSWのパス
CCFINDERSW_JAR = project_root / "lib/CCFinderSW-1.0/lib/CCFinderSW-1.0.jar"

# CCFinderSW Parserのパス
CCFINDERSWPARSER = (
    project_root / "lib/ccfindersw-parser/target/release/ccfindersw-parser"
)

# CCFinderSWのJava実行設定
# 例: "16G", "8G", "1024M"
CCFINDERSW_JAVA_XMX = "20G"
CCFINDERSW_JAVA_XSS = "512m"

# 対象のプログラミング言語
TARGET_PROGRAMING_LANGUAGES = (
    "Java",
    "Python",
    "JavaScript",
    "Go",
    "PHP",
    "TypeScript",
    "Rust",
    "C++",
    "C#",
    "Ruby",
    "Scala",
    "C",
)

# ANTRLから構文定義記述を抽出してCodeCloneを検出する言語
ANTLR_LANGUAGE = ("JavaScript", "TypeScript", "Rust", "C++", "C")

"""
    分析するコミットの決め方を設定します．
    tag: タグがついているコミットを分析する．
    frequency: ANALYSIS_FREQUENCYで設定したコミット区切りで分析する．
    merge_commit: デフォルトブランチのマージコミットを分析する．
"""
ANALYSIS_METHOD = "merge_commit"

# 何コミット区切りで分析するか
ANALYSIS_FREQUENCY = 1

# リポジトリマイニングするコミット数（プロジェクト選定条件に使用）
SEARCH_DEPTH = -1

# 分析対象に含めるコミット数の最大値（-1 の場合は無制限）
# SEARCH_DEPTHとは独立した上限として適用されます。
MAX_ANALYZED_COMMITS = -1

# 分析対象のコミット上限日時（JST）。None の場合は制限なし。
# 例: "2024-03-31 23:59:59"
ANALYSIS_UNTIL = "2026-01-01 00:00:00"

# import 行フィルタを有効にするか
APPLY_IMPORT_FILTER = True
