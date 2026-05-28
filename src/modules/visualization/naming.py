"""可視化用CSVファイルの命名規則を管理するモジュール.

命名フォーマット:
    {リポジトリ名}_{検出手法}_{最小トークン数}_{フィルタ有無}_{判定手法}_{コミット方式}_{日付}.csv

各要素の仕様:
    - リポジトリ名: URLからリポジトリ名を抽出 (例: Caliopen, train-ticket)
    - 検出手法: normal / TKS{値} / RNR{値} (例: normal, TKS12, RNR05)
    - 最小トークン数: 最小一致トークン数の値 (例: 50, 30)
    - フィルタ有無: filtered / nofilter
    - 判定手法: cloneset / clonepair
    - コミット方式: merge / tag / freq{間隔値}
    - 日付: YYYYMMDD形式

補足:
    - SEARCH_DEPTH と MAX_ANALYZED_COMMITS はデフォルト(-1)以外の場合のみ末尾に追加
      (例: _sd100_mac50)
"""

from __future__ import annotations

import re
from datetime import datetime


def extract_repo_name(url: str) -> str:
    """GitHubのURLからリポジトリ名を抽出する.

    Args:
        url: GitHub リポジトリURL (例: https://github.com/CaliOpen/Caliopen).

    Returns:
        リポジトリ名 (例: Caliopen).
    """
    cleaned = url.rstrip("/")
    return cleaned.split("/")[-1]


def _format_detection_method(
    detection_method: str,
    tks: int = 12,
    rnr: float = 0.5,
) -> str:
    """検出手法文字列をフォーマットする.

    Args:
        detection_method: "normal", "tks", "rnr" のいずれか.
        tks: TKS のパラメータ値.
        rnr: RNR のパラメータ値.

    Returns:
        フォーマット済み文字列 (例: "normal", "TKS12", "RNR05").

    Raises:
        ValueError: 未知の detection_method が指定された場合.
    """
    if detection_method == "normal":
        return "normal"
    if detection_method == "tks":
        return f"TKS{tks}"
    if detection_method == "rnr":
        # 0.5 -> "05", 0.3 -> "03" のように小数点を除去してゼロ埋め
        formatted = f"{rnr:.2f}".replace("0.", "").replace(".", "")
        return f"RNR{formatted}"
    raise ValueError(f"unknown detection_method: {detection_method}")


def _format_filter(import_filter: bool) -> str:
    """フィルタ有無を文字列化する."""
    return "filtered" if import_filter else "nofilter"


def _format_comod_method(comod_method: str) -> str:
    """判定手法を文字列化する.

    Args:
        comod_method: "clone_set" or "clone_pair".

    Returns:
        "cloneset" or "clonepair".

    Raises:
        ValueError: 未知の comod_method が指定された場合.
    """
    mapping = {
        "clone_set": "cloneset",
        "clone_pair": "clonepair",
    }
    if comod_method not in mapping:
        raise ValueError(f"unknown comod_method: {comod_method}")
    return mapping[comod_method]


def _format_analysis_method(
    analysis_method: str,
    analysis_frequency: int = 50,
) -> str:
    """コミット方式を文字列化する.

    Args:
        analysis_method: "merge_commit", "tag", "frequency" のいずれか.
        analysis_frequency: frequency方式の場合の間隔値.

    Returns:
        フォーマット済み文字列 (例: "merge", "tag", "freq50").

    Raises:
        ValueError: 未知の analysis_method が指定された場合.
    """
    if analysis_method == "merge_commit":
        return "merge"
    if analysis_method == "tag":
        return "tag"
    if analysis_method == "frequency":
        return f"freq{analysis_frequency}"
    raise ValueError(f"unknown analysis_method: {analysis_method}")


def build_visualization_csv_filename(
    *,
    url: str,
    detection_method: str = "normal",
    tks: int = 12,
    rnr: float = 0.5,
    min_tokens: int = 50,
    import_filter: bool = True,
    comod_method: str = "clone_set",
    analysis_method: str = "merge_commit",
    analysis_frequency: int = 50,
    search_depth: int = -1,
    max_analyzed_commits: int = -1,
    date: str | None = None,
) -> str:
    """可視化用CSVのファイル名(拡張子なし)を生成する.

    Args:
        url: GitHub リポジトリURL.
        detection_method: 検出手法 ("normal", "tks", "rnr").
        tks: TKS パラメータ値.
        rnr: RNR パラメータ値.
        min_tokens: 最小一致トークン数.
        import_filter: import行フィルタの適用有無.
        comod_method: 同時修正の判定単位 ("clone_set", "clone_pair").
        analysis_method: コミット方式 ("merge_commit", "tag", "frequency").
        analysis_frequency: frequency方式の間隔値.
        search_depth: コミット探索深度 (-1=デフォルト).
        max_analyzed_commits: 分析対象コミット数上限 (-1=デフォルト).
        date: YYYYMMDD形式の日付文字列. None の場合は当日日付を使用.

    Returns:
        拡張子なしのファイル名文字列.
    """
    repo_name = extract_repo_name(url)
    detection = _format_detection_method(detection_method, tks, rnr)
    filter_str = _format_filter(import_filter)
    comod = _format_comod_method(comod_method)
    commit_method = _format_analysis_method(analysis_method, analysis_frequency)

    if date is None:
        date = datetime.now().strftime("%Y%m%d")

    parts = [repo_name, detection, str(min_tokens), filter_str, comod, commit_method, date]

    # デフォルトでないオプションを末尾に追加
    if search_depth != -1:
        parts.append(f"sd{search_depth}")
    if max_analyzed_commits != -1:
        parts.append(f"mac{max_analyzed_commits}")

    return "_".join(parts)


