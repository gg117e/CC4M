"""プロジェクト発見・列挙モジュール.

利用可能なプロジェクトや CSV ファイルを探索し,
ドロップダウン等 UI 用のオプションリストを生成する.
"""

import csv
import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from .csv_loader import SCATTER_FILE_COMMIT_PREFIX
from ..paths import (
    DEST_SCATTER,
    DEST_SERVICES_JSON,
    DEST_ENRICHED_FRAGMENTS,
    DEST_CSV,
    DEST_ANALYSIS_PARAMS,
    get_scatter_csv_dir,
    get_services_json_path,
    get_enriched_csv_dir,
    get_analysis_params_path,
)

logger = logging.getLogger(__name__)

# --- ラベル表示用マッピング ---
_DETECTION_LABELS = {
    "normal": "CCFinderSW (Normal)",
}

_FILTER_LABELS = {
    "filtered": "Import Filtered",
    "nofilter": "No Filter",
}

_ANALYSIS_LABELS = {
    "merge": "Merge Commit",
    "tag": "Tag",
}

_COMOD_LABELS = {
    "cloneset": "Clone Set",
    "clonepair": "Clone Pair",
}


def _build_descriptive_label(info: dict, *, include_project: bool = False) -> str:
    """CSVファイル情報から人間が読みやすいラベルを構築する.

    Args:
        info: _parse_scatter_csv_filename の戻り値.
        include_project: プロジェクト名をラベルに含めるか.

    Returns:
        説明的なラベル文字列.
    """
    language = str(info.get("language", ""))
    detection_raw = str(info.get("detection", "unknown"))
    filter_raw = str(info.get("filter", "unknown"))
    analysis_raw = str(info.get("analysis", "unknown"))
    min_tokens = info.get("min_tokens", "?")
    date_raw = str(info.get("date", ""))

    # TKS12 → "TKS (12)", RNR5 → "RNR (0.5)" etc.
    if detection_raw.lower().startswith("tks"):
        detection_label = f"TKS ({detection_raw[3:]})"
    elif detection_raw.lower().startswith("rnr"):
        detection_label = f"RNR ({detection_raw[3:]})"
    else:
        detection_label = _DETECTION_LABELS.get(detection_raw, detection_raw)

    filter_label = _FILTER_LABELS.get(filter_raw, filter_raw)

    # freq50 → "Frequency (50)"
    if analysis_raw.startswith("freq"):
        analysis_label = f"Frequency ({analysis_raw[4:]})"
    else:
        analysis_label = _ANALYSIS_LABELS.get(analysis_raw, analysis_raw)

    # 日付の書式を YYYYMMDD → YYYY/MM/DD に
    if len(date_raw) == 8 and date_raw.isdigit():
        date_label = f"{date_raw[:4]}/{date_raw[4:6]}/{date_raw[6:]}"
    else:
        date_label = date_raw

    parts: list[str] = []
    if include_project:
        parts.append(str(info.get("repo", info.get("project", ""))))
    parts.append(f"Language: {language}")
    parts.append(f"Detection: {detection_label}")
    parts.append(f"Filter: {filter_label}")
    parts.append(f"Analysis: {analysis_label}")
    parts.append(f"Min Tokens: {min_tokens}")

    if info.get("search_depth") is not None:
        parts.append(f"Search Depth: {info['search_depth']}")
    if info.get("max_analyzed_commits") is not None:
        parts.append(f"Max Commits: {info['max_analyzed_commits']}")

    parts.append(f"Date: {date_label}")

    return ", ".join(parts)


def load_project_summary(summary_path="src/visualize/project_summary.json"):
    """プロジェクトサマリーを読み込む"""
    if not os.path.exists(summary_path):
        return None
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Error loading project summary: %s", e)
        return None


def load_dashboard_data(scatter_dir="dest/scatter"):
    """ダッシュボード用のデータを読み込む"""
    dashboard_path = os.path.join(scatter_dir, "dashboard.json")
    if not os.path.exists(dashboard_path):
        return None

    try:
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Error loading dashboard data: %s", e)
        return None


def get_actual_service_count(project_name: str, language: str):
    """実際のservices.jsonからサービス数を取得する"""
    from .csv_loader import resolve_services_json_path

    services_json_path = resolve_services_json_path(project_name)
    if not services_json_path:
        return 0

    try:
        file_ranges = load_service_file_ranges_cached(services_json_path, language)
        return len(file_ranges) if file_ranges else 0
    except Exception as e:
        logger.warning("Could not get service count for %s: %s", project_name, e)
        return 0


