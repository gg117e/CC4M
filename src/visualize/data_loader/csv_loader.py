"""クローンデータ読み込みモジュール.

CSV/JSON 形式のクローン検出結果を読み込み,
サービスマッピングを適用して可視化用 DataFrame を生成する.
"""

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from ..constants import DetectionMethod
from ..paths import (
    DEST_ROOT,
    DEST_SCATTER,
    DEST_CLONE_METRICS,
    DEST_SERVICES_JSON,
    DEST_CLONE_ANALYSIS,
    get_scatter_csv_dir,
    get_clone_metrics_path,
    get_services_json_path,
)

logger = logging.getLogger(__name__)

SCATTER_FILE_COMMIT_PREFIX = "scatter_file:"


def _text_series(series, fill_value=""):
    return series.astype("string").fillna(fill_value).astype(str)


def _comodified_bool_to_count(series) -> pd.Series:
    return series.isin([True, 1, "1", "True", "true"]).astype("Int64")


def _normalize_scatter_comodification_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure scatter data has commit-list and count columns across CSV versions."""

    if "comodified_commits" not in df.columns:
        df["comodified_commits"] = "[]"
    else:
        df["comodified_commits"] = _text_series(df["comodified_commits"], "[]")
        empty_mask = df["comodified_commits"].str.strip() == ""
        df.loc[empty_mask, "comodified_commits"] = "[]"

    if "comodification_count" in df.columns:
        df["comodification_count"] = (
            pd.to_numeric(df["comodification_count"], errors="coerce")
            .fillna(0)
            .astype("Int64")
        )
    elif "comodified" in df.columns:
        df["comodification_count"] = _comodified_bool_to_count(df["comodified"])
    else:
        df["comodification_count"] = pd.Series(0, index=df.index, dtype="Int64")

    if "comodified" not in df.columns:
        df["comodified"] = df["comodification_count"].fillna(0).astype(int) >= 1

    return df

# データキャッシュ用のグローバル変数
_data_cache = {}


def load_service_file_ranges_cached(services_json_path: str, language: str):
    """services.json から言語別の file_ranges を取得する（キャッシュ版）"""
    logger.debug("Loading service ranges from %s", services_json_path)
    with open(services_json_path, encoding="utf-8") as f:
        data = json.load(f)

    # 言語キーの大文字小文字を吸収して検索
    target_lang = (language or "").lower()

    # 1) language_stats (enrich_services_json で生成) を優先的に確認
    language_stats = data.get("language_stats", {})
    lang_stat_section = _find_lang_section(language_stats, language, target_lang)
    if isinstance(lang_stat_section, dict) and "file_ranges" in lang_stat_section:
        result = lang_stat_section["file_ranges"]
        logger.debug(
            "Loaded service ranges from language_stats: %d services", len(result)
        )
        return result

    # 2) languages キー (レガシー形式) にフォールバック
    languages_data = data.get("languages", {})
    lang_section = _find_lang_section(languages_data, language, target_lang)
    if isinstance(lang_section, dict) and "file_ranges" in lang_section:
        result = lang_section["file_ranges"]
        logger.debug("Loaded service ranges from languages: %d services", len(result))
        return result

    # 3) トップレベル file_ranges (最古のレガシー形式)
    result = data.get("file_ranges", {})
    logger.debug("Loaded service ranges (top-level fallback): %s", result)
    return result


def _find_lang_section(container: dict, language: str, target_lang_lower: str) -> dict:
    """辞書内から大文字小文字を無視して言語セクションを探す."""
    if language in container:
        return container[language]
    for key, val in container.items():
        if key.lower() == target_lang_lower:
            return val
    return {}


def load_full_services_json(services_json_path: str):
    """services.json の全データを読み込む"""
    if not os.path.exists(services_json_path):
        return None
    try:
        with open(services_json_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading services.json: {e}")
        return None


def resolve_services_json_path(project_name: str) -> str | None:
    """プロジェクトの services.json パスを解決する.

    優先順位:
    1. ``dest/services_json/{project_name}.json``
    2. ``dest/scatter/{project_name}/services.json``

    Args:
        project_name: プロジェクト名 (owner.repo).

    Returns:
        見つかったパス文字列. いずれも存在しなければ ``None``.
    """
    primary = get_services_json_path(project_name)
    if primary.exists():
        return str(primary)
    fallback = DEST_SCATTER / project_name / "services.json"
    if fallback.exists():
        return str(fallback)
    return None


def load_clone_metrics(
    project: str,
    language: str,
) -> dict | None:
    """dest/clone_metrics から事前計算済みメトリクス JSON を読み込む.

    Args:
        project: プロジェクト名 (owner.repo).
        language: 言語名.

    Returns:
        ``{"service": [...], "clone_set": [...], "file": [...]}``
        またはファイルが見つからない場合は ``None``.
    """
    metrics_path = get_clone_metrics_path(project, language)
    if not metrics_path.exists():
        logger.debug("Clone metrics file not found: %s", metrics_path)
        return None
    try:
        return json.loads(metrics_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Error loading clone metrics: %s", e)
        return None


def load_service_file_ranges(services_json_path: str, language: str):
    """services.json から言語別の file_ranges を取得する（レガシー互換性のため）"""
    return load_service_file_ranges_cached(services_json_path, language)


def file_id_to_service(file_id: int, file_ranges: dict):
    """ファイルIDからサービス名を特定する"""
    for svc, ranges in file_ranges.items():
        for start, end in ranges:
            if start <= file_id <= end:
                return svc
    return "unknown"


def vectorized_file_id_to_service(file_ids, file_ranges):
    """ベクトル化されたファイルIDからサービス名への変換"""
    services = ["unknown"] * len(file_ids)
    for i, file_id in enumerate(file_ids):
        services[i] = file_id_to_service(file_id, file_ranges)
    return services


def postprocess_clone_dataframe(
    df: pd.DataFrame,
    file_ranges: dict,
    *,
    compute_overlap: bool = True,
) -> pd.DataFrame:
    """クローンデータフレームの共通後処理を実行する.

    以下の処理を順次実行:
    1. サービスマッピング（file_id_x/y → service_x/y）
    2. 関係性計算（intra/inter）
    3. 座標ペア生成（coord_pair）
    4. オーバーラップカウント計算（overlap_count, total_lines, coord_total_lines）

    Args:
        df: クローンデータのDataFrame（file_id_x, file_id_y 等を含む）.
        file_ranges: サービス名 -> ファイルID範囲リストのマッピング.
        compute_overlap: overlap_count 等を計算するか（デフォルト True）.

    Returns:
        後処理済みのDataFrame.
    """
    # 1. サービスマッピング
    if "service_x" not in df.columns or "service_y" not in df.columns:
        logger.info("Computing service mappings...")
        if "file_id_x" in df.columns:
            df["service_x"] = vectorized_file_id_to_service(
                df["file_id_x"].values, file_ranges
            )
        if "file_id_y" in df.columns:
            df["service_y"] = vectorized_file_id_to_service(
                df["file_id_y"].values, file_ranges
            )

    # 2. 関係性計算
    if "relation" not in df.columns:
        logger.info("Computing relations...")
        df["relation"] = "inter"
        if "service_x" in df.columns and "service_y" in df.columns:
            df.loc[df["service_x"] == df["service_y"], "relation"] = "intra"

    # 3. 座標ペア生成
    if "coord_pair" not in df.columns and {"file_id_x", "file_id_y"} <= set(df.columns):
        logger.info("Computing coordinate pairs...")
        df["coord_pair"] = (
            df["file_id_x"].astype(str) + "_" + df["file_id_y"].astype(str)
        )

    # 4. オーバーラップカウント計算
    if compute_overlap and "coord_pair" in df.columns:
        if "overlap_count" not in df.columns or "coord_total_lines" not in df.columns:
            logger.info("Computing overlap counts and total lines...")
            coord_counts = df["coord_pair"].value_counts()
            df["overlap_count"] = df["coord_pair"].map(coord_counts)

            # total_lines 計算（行範囲カラムが存在する場合）
            line_cols = {"start_line_x", "end_line_x", "start_line_y", "end_line_y"}
            if line_cols <= set(df.columns):
                df["total_lines"] = (df["end_line_x"] - df["start_line_x"] + 1) + (
                    df["end_line_y"] - df["start_line_y"] + 1
                )
                coord_total_lines = df.groupby("coord_pair")["total_lines"].sum()
                df["coord_total_lines"] = df["coord_pair"].map(coord_total_lines)

    return df


def _unified_sources_exist(project_name: str, language: str) -> bool:
    project_csv_dir = f"data/csv/{project_name}"
    return os.path.exists(
        f"{project_csv_dir}/ccfsw_{language.lower()}.csv"
    ) or os.path.exists(f"{project_csv_dir}/tks_{language.lower()}.csv")


def _scatter_sources(project_name: str, language: str, commit_hash: str | None = None):
    from .project_discovery import _parse_scatter_csv_filename

    base_dir = get_scatter_csv_dir(project_name)
    if not base_dir.exists():
        return []

    if commit_hash and str(commit_hash).startswith(SCATTER_FILE_COMMIT_PREFIX):
        filename = str(commit_hash)[len(SCATTER_FILE_COMMIT_PREFIX) :]
        specific = base_dir / filename
        if not specific.exists() or not specific.is_file():
            return []
        if specific.name.endswith("_unknown.csv"):
            return []

        match = _parse_scatter_csv_filename(specific.name)
        if not match:
            return []
        if str(match.get("language", "")).lower() != language.lower():
            return []

        detection_token = str(match.get("detection", "normal")).lower()
        if detection_token.startswith("tks"):
            detection_method = DetectionMethod.TKS
        elif detection_token.startswith("rnr"):
            detection_method = DetectionMethod.CCFSW
        else:
            detection_method = DetectionMethod.NO_IMPORT

        return [(specific, detection_method)]

    pattern = re.compile(
        r"^(?P<prefix>tks_|import_)?(?P<lang>.+)_scatter(_unknown)?\.csv$",
        re.IGNORECASE,
    )
    sources = []
    for csv_path in base_dir.iterdir():
        match = pattern.match(csv_path.name)
        if not match:
            continue
        lang = match.group("lang")
        if lang.lower() != language.lower():
            continue

        prefix = match.group("prefix") or ""
        detection_method = DetectionMethod.from_prefix(prefix)

        # UIでサポートされていないCCFSW (Legacy) は読み込まない
        if detection_method == DetectionMethod.CCFSW:
            continue

        sources.append((csv_path, detection_method))

    return sorted(sources, key=lambda s: s[0].name)


def load_from_scatter_csv(
    sources, services_json_path: str, cache_key: str, language: str
):
    """dest/scatter 出力からクローンデータを読み込む"""
    file_ranges = {}
    if os.path.exists(services_json_path):
        try:
            file_ranges = load_service_file_ranges_cached(services_json_path, language)
        except Exception as exc:
            logger.warning(
                "services.json unreadable, continue without boundaries: path=%s err=%s",
                services_json_path,
                exc,
            )
            file_ranges = {}
    else:
        logger.warning(
            "services.json not found, continue without boundaries: path=%s",
            services_json_path,
        )

    frames = []
    MAX_FILE_SIZE_MB = 2000  # 2000MB制限 (静的モード対応のため緩和)

    for csv_path, detection_method in sources:
        # ファイルサイズチェック
        try:
            file_size_mb = csv_path.stat().st_size / (1024 * 1024)
            if file_size_mb > MAX_FILE_SIZE_MB:
                logger.warning(
                    f"ファイルサイズが大きすぎます ({file_size_mb:.0f} MB)。このファイルはスキップされます: {csv_path.name}"
                )
                continue
        except Exception as e:
            logger.warning(f"Failed to check file size for {csv_path}: {e}")

        try:
            # メモリ使用量削減のために型を明示的に指定
            dtypes = {
                "clone_id": "Int64",
                "file_id_x": "Int64",
                "file_id_y": "Int64",
                "start_line_x": "Int64",
                "end_line_x": "Int64",
                "start_line_y": "Int64",
                "end_line_y": "Int64",
                "token_count": "Int64",
                "relation": "category",
                "file_type_x": "category",
                "file_type_y": "category",
                "service_x": "string",
                "service_y": "string",
                "file_path_x": "string",
                "file_path_y": "string",
                "comodified": "boolean",
                "comodified_commits": "string",
                "comodification_count": "Int64",
            }
            df = pd.read_csv(csv_path, dtype=dtypes)
            logger.info(
                "Loaded %s with %d rows. Method: %s",
                csv_path.name,
                len(df),
                detection_method,
            )
        except Exception as exc:
            error_msg = f"scatter CSV 読み込みに失敗: path={csv_path}"
            logger.error(error_msg)
            result = (None, None, error_msg)
            _data_cache[cache_key] = result
            return result

        df["detection_method"] = detection_method
        frames.append(df)

    if not frames:
        logger.debug("No frames loaded from scatter sources.")
        result = (None, None, "scatter CSV が見つかりません")
        _data_cache[cache_key] = result
        return result

    df = pd.concat(frames, ignore_index=True)
    df = _normalize_scatter_comodification_columns(df)

    # サービス名の欠損補完 (unknown対応)
    if "service_x" in df.columns:
        df["service_x"] = _text_series(df["service_x"], "unknown").replace(
            "", "unknown"
        )
    if "service_y" in df.columns:
        df["service_y"] = _text_series(df["service_y"], "unknown").replace(
            "", "unknown"
        )

    # relationの欠損補完
    if "relation" in df.columns:
        df["relation"] = _text_series(df["relation"])
        mask = df["relation"].isna() | (df["relation"] == "")
        if mask.any():
            is_intra = df.loc[mask, "service_x"] == df.loc[mask, "service_y"]
            df.loc[mask, "relation"] = is_intra.map({True: "intra", False: "inter"})

    if "coord_pair" not in df.columns and {"file_id_x", "file_id_y"} <= set(df.columns):
        df["coord_pair"] = (
            df["file_id_y"].astype(str) + "_" + df["file_id_x"].astype(str)
        )

    numeric_cols = [
        "file_id_x",
        "file_id_y",
        "start_line_x",
        "end_line_x",
        "start_line_y",
        "end_line_y",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    if "clone_id" in df.columns:
        df["clone_id"] = pd.to_numeric(df["clone_id"], errors="coerce").astype("Int64")

    if "service_x" not in df.columns and "file_id_x" in df.columns:
        if file_ranges:
            df["service_x"] = vectorized_file_id_to_service(
                df["file_id_x"].fillna(-1).astype(int).values, file_ranges
            )
        else:
            df["service_x"] = "unknown"
    if "service_y" not in df.columns and "file_id_y" in df.columns:
        if file_ranges:
            df["service_y"] = vectorized_file_id_to_service(
                df["file_id_y"].fillna(-1).astype(int).values, file_ranges
            )
        else:
            df["service_y"] = "unknown"

    df = df.dropna(subset=["file_id_x", "file_id_y"])

    result = (df, file_ranges, None)
    _data_cache[cache_key] = result
    return result


def _no_imports_sources(project_name: str, language: str):
    codeclones_dir = DEST_ROOT / "codeclones"
    return (
        str(codeclones_dir / project_name / "latest" / f"{language}_no_imports.json"),
        str(DEST_CLONE_ANALYSIS / project_name / "services.json"),
    )


def _project_csv_sources(project_name: str, language: str):
    base = f"data/csv/{project_name}"
    return (
        base,
        f"{base}/ccfsw_{language.lower()}.csv",
        f"{base}/tks_{language.lower()}.csv",
        f"{base}/rnr_{language.lower()}.csv",
    )


def _legacy_csv_path(project_name: str, commit_hash: str, language: str):
    legacy = f"src/visualize/csv/{project_name}_{commit_hash}_{language}_all.csv"
    if os.path.exists(legacy):
        return legacy
    fallback = f"src/visualize/csv/{project_name}_latest_{language}_all.csv"
    return fallback if os.path.exists(fallback) else None


def load_and_process_data(project_name: str, commit_hash: str, language: str):
    """可視化用クローンデータをロード。

    優先順位: dest/scatter > 統一ローダー > no_imports JSON > プロジェクトCSV > レガシーCSV
    """
    cache_key = f"{project_name}_{commit_hash}_{language}"
    if cache_key in _data_cache:
        logger.debug("Loading from cache: %s", cache_key)
        return _data_cache[cache_key]

    logger.info("Loading and processing data: %s", cache_key)

    # 0) dest/scatter 出力
    scatter_sources = _scatter_sources(project_name, language, commit_hash)
    services_json_path = (
        resolve_services_json_path(project_name)
        or str(DEST_SCATTER / project_name / "services.json")
    )
    if scatter_sources:
        result = load_from_scatter_csv(
            scatter_sources, services_json_path, cache_key, language
        )
        if result[0] is not None:
            return result
        logger.info(
            "Scatter CSV loading failed or empty: %s, falling back...", result[2]
        )

    # 1) 統一データローダー
    try:
        from core.unified_data_loader import UnifiedDataLoader  # noqa: F401

        if _unified_sources_exist(project_name, language):
            logger.info("Using unified data loader")
            return load_from_unified_loader(project_name, language, cache_key)
    except ImportError:
        logger.info("Unified data loader not available, falling back")

    # 2) no_imports JSON
    no_imports_json_path, services_json_path = _no_imports_sources(
        project_name, language
    )
    if os.path.exists(no_imports_json_path) and os.path.exists(services_json_path):
        logger.info("Using no_imports JSON data: %s", no_imports_json_path)
        return load_from_no_imports_json(
            no_imports_json_path, services_json_path, cache_key, project_name, language
        )

    # 3) プロジェクトCSV (CCFSW/TKS/RNR)
    project_csv_dir, ccfsw_csv_path, tks_csv_path, rnr_csv_path = _project_csv_sources(
        project_name, language
    )
    if os.path.exists(services_json_path) and (
        os.path.exists(ccfsw_csv_path)
        or os.path.exists(tks_csv_path)
        or os.path.exists(rnr_csv_path)
    ):
        logger.info("Using project-based CSV data: %s", project_csv_dir)
        return load_from_project_csv_with_rnr(
            project_csv_dir,
            ccfsw_csv_path,
            tks_csv_path,
            rnr_csv_path,
            services_json_path,
            cache_key,
            language,
        )

    # 4) レガシーCSV
    legacy_csv_path = _legacy_csv_path(project_name, commit_hash, language)
    if legacy_csv_path and os.path.exists(services_json_path):
        logger.info("Fallback to legacy CSV data: %s", legacy_csv_path)
        return load_from_csv_fallback(
            legacy_csv_path, services_json_path, cache_key, language
        )

    error_msg = f"No data source found for {project_name}_{language}"
    result = (None, None, error_msg)
    _data_cache[cache_key] = result
    return result


def load_from_unified_loader(project_name: str, language: str, cache_key: str):
    """統一データローダーからデータを読み込み"""
    try:
        from core.unified_data_loader import UnifiedDataLoader

        loader = UnifiedDataLoader(project_name, language)
        df, service_ranges, error = loader.load_unified_data()

        if error:
            logger.warning("Unified loader error: %s", error)
            result = (None, None, error)
        else:
            logger.info("Unified data loaded: %d clone pairs", len(df))
            result = (df, service_ranges, None)

        _data_cache[cache_key] = result
        return result

    except Exception as e:
        logger.error("Unified loader failed: %s", e)
        error_msg = f"Unified data loader error: {e}"
        result = (None, None, error_msg)
        _data_cache[cache_key] = result
        return result


def load_from_no_imports_json(
    json_path: str,
    services_json_path: str,
    cache_key: str,
    project_name: str,
    language: str,
):
    """
    no_importsのJSONファイルからクローンデータを読み込む（推奨方式）

    no_importsデータには以下の利点があります：
    - importステートメントが除外されているため、実質的なコードクローンのみが検出される
    - file_dataにfile_idとfile_pathの完全なマッピングが含まれている
    - 処理速度が高速
    """
    try:
        logger.info("Loading no_imports JSON file...")
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        logger.info("Loading service file ranges...")
        file_ranges = load_service_file_ranges_cached(services_json_path, language)

        # file_idからfile_pathへのマッピングを作成
        file_id_to_path = {}
        for file_info in json_data.get("file_data", []):
            file_id_to_path[file_info["file_id"]] = file_info["file_path"]

        # JSONからクローンペアのDataFrameを構築
        clone_pairs = []
        clone_sets = json_data.get("clone_sets", [])

        logger.info("Processing %d clone sets...", len(clone_sets))

        for clone_id, clone_set in enumerate(clone_sets):
            fragments = clone_set.get("fragments", [])
            if len(fragments) < 2:
                continue

            # クローンセット内のすべてのペアを生成
            for i in range(len(fragments)):
                for j in range(i + 1, len(fragments)):
                    frag1, frag2 = fragments[i], fragments[j]

                    clone_pairs.append(
                        {
                            "clone_id": clone_id,
                            "file_id_x": frag1["file_id"],
                            "start_line_x": frag1["start_line"],
                            "end_line_x": frag1["end_line"],
                            "file_id_y": frag2["file_id"],
                            "start_line_y": frag2["start_line"],
                            "end_line_y": frag2["end_line"],
                            "file_path_x": file_id_to_path.get(frag1["file_id"], ""),
                            "file_path_y": file_id_to_path.get(frag2["file_id"], ""),
                        }
                    )

        if not clone_pairs:
            result = (None, None, "No clone pairs found in JSON data")
            _data_cache[cache_key] = result
            return result

        logger.info("Generated %d clone pairs from JSON", len(clone_pairs))
        df = pd.DataFrame(clone_pairs)

        # 型を最適化
        df = df.astype(
            {
                "file_id_x": "int32",
                "file_id_y": "int32",
                "start_line_x": "int32",
                "end_line_x": "int32",
                "start_line_y": "int32",
                "end_line_y": "int32",
                "clone_id": "int32",
            }
        )

        # サービス情報の計算
        logger.info("Computing service mappings...")
        df["service_x"] = vectorized_file_id_to_service(
            df["file_id_x"].values, file_ranges
        )
        df["service_y"] = vectorized_file_id_to_service(
            df["file_id_y"].values, file_ranges
        )

        # 関係性の計算
        logger.info("Computing relations...")
        df["relation"] = "inter"
        df.loc[df["service_x"] == df["service_y"], "relation"] = "intra"
        df["clone_type"] = "Normal"  # デフォルトはNormal

        # TKSデータを統合
        tks_csv_path = f"data/csv/{project_name}/tks_{language.lower()}.csv"
        if os.path.exists(tks_csv_path):
            logger.info("Loading and integrating TKS data from: %s", tks_csv_path)
            try:
                tks_df = pd.read_csv(
                    tks_csv_path,
                    dtype={
                        "file_id_x": "int32",
                        "file_id_y": "int32",
                        "start_line_x": "int32",
                        "end_line_x": "int32",
                        "start_line_y": "int32",
                        "end_line_y": "int32",
                        "clone_id": "int32",
                    },
                )

                if not tks_df.empty:
                    # TKSデータの前処理
                    tks_df["service_x"] = vectorized_file_id_to_service(
                        tks_df["file_id_x"].values, file_ranges
                    )
                    tks_df["service_y"] = vectorized_file_id_to_service(
                        tks_df["file_id_y"].values, file_ranges
                    )
                    tks_df["relation"] = "inter"
                    tks_df.loc[
                        tks_df["service_x"] == tks_df["service_y"], "relation"
                    ] = "intra"
                    tks_df["clone_type"] = "TKS"

                    # TKSデータを統合
                    df = pd.concat([df, tks_df], ignore_index=True)
                    logger.info("Integrated %d TKS clone pairs", len(tks_df))

            except Exception as e:
                logger.warning("Failed to load TKS data: %s", e)

        # coord_pair列を作成
        logger.info("Computing coordinate pairs...")
        df["coord_pair"] = (
            df["file_id_x"].astype(str) + "_" + df["file_id_y"].astype(str)
        )

        # overlap_countとcoord_total_linesの計算
        logger.info("Computing overlap counts and total lines...")
        coord_counts = df["coord_pair"].value_counts()
        df["overlap_count"] = df["coord_pair"].map(coord_counts)
        df["total_lines"] = (df["end_line_x"] - df["start_line_x"] + 1) + (
            df["end_line_y"] - df["start_line_y"] + 1
        )
        coord_total_lines = df.groupby("coord_pair")["total_lines"].sum()
        df["coord_total_lines"] = df["coord_pair"].map(coord_total_lines)

        logger.info("Data processing completed. Shape: %s", df.shape)

        # 結果をキャッシュに保存
        result = (df, file_ranges, None)
        _data_cache[cache_key] = result

        return result
    except Exception as e:
        result = (None, None, f"Error loading no_imports JSON: {e}")
        _data_cache[cache_key] = result
        return result


def load_from_project_csv_with_rnr(
    project_csv_dir: str,
    ccfsw_csv_path: str,
    tks_csv_path: str,
    rnr_csv_path: str,
    services_json_path: str,
    cache_key: str,
    language: str,
):
    """プロジェクトベースCSVファイルからデータを読み込む（CCFSW、TKS、RNR統合）"""
    try:
        dfs = []
        ccfsw_df = None
        tks_df = None
        rnr_df = None

        # CCFSWデータの読み込み
        if os.path.exists(ccfsw_csv_path):
            logger.info("Loading CCFSW CSV: %s", ccfsw_csv_path)
            ccfsw_df = pd.read_csv(
                ccfsw_csv_path,
                dtype={
                    "file_id_x": "int32",
                    "file_id_y": "int32",
                    "start_line_x": "int32",
                    "end_line_x": "int32",
                    "start_line_y": "int32",
                    "end_line_y": "int32",
                    "clone_id": "int32",
                },
            )
            # clone_typeがない場合はNormalとして設定
            if "clone_type" not in ccfsw_df.columns:
                ccfsw_df["clone_type"] = "Normal"
            logger.info("CCFSW data loaded: %d rows", ccfsw_df.shape[0])

        # TKSデータの読み込み
        if os.path.exists(tks_csv_path):
            logger.info("Loading TKS CSV: %s", tks_csv_path)
            tks_df = pd.read_csv(
                tks_csv_path,
                dtype={
                    "file_id_x": "int32",
                    "file_id_y": "int32",
                    "start_line_x": "int32",
                    "end_line_x": "int32",
                    "start_line_y": "int32",
                    "end_line_y": "int32",
                    "clone_id": "int32",
                },
            )
            # clone_typeがない場合はTKSとして設定
            if "clone_type" not in tks_df.columns:
                tks_df["clone_type"] = "TKS"
            logger.info("TKS data loaded: %d rows", tks_df.shape[0])

        # RNRデータの読み込み
        if os.path.exists(rnr_csv_path):
            logger.info("Loading RNR CSV: %s", rnr_csv_path)
            rnr_df = pd.read_csv(
                rnr_csv_path,
                dtype={
                    "file_id_x": "int32",
                    "file_id_y": "int32",
                    "start_line_x": "int32",
                    "end_line_x": "int32",
                    "start_line_y": "int32",
                    "end_line_y": "int32",
                    "clone_id": "int32",
                },
            )
            # clone_typeがない場合はRNRとして設定
            if "clone_type" not in rnr_df.columns:
                rnr_df["clone_type"] = "RNR"
            logger.info("RNR data loaded: %d rows", rnr_df.shape[0])

        # データフレームが存在しない場合のエラーハンドリング
        if ccfsw_df is None and tks_df is None and rnr_df is None:
            raise FileNotFoundError(f"No valid CSV files found in {project_csv_dir}")

        # データ統合
        available_dfs = []
        if ccfsw_df is not None:
            available_dfs.append(ccfsw_df)
        if tks_df is not None:
            available_dfs.append(tks_df)
        if rnr_df is not None:
            available_dfs.append(rnr_df)

        # 統合
        df = pd.concat(available_dfs, ignore_index=True)
        logger.info("Integrated data: %d total rows", len(df))

        logger.info("Loading service file ranges...")
        file_ranges = load_service_file_ranges_cached(services_json_path, language)

        # 共通後処理（サービスマッピング、関係性、座標ペア、オーバーラップ）
        df = postprocess_clone_dataframe(df, file_ranges)

        logger.info("RNR-integrated data processing completed. Shape: %s", df.shape)

        # 結果をキャッシュに保存
        result = (df, file_ranges, None)
        _data_cache[cache_key] = result

        return result

    except Exception as e:
        result = (None, None, f"Error loading RNR-integrated CSV data: {e}")
        _data_cache[cache_key] = result
        return result


def load_from_project_csv(
    project_csv_dir: str,
    ccfsw_csv_path: str,
    tks_csv_path: str,
    services_json_path: str,
    cache_key: str,
    language: str,
):
    """プロジェクトベースCSVファイルからデータを読み込む（CCFSWとTKS最適化統合）"""
    try:
        dfs = []
        ccfsw_df = None
        tks_df = None

        # CCFSWデータの読み込み
        if os.path.exists(ccfsw_csv_path):
            logger.info("Loading CCFSW CSV: %s", ccfsw_csv_path)
            ccfsw_df = pd.read_csv(
                ccfsw_csv_path,
                dtype={
                    "file_id_x": "int32",
                    "file_id_y": "int32",
                    "start_line_x": "int32",
                    "end_line_x": "int32",
                    "start_line_y": "int32",
                    "end_line_y": "int32",
                    "clone_id": "int32",
                },
            )
            # clone_typeがない場合はNormalとして設定
            if "clone_type" not in ccfsw_df.columns:
                ccfsw_df["clone_type"] = "Normal"
            logger.info("CCFSW data loaded: %d rows", ccfsw_df.shape[0])

        # TKSデータの読み込み
        if os.path.exists(tks_csv_path):
            logger.info("Loading TKS CSV: %s", tks_csv_path)
            tks_df = pd.read_csv(
                tks_csv_path,
                dtype={
                    "file_id_x": "int32",
                    "file_id_y": "int32",
                    "start_line_x": "int32",
                    "end_line_x": "int32",
                    "start_line_y": "int32",
                    "end_line_y": "int32",
                    "clone_id": "int32",
                },
            )
            # clone_typeがない場合はTKSとして設定
            if "clone_type" not in tks_df.columns:
                tks_df["clone_type"] = "TKS"
            logger.info("TKS data loaded: %d rows", tks_df.shape[0])

        # データフレームが存在しない場合のエラーハンドリング
        if ccfsw_df is None and tks_df is None:
            raise FileNotFoundError(f"No valid CSV files found in {project_csv_dir}")

        # T047: データ品質検証とエラーハンドリング統合
        # CCFSW/TKSの内部重複除去と品質検証を実行
        try:
            from core.data_quality_validator import DataQualityValidator

            validator = DataQualityValidator()

            # CCFSW内部重複除去
            if ccfsw_df is not None:
                ccfsw_validation = validator.validate_ccfsw_data(ccfsw_df)
                ccfsw_df = ccfsw_validation["cleaned_data"]
                logger.info(
                    "CCFSW quality validation: %d -> %d rows (%.1f%% duplicates removed)",
                    ccfsw_validation["original_count"],
                    len(ccfsw_df),
                    ccfsw_validation["cleaning_stats"].get("removal_rate", 0),
                )

            # TKS内部重複除去
            if tks_df is not None:
                tks_validation = validator.validate_tks_data(tks_df)
                tks_df = tks_validation["cleaned_data"]
                logger.info(
                    "TKS quality validation: %d -> %d rows (%.1f%% duplicates removed)",
                    tks_validation["original_count"],
                    len(tks_df),
                    tks_validation["cleaning_stats"].get("removal_rate", 0),
                )

        except ImportError:
            logger.warning(
                "Data quality validator not available, skipping internal deduplication"
            )

        # T046: CCFSW/TKS間重複除去最適化
        if ccfsw_df is not None and tks_df is not None:
            # 両方存在する場合：CCFSW/TKS間の重複を分析して最適化
            try:
                from core.deduplication_optimizer import (
                    analyze_clone_overlap,
                    remove_duplicate_clones,
                )

                overlap_analysis = analyze_clone_overlap(ccfsw_df, tks_df)
                if overlap_analysis.get("significant_overlap", False):
                    # 重要な重複がある場合：CCFSWを優先してTKSから重複除去
                    df, dedup_stats = remove_duplicate_clones(
                        ccfsw_df, tks_df, strategy="keep_ccfsw"
                    )
                    logger.info(
                        "Inter-dataset deduplication: removed %d duplicates",
                        dedup_stats["removed_duplicates"],
                    )
                else:
                    # 重複が少ない場合：両方を統合
                    df = pd.concat([ccfsw_df, tks_df], ignore_index=True)
                    logger.info(
                        "Both datasets integrated: %d CCFSW + %d TKS = %d total",
                        len(ccfsw_df),
                        len(tks_df),
                        len(df),
                    )
            except ImportError:
                # フォールバック：単純統合
                df = pd.concat([ccfsw_df, tks_df], ignore_index=True)
                logger.info(
                    "Fallback integration: %d CCFSW + %d TKS = %d total",
                    len(ccfsw_df),
                    len(tks_df),
                    len(df),
                )
        elif ccfsw_df is not None:
            # CCFSWのみ（内部重複除去済み）
            df = ccfsw_df
            logger.info("Using cleaned CCFSW data: %d rows", len(df))
        else:
            # TKSのみ（内部重複除去済み）
            df = tks_df
            logger.info("Using cleaned TKS data: %d rows", len(df))

        # 統合完了後の処理

        logger.info("Loading service file ranges...")
        file_ranges = load_service_file_ranges_cached(services_json_path, language)

        # 共通後処理（サービスマッピング、関係性、座標ペア、オーバーラップ）
        df = postprocess_clone_dataframe(df, file_ranges)

        logger.info("Project-based data processing completed. Shape: %s", df.shape)

        # 結果をキャッシュに保存
        result = (df, file_ranges, None)
        _data_cache[cache_key] = result

        return result
    except Exception as e:
        result = (None, None, f"Error loading project CSV data: {e}")
        _data_cache[cache_key] = result
        return result


def load_from_csv_fallback(
    csv_path: str, services_json_path: str, cache_key: str, language: str
):
    """従来のCSVファイルからデータを読み込む（no_importsが利用できない場合のフォールバック）"""
    try:
        # CSVファイルの読み込み（高速化）
        logger.info("Loading CSV file...")
        df = pd.read_csv(
            csv_path,
            dtype={
                "file_id_x": "int32",
                "file_id_y": "int32",
                "start_line_x": "int32",
                "end_line_x": "int32",
                "start_line_y": "int32",
                "end_line_y": "int32",
                "clone_id": "int32",  # intに修正
            },
        )

        logger.info("Loading service file ranges...")
        file_ranges = load_service_file_ranges_cached(services_json_path, language)

        # 共通後処理（サービスマッピング、関係性、座標ペア、オーバーラップ）
        df = postprocess_clone_dataframe(df, file_ranges)

        logger.info("Data processing completed. Shape: %s", df.shape)

        # 結果をキャッシュに保存
        result = (df, file_ranges, None)
        _data_cache[cache_key] = result

        return result
    except Exception as e:
        result = (None, None, f"Error loading CSV data: {e}")
        _data_cache[cache_key] = result
        return result


def clear_data_cache():
    """データキャッシュをクリアする"""
    global _data_cache
    _data_cache.clear()
    # load_service_file_ranges_cached.cache_clear()  # lru_cache無効化のため一時的にコメントアウト
    logger.info("Data cache cleared.")
