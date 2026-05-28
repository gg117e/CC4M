import hashlib
import json
import logging
from pathlib import Path

from dash import html, dcc
import pandas as pd

from ..utils import get_local_snippet
from ..constants import DetectionMethod
from collections import Counter

logger = logging.getLogger(__name__)

def calculate_unique_pair_count_for_clone(clone_df):
    """クローンデータフレームに対してユニークペア数を計算する"""
    if clone_df is None or clone_df.empty:
        return 0

    # 重複除去のためのキーを作成
    df_temp = clone_df.copy()
    df_temp["clone_key"] = (
        df_temp["clone_id"].astype(str)
        + "|"
        + df_temp["file_path_x"].str.split("/").str[-1]
        + "|"
        + df_temp["start_line_x"].astype(str)
        + "-"
        + df_temp["end_line_x"].astype(str)
        + "|"
        + df_temp["file_path_y"].str.split("/").str[-1]
        + "|"
        + df_temp["start_line_y"].astype(str)
        + "-"
        + df_temp["end_line_y"].astype(str)
    )

    # coord_pair列が存在しない場合は作成
    if "coord_pair" not in df_temp.columns:
        df_temp["coord_pair"] = (
            df_temp["file_id_y"].astype(str) + "_" + df_temp["file_id_x"].astype(str)
        )

    # 重複除去して数をカウント
    return len(df_temp.drop_duplicates(subset=["coord_pair", "clone_key"]))


def calculate_cross_service_metrics(df):
    """クローンの多サービス跨り度を分析する"""
    if df is None or df.empty:
        return {}, 0, {}

    # 全サービス数を計算
    services_x = set(df["service_x"].unique())
    services_y = set(df["service_y"].unique())
    total_services = len(services_x.union(services_y))

    # 各クローンIDが跨るサービス数を計算 (groupby で効率化)
    clone_metrics = {}
    for clone_id, clone_rows in df.groupby("clone_id"):
        services_x = set(clone_rows["service_x"].unique())
        services_y = set(clone_rows["service_y"].unique())
        all_clone_services = services_x.union(services_y)

        # ユニークペア数を計算
        unique_pair_count = calculate_unique_pair_count_for_clone(clone_rows)

        # Co-modifiedペア数を計算
        comodified_count = 0
        if "comodified" in clone_rows.columns:
            comodified_count = len(
                clone_rows[clone_rows["comodified"].isin([1, True, "1", "True"])]
            )

        # Code Typeの内訳を計算
        code_types = Counter()
        is_mixed = False
        if "file_type_x" in clone_rows.columns and "file_type_y" in clone_rows.columns:
            # Mixed判定: Test vs Product (Test vs Non-Test)
            is_test_x = clone_rows["file_type_x"] == "test"
            is_test_y = clone_rows["file_type_y"] == "test"
            mixed_rows = clone_rows[is_test_x != is_test_y]

            if not mixed_rows.empty:
                is_mixed = True

            # 集計はx側をベースにする（代表値）
            code_types.update(clone_rows["file_type_x"])
        elif "file_type_x" in clone_rows.columns:
            code_types.update(clone_rows["file_type_x"])

        # Detection Method (もし混在している場合)
        methods = set()
        if "detection_method" in clone_rows.columns:
            methods.update(clone_rows["detection_method"].unique())
        elif "clone_type" in clone_rows.columns:  # fallback
            methods.update(clone_rows["clone_type"].unique())

        # inter_service_pairs の計算（カラム存在チェック付き）
        if "relation" in clone_rows.columns:
            inter_service_pairs = len(clone_rows[clone_rows["relation"] == "inter"])
        elif "clone_type" in clone_rows.columns:
            inter_service_pairs = len(clone_rows[clone_rows["clone_type"] == "inter"])
        elif "service_x" in clone_rows.columns and "service_y" in clone_rows.columns:
            inter_service_pairs = len(
                clone_rows[clone_rows["service_x"] != clone_rows["service_y"]]
            )
        else:
            inter_service_pairs = 0

        clone_metrics[clone_id] = {
            "service_count": len(all_clone_services),
            "services": list(all_clone_services),
            "pair_count": unique_pair_count,  # ユニークペア数を使用
            "total_pair_count": len(clone_rows),  # 元の重複含む数も保持
            "comodified_count": comodified_count,
            "code_types": dict(code_types),
            "is_mixed": is_mixed,
            "methods": list(methods),
            "inter_service_pairs": inter_service_pairs,
            "file_paths": list(
                set(
                    clone_rows["file_path_x"].tolist()
                    + clone_rows["file_path_y"].tolist()
                )
            ),
        }

    # サービス跨り度の分布
    service_count_distribution = Counter(
        [metrics["service_count"] for metrics in clone_metrics.values()]
    )

    return clone_metrics, total_services, service_count_distribution