def get_available_projects_enhanced(language_filter=None):
    """
    プロジェクトサマリーを利用して改善されたプロジェクト一覧を取得.

    Scatter CSV ベースのオプションに加え, services.json のみ存在する
    プロジェクトも含める.

    Args:
        language_filter: 特定の言語でフィルター（None=全言語）
    """
    scatter_options = _gather_scatter_projects()
    services_options = _gather_services_json_projects(language_filter)

    if scatter_options or services_options:
        # scatter で見つかったプロジェクト名を収集
        scatter_project_langs: set[tuple[str, str]] = set()
        for opt in scatter_options:
            if isinstance(opt, dict) and "project" in opt and "language" in opt:
                scatter_project_langs.add((opt["project"], opt["language"]))

        # services_json から scatter にないプロジェクトだけ追加
        merged = list(scatter_options)
        for opt in services_options:
            key = (opt.get("project", ""), opt.get("language", ""))
            if key not in scatter_project_langs:
                merged.append(opt)

        if merged:
            return sorted(merged, key=lambda o: o.get("label", ""))

    summary = load_project_summary()
    if not summary:
        logger.warning("Project summary not found. Using fallback method.")
        return get_available_projects()

    options = []

    for project_name, project_data in summary["projects"].items():
        metadata = project_data.get("metadata", {})

        for language, lang_data in project_data["languages"].items():
            # 言語フィルターがある場合、指定言語以外をスキップ
            if language_filter and language != language_filter:
                continue

            stats = lang_data["stats"]
            commit = lang_data.get("commit", "latest")

            # 表示用ラベルの作成
            base_display = f"{project_name} ({language})"
            if commit != "latest":
                base_display += f", {commit[:7]}"

            # 統計情報を表示に追加（実際のサービス数を使用）
            actual_service_count = get_actual_service_count(project_name, language)
            stats_info = []
            if stats.get("total_clones", 0) > 0:
                stats_info.append(f"{stats['total_clones']:,} clones")
            if actual_service_count > 0:
                stats_info.append(f"{actual_service_count} services")
            if metadata.get("stars", 0) > 0:
                stats_info.append(f"⭐{metadata['stars']}")

            display = base_display
            if stats_info:
                display += f" - {', '.join(stats_info)}"

            value = f"{project_name}|||{commit}|||{language}"

            option_data = {
                "label": display,
                "value": value,
                "project_name": project_name,
                "language": language,
                "commit": commit,
                "stats": stats,
                "metadata": metadata,
                "clone_count": stats.get("total_clones", 0),
            }
            options.append(option_data)

    if not options:
        logger.warning("No valid projects found in summary. Using fallback method.")
        return get_available_projects()

    # 常にクローン数で降順ソート
    options.sort(key=lambda x: x["clone_count"], reverse=True)

    # 言語別にグループ化（言語フィルターがない場合のみ）
    if not language_filter:
        grouped_options = []
        current_lang = None
        lang_options = []

        # まず言語でソートしてからクローン数でソート
        options.sort(key=lambda x: (x["language"], -x["clone_count"]))

        for option in options:
            if current_lang != option["language"]:
                if lang_options:
                    # 前の言語グループを追加
                    grouped_options.append(
                        {
                            "label": f"── {current_lang} ({len(lang_options)} projects) ──",
                            "value": f"HEADER_{current_lang}",
                            "disabled": True,
                        }
                    )
                    grouped_options.extend(lang_options)

                current_lang = option["language"]
                lang_options = []

            lang_options.append({"label": option["label"], "value": option["value"]})

        # 最後のグループを追加
        if lang_options:
            grouped_options.append(
                {
                    "label": f"── {current_lang} ({len(lang_options)} projects) ──",
                    "value": f"HEADER_{current_lang}",
                    "disabled": True,
                }
            )
            grouped_options.extend(lang_options)

        return grouped_options

    # 言語フィルターがある場合はグループ化なし
    return [{"label": opt["label"], "value": opt["value"]} for opt in options]