def build_visualization_csv_filename_from_params(params: dict) -> str:
    """Web UIのパラメータ辞書から可視化用CSVファイル名を生成する.

    Args:
        params: Web UIの _validate_run_params() で検証済みのパラメータ辞書.

    Returns:
        拡張子なしのファイル名文字列.
    """
    return build_visualization_csv_filename(
        url=params["url"],
        detection_method=params.get("detection_method", "normal"),
        tks=params.get("tks", 12),
        rnr=params.get("rnr", 0.5),
        min_tokens=params.get("min_tokens", 50),
        import_filter=params.get("import_filter", True),
        comod_method=params.get("comod_method", "clone_set"),
        analysis_method=params.get("analysis_method", "merge_commit"),
        analysis_frequency=params.get("analysis_frequency", 50),
        search_depth=params.get("search_depth", -1),
        max_analyzed_commits=params.get("max_analyzed_commits", -1),
    )


def parse_visualization_csv_filename(filename: str) -> dict | None:
    """可視化CSVのファイル名をパースしてパラメータ辞書に分解する.

    Args:
        filename: ファイル名 (拡張子あり/なし どちらも可).

    Returns:
        パース成功時はパラメータ辞書, 失敗時は None.
    """
    stem = filename.removesuffix(".csv")

    # 末尾のオプション (sd, mac) を先に抽出
    search_depth = -1
    max_analyzed_commits = -1
    sd_match = re.search(r"_sd(\d+)", stem)
    if sd_match:
        search_depth = int(sd_match.group(1))
        stem = stem[: sd_match.start()] + stem[sd_match.end() :]
    mac_match = re.search(r"_mac(\d+)", stem)
    if mac_match:
        max_analyzed_commits = int(mac_match.group(1))
        stem = stem[: mac_match.start()] + stem[mac_match.end() :]

    # 末尾から日付を抽出 (YYYYMMDD)
    date_match = re.search(r"_(\d{8})$", stem)
    if not date_match:
        return None
    date = date_match.group(1)
    stem = stem[: date_match.start()]

    # コミット方式を抽出
    commit_match = re.search(r"_(merge|tag|freq\d+)$", stem)
    if not commit_match:
        return None
    commit_method_str = commit_match.group(1)
    stem = stem[: commit_match.start()]

    # 判定手法を抽出
    comod_match = re.search(r"_(cloneset|clonepair)$", stem)
    if not comod_match:
        return None
    comod_str = comod_match.group(1)
    stem = stem[: comod_match.start()]

    # フィルタ有無を抽出
    filter_match = re.search(r"_(filtered|nofilter)$", stem)
    if not filter_match:
        return None
    filter_str = filter_match.group(1)
    stem = stem[: filter_match.start()]

    # 最小トークン数を抽出
    tokens_match = re.search(r"_(\d+)$", stem)
    if not tokens_match:
        return None
    min_tokens = int(tokens_match.group(1))
    stem = stem[: tokens_match.start()]

    # 検出手法を抽出
    detection_match = re.search(r"_(normal|TKS\d+|RNR\d+)$", stem)
    if not detection_match:
        return None
    detection_str = detection_match.group(1)
    repo_name = stem[: detection_match.start()]

    # コミット方式を復元
    if commit_method_str == "merge":
        analysis_method = "merge_commit"
        analysis_frequency = 50
    elif commit_method_str == "tag":
        analysis_method = "tag"
        analysis_frequency = 50
    elif commit_method_str.startswith("freq"):
        analysis_method = "frequency"
        analysis_frequency = int(commit_method_str[4:])
    else:
        return None

    # 検出手法を復元
    detection_method = "normal"
    tks = 12
    rnr = 0.5
    if detection_str.startswith("TKS"):
        detection_method = "tks"
        tks = int(detection_str[3:])
    elif detection_str.startswith("RNR"):
        detection_method = "rnr"
        rnr_digits = detection_str[3:]
        rnr = int(rnr_digits) / 100 if len(rnr_digits) > 2 else int(rnr_digits) / 10

    return {
        "repo_name": repo_name,
        "detection_method": detection_method,
        "tks": tks,
        "rnr": rnr,
        "min_tokens": min_tokens,
        "import_filter": filter_str == "filtered",
        "comod_method": "clone_set" if comod_str == "cloneset" else "clone_pair",
        "analysis_method": analysis_method,
        "analysis_frequency": analysis_frequency,
        "search_depth": search_depth,
        "max_analyzed_commits": max_analyzed_commits,
        "date": date,
    }