def generate_cross_service_filter_options(clone_stats, sort_by="service_count"):
    """
    クローンIDごとの統計情報リストからフィルタリングオプションを生成.

    Args:
        clone_stats: list of dict containing clone statistics:
            - clone_id: クローンID
            - service_count: 跨るサービス数
            - code_type: コードタイプ (Data/Logic/Test/Config/Mixed)
            - comod_count: 同時修正されたペア数 (optional)
        sort_by: ソート基準 ("service_count" or "comod_count")

    Returns:
        ドロップダウンオプションのリスト
    """
    options = [{"label": "All", "value": "all"}]

    # ソート
    if sort_by == "comod_count":
        sorted_stats = sorted(
            clone_stats,
            key=lambda x: (-x.get("comod_count", 0), -x.get("service_count", 0)),
        )
    else:  # default: service_count
        sorted_stats = sorted(
            clone_stats,
            key=lambda x: (-x.get("service_count", 0), -x.get("comod_count", 0)),
        )

    for stat in sorted_stats:
        comod_count = stat.get("comod_count", 0)
        pair_count = stat.get("pair_count", 0) or 0
        svc_count = stat.get("service_count", 0)
        code_type = stat.get("code_type", "")

        label = (
            f"#{stat['clone_id']} "
            f"{svc_count} svcs "
            f"{pair_count} pairs "
            f"🔄{comod_count} "
            f"· {code_type}"
        )
        services = " ".join(str(s) for s in stat.get("services", []))
        options.append(
            {
                "label": label,
                "value": stat["clone_id"],
                "search": f"{stat['clone_id']} {services}",
            }
        )

    return options


def get_github_base_url(project: str) -> str:
    """プロジェクト概要と同じ方法でGitHubベースURLを取得する.

    取得優先順位:
    1. project_summary.json の metadata.url
    2. dest/services_json/{project}.json の URL フィールド
    3. fallback: プロジェクト名のドットをスラッシュに変換

    Args:
        project: プロジェクト名（例: "FudanSELab.train-ticket"）

    Returns:
        GitHubベースURL（例: "https://github.com/FudanSELab/train-ticket"）
    """
    from ..data_loader import load_project_summary

    # 1. project_summary.json から取得を試みる
    summary_data = load_project_summary()
    if summary_data and project in summary_data.get("projects", {}):
        project_info = summary_data["projects"][project]
        if "metadata" in project_info:
            metadata = project_info["metadata"]
            url = metadata.get("url")
            if url:
                return url

    # 2. services_json から取得を試みる
    services_json_url = _load_url_from_services_json(project)
    if services_json_url:
        return services_json_url

    # 3. fallback: プロジェクト名のドットをスラッシュに変換して URL 生成
    # 例: "FudanSELab.train-ticket" → "FudanSELab/train-ticket"
    project_path = project.replace(".", "/", 1)  # 最初のドットのみ変換
    return f"https://github.com/{project_path}"


class ProjectInfo:
    """services_json から読み込んだプロジェクト情報."""

    def __init__(self, url: str | None = None, default_branch: str | None = None):
        """Initialize ProjectInfo.

        Args:
            url: GitHub リポジトリ URL
            default_branch: デフォルトブランチ名
        """
        self.url = url
        self.default_branch = default_branch