def get_available_languages():
    """利用可能な言語の一覧を取得"""
    langs: set[str] = set()

    scatter_options = _gather_scatter_projects()
    for opt in scatter_options:
        if (
            isinstance(opt, dict)
            and "value" in opt
            and not str(opt["value"]).startswith("HEADER_")
        ):
            parts = opt["value"].split("|||")
            if len(parts) >= 3:
                langs.add(parts[2])

    services_options = _gather_services_json_projects()
    for opt in services_options:
        if isinstance(opt, dict) and "language" in opt:
            langs.add(opt["language"])

    if langs:
        return sorted(langs)

    summary = load_project_summary()
    if summary:
        languages = set()
        for project_data in summary["projects"].values():
            languages.update(project_data["languages"].keys())
        return sorted(list(languages))

    return []


def get_available_projects():
    """利用可能なプロジェクトの一覧を取得する.

    優先順位: dest/scatter -> data/csv -> visualize/csv(legacy).
    """

    options = _gather_scatter_projects()
    if options:
        return options

    options.extend(_gather_project_csv_projects())
    options.extend(_gather_legacy_projects())

    seen = set()
    unique = [
        opt
        for opt in options
        if opt["value"] not in seen and not seen.add(opt["value"])
    ]
    return sorted(unique, key=lambda o: o["label"])


def get_project_names() -> list[dict]:
    """プロジェクト名の一覧を取得する (2段階選択の Step 1 用).

    以下のディレクトリを走査し, いずれかにデータがあるプロジェクトを列挙する:

    1. ``dest/scatter``
    2. ``dest/services_json``
    3. ``dest/enriched_fragments``
    4. ``dest/csv``

    Returns:
        プロジェクト名のドロップダウンオプション (label/value).
    """
    names: set[str] = set()

    # 1. dest/scatter からプロジェクト名を取得 (scatter CSV あり)
    if DEST_SCATTER.exists():
        for project_dir in DEST_SCATTER.iterdir():
            csv_dir = project_dir / "csv"
            if not csv_dir.is_dir():
                continue
            has_csv = any(
                p.is_file()
                and p.name.endswith(".csv")
                and not p.name.endswith("_unknown.csv")
                for p in csv_dir.iterdir()
            )
            if has_csv:
                names.add(project_dir.name)

    # 2. dest/services_json からプロジェクト名を取得
    if DEST_SERVICES_JSON.exists():
        for json_file in DEST_SERVICES_JSON.iterdir():
            if json_file.is_file() and json_file.suffix == ".json":
                names.add(json_file.stem)

    # 3. dest/enriched_fragments からプロジェクト名を取得
    if DEST_ENRICHED_FRAGMENTS.exists():
        for project_dir in DEST_ENRICHED_FRAGMENTS.iterdir():
            if project_dir.is_dir() and any(project_dir.glob("*.csv")):
                names.add(project_dir.name)

    # 4. dest/csv からプロジェクト名を取得
    if DEST_CSV.exists():
        for project_dir in DEST_CSV.iterdir():
            if project_dir.is_dir() and any(project_dir.glob("*.csv")):
                names.add(project_dir.name)

    return [{"label": name, "value": name} for name in sorted(names)]


def get_csv_options_for_project(project_name: str) -> list[dict]:
    """指定プロジェクトの可視化データ一覧を取得する (2段階選択の Step 2 用).

    Scatter CSV が存在するプロジェクトはファイル単位で列挙し,
    存在しないプロジェクトは enriched_fragments + services.json +
    analysis_params.json から言語単位のオプションを生成する.

    Args:
        project_name: プロジェクト名 (owner.repo 形式).

    Returns:
        ドロップダウンオプション (label/value).
            value は ``project|||scatter_file:<filename>|||language`` 形式
            または ``project|||latest|||language`` 形式.
    """
    # 1. Scatter CSV がある場合は従来通り
    csv_dir = get_scatter_csv_dir(project_name)
    if csv_dir.is_dir():
        options = _gather_csv_options_from_scatter(project_name, csv_dir)
        if options:
            return options

    # 2. enriched_fragments + services.json + analysis_params からオプション生成
    return _gather_options_from_enriched(project_name)


