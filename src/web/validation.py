"""Web UIリクエストのバリデーションモジュール.

パイプライン実行パラメータの型変換と値検証を行う.
"""

import re


def _parse_bool(value: object, name: str) -> bool:
    """値をboolに変換する.真偽判定が曖昧な値はValueErrorを送出する."""
    if isinstance(value, bool):
        return value
    raise ValueError(f"{name} must be a boolean, got {type(value).__name__}")


def _parse_int(value: object, name: str) -> int:
    """値をintに変換する.

    Args:
        value: 変換対象.
        name: パラメータ名 (エラーメッセージ用).

    Returns:
        変換した整数値.

    Raises:
        ValueError: 変換不可能な値の場合.
    """
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, got bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    raise ValueError(f"{name} must be an integer, got {type(value).__name__}: {value}")


def _parse_float(value: object, name: str) -> float:
    """値をfloatに変換する.

    Args:
        value: 変換対象.
        name: パラメータ名 (エラーメッセージ用).

    Returns:
        変換した浮動小数点値.

    Raises:
        ValueError: 変換不可能な値の場合.
    """
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, got bool")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            pass
    raise ValueError(f"{name} must be a number, got {type(value).__name__}: {value}")


def validate_run_params(params: dict) -> dict:
    """パイプライン実行パラメータを検証し,正規化した辞書を返す.

    Args:
        params: Web UIから送信された生パラメータ辞書.

    Returns:
        検証・型変換済みのパラメータ辞書.

    Raises:
        ValueError: 必須パラメータの欠落や不正な値の場合.
    """
    url = (params.get("url") or "").strip()
    if not url:
        raise ValueError("url is required")
    if not re.match(r"https?://", url):
        raise ValueError(f"url must start with http:// or https://, got: {url}")

    detection_method = params.get("detection_method", "normal")
    if detection_method not in ("normal", "tks", "rnr"):
        raise ValueError(
            f"detection_method must be 'normal', 'tks', or 'rnr', got: {detection_method}"
        )

    tks = _parse_int(params.get("tks", 12), "tks")
    if tks < 1:
        raise ValueError(f"tks must be >= 1, got {tks}")
    rnr = _parse_float(params.get("rnr", 0.5), "rnr")
    if not 0.0 < rnr <= 1.0:
        raise ValueError(f"rnr must be in (0, 1], got {rnr}")
    min_tokens = _parse_int(params.get("min_tokens", 50), "min_tokens")
    if min_tokens < 1:
        raise ValueError(f"min_tokens must be >= 1, got {min_tokens}")
    import_filter = _parse_bool(params.get("import_filter", True), "import_filter")
    force_recompute = _parse_bool(
        params.get("force_recompute", True), "force_recompute"
    )
    generate_scatter_csv = _parse_bool(
        params.get("generate_scatter_csv", True), "generate_scatter_csv"
    )
    comod_method = params.get("comod_method", "clone_set")
    analysis_method = params.get("analysis_method", "merge_commit")
    analysis_frequency = _parse_int(
        params.get("analysis_frequency", 1), "analysis_frequency"
    )
    search_depth = _parse_int(params.get("search_depth", -1), "search_depth")
    max_analyzed_commits = _parse_int(
        params.get("max_analyzed_commits", -1), "max_analyzed_commits"
    )

    return {
        "url": url,
        "detection_method": detection_method,
        "tks": tks,
        "rnr": rnr,
        "min_tokens": min_tokens,
        "import_filter": import_filter,
        "force_recompute": force_recompute,
        "generate_scatter_csv": generate_scatter_csv,
        "comod_method": comod_method,
        "analysis_method": analysis_method,
        "analysis_frequency": analysis_frequency,
        "search_depth": search_depth,
        "max_analyzed_commits": max_analyzed_commits,
    }