def _load_project_info_from_services_json(project: str) -> ProjectInfo:
    """services_json/{project}.json から URL とブランチ情報を読み込む.

    Args:
        project: プロジェクト名

    Returns:
        ProjectInfo オブジェクト（URL とブランチを含む）
    """
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent
    services_json_path = project_root / "dest" / "services_json" / f"{project}.json"

    try:
        if not services_json_path.exists():
            logger.debug(
                "services_json not found for project %s: %s",
                project,
                services_json_path,
            )
            return ProjectInfo()

        with services_json_path.open(encoding="utf-8") as f:
            data = json.load(f)
            url = data.get("URL")
            default_branch = data.get("default_branch")
            if url:
                logger.debug("Found URL in services_json for %s: %s", project, url)
            if default_branch:
                logger.debug(
                    "Found default_branch in services_json for %s: %s",
                    project,
                    default_branch,
                )
            return ProjectInfo(url=url, default_branch=default_branch)
    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to parse services_json for project %s: %s",
            project,
            e,
        )
        return ProjectInfo()
    except OSError as e:
        logger.warning(
            "Failed to read services_json for project %s: %s",
            project,
            e,
        )
        return ProjectInfo()


def _load_url_from_services_json(project: str) -> str | None:
    """services_json/{project}.json から URL フィールドを読み込む.

    Args:
        project: プロジェクト名

    Returns:
        URL フィールドの値、または None（ファイルがない/URLがない場合）
    """
    return _load_project_info_from_services_json(project).url


def generate_github_file_url(
    project: str,
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    commit_hash: str | None = None,
) -> str | None:
    """プロジェクト概要と整合性のあるGitHubファイルURLを生成する.

    Args:
        project: プロジェクト名（例: "FudanSELab.train-ticket"）
        file_path: ファイルパス（例: "/ts-auth-service/src/Main.java"）
        start_line: 開始行番号（任意）
        end_line: 終了行番号（任意）
        commit_hash: コミットハッシュ（任意）。指定時はそのコミット時点のファイルを参照。

    Returns:
        GitHubファイルURL、または None（project/file_path が空の場合）

    URL生成ロジック:
        - commit_hash が指定されている場合: /blob/{commit_hash}/path/file
        - commit_hash が None の場合: ブランチを使用（下位互換性維持）
          - ブランチ取得優先順位:
            1. project_summary.json の metadata.default_branch
            2. services_json/{project}.json の default_branch フィールド
            3. fallback: "master"（多くの古いプロジェクトが master を使用）
    """
    if not project or not file_path:
        return None

    # プロジェクト概要と同じ方法でベースURLを取得
    github_base = get_github_base_url(project)

    # ファイルパスの先頭の/を削除
    clean_file_path = file_path.lstrip("/")

    # commit_hash が指定されている場合はそれを使用
    if commit_hash:
        ref = commit_hash
    else:
        # デフォルトブランチを取得（優先順位: summary → services_json → fallback）
        from ..data_loader import load_project_summary

        branch = None

        # 1. project_summary.json から取得
        summary_data = load_project_summary()
        if summary_data and project in summary_data.get("projects", {}):
            project_info = summary_data["projects"][project]
            if "metadata" in project_info:
                metadata = project_info["metadata"]
                branch = metadata.get("default_branch")

        # 2. services_json から取得
        if not branch:
            project_info_from_json = _load_project_info_from_services_json(project)
            branch = project_info_from_json.default_branch

        # 3. fallback: "master"（多くの古いプロジェクトが使用）
        if not branch:
            branch = "master"

        ref = branch

    # ファイルURLを構築
    file_url = f"{github_base}/blob/{ref}/{clean_file_path}"

    # 行番号が指定されている場合は行範囲を追加
    if start_line is not None:
        if end_line is not None and end_line != start_line:
            file_url += f"#L{start_line}-L{end_line}"
        else:
            file_url += f"#L{start_line}"

    return file_url