def _gather_csv_options_from_scatter(project_name: str, csv_dir: Path) -> list[dict]:
    """dest/scatter のCSVファイルからオプションリストを生成する."""
    options: list[dict] = []
    for csv_path in csv_dir.iterdir():
        if not csv_path.is_file() or not csv_path.name.endswith(".csv"):
            continue
        if csv_path.name.endswith("_unknown.csv"):
            continue

        info = _parse_scatter_csv_filename(csv_path.name)
        if info is None:
            continue

        language = str(info.get("language", ""))
        if not language:
            continue

        # Skip empty or header-only files
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                f.readline()  # header
                if not f.readline().strip():
                    continue
        except (OSError, UnicodeDecodeError, csv.Error) as e:
            logger.warning("Skipping unreadable CSV file %s: %s", csv_path, e)
            continue
        except Exception as e:
            raise RuntimeError(f"Failed to enumerate CSV file {csv_path}") from e

        file_size = csv_path.stat().st_size

        label = _build_descriptive_label(info)
        value = (
            f"{project_name}|||{SCATTER_FILE_COMMIT_PREFIX}{csv_path.name}|||{language}"
        )
        options.append(
            {
                "label": label,
                "value": value,
                "language": language,
                "date": str(info.get("date", "")),
                "size": file_size,
            }
        )

    options.sort(
        key=lambda item: (
            item.get("size", 0),
            item.get("language", ""),
            item.get("date", ""),
            item.get("label", ""),
        ),
        reverse=True,
    )
    return options


def _load_analysis_params(project_name: str) -> dict:
    """分析パラメータを読み込む.

    ``dest/analysis_params/{project_name}.json`` が存在しない場合は
    ``config.py`` のデフォルト値をフォールバックとして使用する.

    Returns:
        分析パラメータの辞書.
    """
    params_path = get_analysis_params_path(project_name)
    if params_path.is_file():
        try:
            data = json.loads(params_path.read_text(encoding="utf-8"))
            logger.debug("Loaded analysis_params from %s", params_path)
            return data
        except Exception as exc:
            logger.warning("Failed to read analysis_params %s: %s", params_path, exc)

    # config.py からのフォールバック
    try:
        import config as _cfg

        return {
            "detection_method": "normal",
            "min_tokens": 50,
            "import_filter": getattr(_cfg, "APPLY_IMPORT_FILTER", True),
            "comod_method": "clone_set",
            "analysis_method": getattr(_cfg, "ANALYSIS_METHOD", "merge_commit"),
            "analysis_frequency": getattr(_cfg, "ANALYSIS_FREQUENCY", 1),
            "search_depth": getattr(_cfg, "SEARCH_DEPTH", -1),
            "max_analyzed_commits": getattr(_cfg, "MAX_ANALYZED_COMMITS", -1),
        }
    except ImportError:
        logger.warning("config module not importable; using hard-coded defaults")
        return {
            "detection_method": "normal",
            "min_tokens": 50,
            "import_filter": True,
            "comod_method": "clone_set",
            "analysis_method": "merge_commit",
            "analysis_frequency": 1,
            "search_depth": -1,
            "max_analyzed_commits": -1,
        }


def _build_enriched_label(language: str, params: dict) -> str:
    """enriched_fragments 用の説明的ラベルを構築する.

    Scatter CSV 用の ``_build_descriptive_label`` と同じフォーマットに
    なるよう, 分析パラメータからラベル部品を組み立てる.

    Args:
        language: 対象プログラミング言語名.
        params: ``_load_analysis_params`` の戻り値.

    Returns:
        説明的なラベル文字列.
    """
    detection_raw = params.get("detection_method", "normal")
    if detection_raw.lower().startswith("tks"):
        detection_label = f"TKS ({detection_raw[3:]})"
    elif detection_raw.lower().startswith("rnr"):
        detection_label = f"RNR ({detection_raw[3:]})"
    else:
        detection_label = _DETECTION_LABELS.get(detection_raw, detection_raw)

    import_filter = params.get("import_filter", True)
    filter_label = "Import Filtered" if import_filter else "No Filter"

    analysis_raw = params.get("analysis_method", "merge_commit")
    freq = params.get("analysis_frequency", 1)
    if analysis_raw == "frequency":
        analysis_label = f"Frequency ({freq})"
    elif analysis_raw == "merge_commit":
        analysis_label = "Merge Commit"
    elif analysis_raw == "tag":
        analysis_label = "Tag"
    else:
        analysis_label = analysis_raw

    comod_raw = params.get("comod_method", "clone_set")
    comod_label = {
        "clone_set": "Clone Set",
        "clone_pair": "Clone Pair",
    }.get(comod_raw, comod_raw)

    min_tokens = params.get("min_tokens", 50)

    parts = [
        f"Language: {language}",
        f"Detection: {detection_label}",
        f"Filter: {filter_label}",
        f"Analysis: {analysis_label}",
        f"Comod: {comod_label}",
        f"Min Tokens: {min_tokens}",
    ]

    sd = params.get("search_depth")
    if sd is not None and sd != -1:
        parts.append(f"Search Depth: {sd}")
    mac = params.get("max_analyzed_commits")
    if mac is not None and mac != -1:
        parts.append(f"Max Commits: {mac}")

    return ", ".join(parts)