def generate_github_commit_url(project: str, commit_hash: str) -> str | None:
    """プロジェクト名とコミットハッシュからGitHubコミットURLを生成する.

    Args:
        project: プロジェクト名（例: "owner.repo"）
        commit_hash: コミットのSHAハッシュ

    Returns:
        GitHubコミットURLまたはNone（project/commitが空の場合）
    """
    if not project or not commit_hash:
        return None

    github_base = get_github_base_url(project)
    return f"{github_base}/commit/{commit_hash}"


def generate_github_diff_url(
    project: str,
    commit_hash: str,
    file_path: str,
) -> str | None:
    """コミット内の特定ファイルの差分ビューURLを生成する.

    GitHubの差分ビューURL形式:
    https://github.com/owner/repo/commit/{commit_hash}#diff-{sha256_of_filepath}

    Args:
        project: プロジェクト名
        commit_hash: コミットハッシュ
        file_path: ファイルパス

    Returns:
        差分ビューURL、または None（project/commit_hash/file_pathが空の場合）
    """
    if not project or not commit_hash or not file_path:
        return None

    github_base = get_github_base_url(project)
    clean_path = file_path.lstrip("/")
    path_hash = hashlib.sha256(clean_path.encode()).hexdigest()
    return f"{github_base}/commit/{commit_hash}#diff-{path_hash}"


def find_overlapping_clones(df, click_x, click_y):
    """指定された座標にあるクローンを検索する"""
    # 散布図は x=file_id_y, y=file_id_x で描画されているため、
    # coord_pair (file_id_y_file_id_x) と一致させるには click_x_click_y の順にする必要がある
    coord_pair = f"{int(click_x)}_{int(click_y)}"

    # coord_pair列が存在しない場合はコピー上で作成し、元の DataFrame を変更しない
    if "coord_pair" not in df.columns:
        df = df.copy()
        df["coord_pair"] = (
            df["file_id_y"].astype(str) + "_" + df["file_id_x"].astype(str)
        )

    # 該当する座標のクローンを検索
    overlapping_indices = df[df["coord_pair"] == coord_pair].index.tolist()
    return overlapping_indices