def _gather_options_from_enriched(project_name: str) -> list[dict]:
    """enriched_fragments と analysis_params から言語ごとのオプションを生成する.

    ``dest/enriched_fragments/{project_name}/`` を走査して利用可能な言語を
    取得し, ``_load_analysis_params`` でパラメータを読み込んで
    Scatter CSV と同等の説明的ラベルを構築する.

    enriched_fragments が存在しない場合は ``dest/csv/{project_name}/`` に
    フォールバックする.

    Args:
        project_name: プロジェクト名.

    Returns:
        ドロップダウン用オプションリスト. CSV が見つからない場合は空リスト.
    """
    # 言語を探索: enriched_fragments → dest/csv → services.json の順
    languages: list[str] = []
    for search_dir in (
        get_enriched_csv_dir(project_name),
        DEST_CSV / project_name,
    ):
        if search_dir.is_dir():
            for csv_path in sorted(search_dir.iterdir()):
                if not csv_path.is_file() or csv_path.suffix != ".csv":
                    continue
                # ファイル名: {filter_prefix}{language}.csv
                # filter_prefix は "filtered_" or "" (空)
                stem = csv_path.stem
                lang = stem.removeprefix("filtered_")
                if lang and lang not in languages:
                    languages.append(lang)
            if languages:
                break

    # CSV ディレクトリに何もなければ services.json の language_stats から言語を取得
    if not languages:
        sj_path = get_services_json_path(project_name)
        if sj_path.is_file():
            try:
                sj_data = json.loads(sj_path.read_text(encoding="utf-8"))
                languages = sorted(sj_data.get("language_stats", {}).keys())
            except Exception:
                pass

    if not languages:
        return []

    params = _load_analysis_params(project_name)
    options: list[dict] = []
    for language in languages:
        label = _build_enriched_label(language, params)
        value = f"{project_name}|||latest|||{language}"
        options.append(
            {
                "label": label,
                "value": value,
                "language": language,
            }
        )

    options.sort(key=lambda item: item.get("language", ""))
    return options


def _gather_services_json_projects(language_filter=None):
    """dest/services_json からプロジェクト・言語のオプションを生成する.

    services.json に ``language_stats`` が含まれるプロジェクトを対象とし,
    analysis_params.json / config.py の分析パラメータで説明的ラベルを付与する.
    """
    if not DEST_SERVICES_JSON.exists():
        return []

    options = []
    for json_file in sorted(DEST_SERVICES_JSON.iterdir()):
        if not json_file.is_file() or json_file.suffix != ".json":
            continue

        project_name = json_file.stem
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        lang_stats = data.get("language_stats", {})
        if not lang_stats:
            continue

        params = _load_analysis_params(project_name)
        for language in sorted(lang_stats):
            if language_filter and language != language_filter:
                continue

            label = f"{project_name}, {_build_enriched_label(language, params)}"
            value = f"{project_name}|||latest|||{language}"
            options.append(
                {
                    "label": label,
                    "value": value,
                    "project": project_name,
                    "language": language,
                }
            )

    return options


def _gather_scatter_projects():
    if not DEST_SCATTER.exists():
        return []

    options = []

    for project_dir in sorted(DEST_SCATTER.iterdir()):
        csv_dir = project_dir / "csv"
        if not csv_dir.is_dir():
            continue

        file_options = []
        for csv_path in csv_dir.iterdir():
            if not csv_path.is_file() or not csv_path.name.endswith(".csv"):
                continue

            if csv_path.name.endswith("_unknown.csv"):
                continue

            info = _parse_scatter_csv_filename(csv_path.name)
            if info is None:
                continue

            language = str(info.get("language", ""))
            if not language:
                continue

            # Skip empty or header-only files
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    f.readline()  # header
                    if not f.readline().strip():
                        continue
            except (OSError, UnicodeDecodeError, csv.Error) as e:
                logger.warning("Skipping unreadable CSV file %s: %s", csv_path, e)
                continue
            except Exception as e:
                raise RuntimeError(f"Failed to enumerate CSV file {csv_path}") from e

            file_size = csv_path.stat().st_size

            info["project"] = project_dir.name
            label = _build_descriptive_label(info, include_project=True)
            value = f"{project_dir.name}|||{SCATTER_FILE_COMMIT_PREFIX}{csv_path.name}|||{language}"
            file_options.append(
                {
                    "label": label,
                    "value": value,
                    "project": project_dir.name,
                    "language": language,
                    "date": str(info.get("date", "")),
                }
            )

        file_options.sort(
            key=lambda item: (
                item.get("project", ""),
                item.get("language", ""),
                item.get("date", ""),
                item.get("label", ""),
            ),
            reverse=True,
        )
        options.extend(file_options)

    return sorted(options, key=lambda o: o["label"])