def build_clone_selector(overlapping_indices, df, sort_mode="line_count"):
    """重複クローン選択用のドロップダウンを生成する"""
    if len(overlapping_indices) <= 1:
        return html.Div()  # 重複がない場合は何も表示しない

    clone_count = len(overlapping_indices)
    clone_data = []  # ソート用のデータを格納
    seen_clones = set()  # 重複除去用

    # まず全てのクローンデータを収集し、重複を除去
    for i, idx in enumerate(overlapping_indices):
        row = df.loc[idx]
        file_x_path = row.get("file_path_x", "Unknown")
        file_y_path = row.get("file_path_y", "Unknown")
        file_x = str(file_x_path).split("/")[-1]
        file_y = str(file_y_path).split("/")[-1]
        lines_x = f"{row.get('start_line_x', 0)}-{row.get('end_line_x', 0)}"
        lines_y = f"{row.get('start_line_y', 0)}-{row.get('end_line_y', 0)}"
        line_count_x = _line_count(row.get("start_line_x", 0), row.get("end_line_x", 0))
        line_count_y = _line_count(row.get("start_line_y", 0), row.get("end_line_y", 0))
        clone_line_count = max(line_count_x, line_count_y)
        clone_id = row.get("clone_id", idx)

        # 重複チェック用のキーを作成（clone_id + ファイル + 行範囲）
        clone_key = f"{clone_id}|{file_x}|{lines_x}|{file_y}|{lines_y}"

        if clone_key not in seen_clones:
            seen_clones.add(clone_key)
            clone_data.append(
                {
                    "clone_id": clone_id,
                    "idx": idx,
                    "file_x": file_x,
                    "file_y": file_y,
                    "file_x_path": file_x_path,
                    "file_y_path": file_y_path,
                    "service_x": row.get("service_x", "Unknown"),
                    "service_y": row.get("service_y", "Unknown"),
                    "lines_x": lines_x,
                    "lines_y": lines_y,
                    "line_count_x": line_count_x,
                    "line_count_y": line_count_y,
                    "clone_line_count": clone_line_count,
                    "clone_key": clone_key,
                }
            )

    # 重複除去後の数が1以下の場合は何も表示しない
    if len(clone_data) <= 1:
        return html.Div()

    # clone_idごとの個数をカウント（重複除去後）
    clone_id_counts = Counter(data["clone_id"] for data in clone_data)

    clone_data = _sort_clone_selector_data(clone_data, clone_id_counts, sort_mode)
    options = _build_clone_selector_options(clone_data, clone_id_counts)

    # 重複除去の情報を表示
    removed_count = clone_count - len(clone_data)
    duplicate_note = (
        f"{removed_count} duplicate rows removed." if removed_count > 0 else None
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                f"{len(clone_data)}",
                                className="clone-selector-count",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        "Overlapping clones",
                                        className="clone-selector-title",
                                    ),
                                    html.Div(
                                        "Choose the line range to show below.",
                                        className="clone-selector-subtitle",
                                    ),
                                ],
                                className="clone-selector-title-stack",
                            ),
                        ],
                        className="clone-selector-title-row",
                    ),
                    (
                        html.Div(
                            duplicate_note,
                            className="clone-selector-duplicate-note",
                        )
                        if duplicate_note
                        else None
                    ),
                ],
                className="clone-selector-header",
            ),
            html.Div(
                [
                    html.Div("Line ranges", className="clone-selector-select-label"),
                    html.Div(
                        [
                            html.Span("Sort by", className="clone-selector-sort-label"),
                            dcc.RadioItems(
                                id="clone-selector-sort",
                                options=[
                                    {"label": "Lines", "value": "line_count"},
                                    {"label": "Clone ID", "value": "clone_id"},
                                ],
                                value=(
                                    sort_mode
                                    if sort_mode in {"line_count", "clone_id"}
                                    else "line_count"
                                ),
                                className="clone-selector-sort",
                                inputClassName="clone-selector-sort-input",
                                labelClassName="clone-selector-sort-option",
                            ),
                        ],
                        className="clone-selector-sort-row",
                    ),
                ],
                className="clone-selector-select-header",
            ),
            dcc.Dropdown(
                id="clone-dropdown",
                options=options,
                value=clone_data[0]["idx"],  # ソート後の最初のクローンを選択
                clearable=False,
                className="clone-selector-dropdown",
                style={"width": "100%"},
            ),
        ],
        className="clone-selector-panel",
    )


def build_clone_selector_options(overlapping_indices, df, sort_mode="line_count"):
    selector = build_clone_selector(overlapping_indices, df, sort_mode)
    for child in getattr(selector, "children", []) or []:
        if getattr(child, "id", None) == "clone-dropdown":
            return child.options, child.value
    return [], None


def _line_count(start_line, end_line):
    try:
        start = int(start_line)
        end = int(end_line)
    except (TypeError, ValueError):
        return 0
    return max(0, end - start + 1)


def _clone_id_sort_value(clone_id):
    try:
        return (0, int(clone_id))
    except (TypeError, ValueError):
        return (1, str(clone_id))


def _sort_clone_selector_data(clone_data, clone_id_counts, sort_mode):
    if sort_mode == "clone_id":
        return sorted(
            clone_data,
            key=lambda data: (
                _clone_id_sort_value(data["clone_id"]),
                -data["clone_line_count"],
                data["idx"],
            ),
        )
    return sorted(
        clone_data,
        key=lambda data: (
            -data["clone_line_count"],
            -data["line_count_x"] - data["line_count_y"],
            -clone_id_counts[data["clone_id"]],
            _clone_id_sort_value(data["clone_id"]),
            data["idx"],
        ),
    )


def _build_clone_selector_options(clone_data, clone_id_counts):
    options = []
    for data in clone_data:
        clone_id = data["clone_id"]
        count = clone_id_counts[clone_id]
        count_info = f" ({count} pairs)" if count > 1 else ""
        label = (
            f"Clone ID {clone_id}   "
            f"X: {data['line_count_y']}lines [{data['lines_y']}]   "
            f"<--->   "
            f"Y: {data['line_count_x']}lines [{data['lines_x']}]"
            f"{count_info}"
        )
        options.append({"label": label, "value": data["idx"]})
    return options