def _parse_scatter_csv_filename(filename: str) -> dict | None:
    """散布図CSVファイル名を解析する.

    期待形式:
        {repo}_{detection}_{min_tokens}_{filter}_{comod}_{analysis}_{date}[_{sd...}][_{mac...}]_{language}.csv

    互換のため `sd/mac` が `date` の前後どちらにあっても許容する.
    """

    stem = filename.removesuffix(".csv")
    parts = stem.split("_")
    if len(parts) < 8:
        return None

    language = parts[-1]
    core = parts[:-1]

    detection_idx = None
    for i, token in enumerate(core):
        if re.fullmatch(r"normal|TKS\d+|RNR\d+", token):
            detection_idx = i
            break
    if detection_idx is None:
        return None

    if len(core) <= detection_idx + 5:
        return None

    repo = "_".join(core[:detection_idx])
    detection = core[detection_idx]
    min_tokens_token = core[detection_idx + 1]
    filter_token = core[detection_idx + 2]
    comod_token = core[detection_idx + 3]
    analysis_token = core[detection_idx + 4]
    tail_tokens = core[detection_idx + 5 :]

    if not repo:
        return None
    if not min_tokens_token.isdigit():
        return None
    if filter_token not in {"filtered", "nofilter"}:
        return None
    if comod_token not in {"cloneset", "clonepair"}:
        return None
    if not re.fullmatch(r"merge|tag|freq\d+", analysis_token):
        return None

    date_token = None
    search_depth = None
    max_analyzed_commits = None
    for token in tail_tokens:
        if re.fullmatch(r"\d{8}", token):
            date_token = token
        elif re.fullmatch(r"sd\d+", token):
            search_depth = int(token[2:])
        elif re.fullmatch(r"mac\d+", token):
            max_analyzed_commits = int(token[3:])

    if date_token is None:
        return None

    return {
        "repo": repo,
        "detection": detection,
        "min_tokens": int(min_tokens_token),
        "filter": filter_token,
        "comod": comod_token,
        "analysis": analysis_token,
        "date": date_token,
        "search_depth": search_depth,
        "max_analyzed_commits": max_analyzed_commits,
        "language": language,
        "filename": filename,
    }


def _gather_project_csv_projects():
    csv_data_folder = Path("data/csv")
    options = []
    if not csv_data_folder.exists():
        return options

    for project_dir in csv_data_folder.iterdir():
        if not project_dir.is_dir():
            continue
        for csv_file in project_dir.glob("*.csv"):
            filename = csv_file.name
            name_parts = filename[:-4].split("_")
            if len(name_parts) != 2:
                continue
            detection_type, language = name_parts
            if detection_type not in ["ccfsw", "tks"]:
                continue
            display = (
                f"{project_dir.name} ({language.upper()}, {detection_type.upper()})"
            )
            value = f"{project_dir.name}|||latest|||{language.upper()}"
            options.append({"label": display, "value": value})
    return options


def _gather_legacy_projects():
    legacy_csv_folder = Path("src/visualize/csv")
    options = []
    if not legacy_csv_folder.exists():
        return options

    for csv_file in legacy_csv_folder.glob("*_all.csv"):
        base = csv_file.name[:-8]
        parts = base.split("_")
        if len(parts) < 3:
            continue
        language, commit, project = parts[-1], parts[-2], "_".join(parts[:-2])
        display = f"{project} ({language.upper()}, LEGACY)"
        value = f"{project}|||{commit}|||{language.upper()}"
        options.append({"label": display, "value": value})
    return options
