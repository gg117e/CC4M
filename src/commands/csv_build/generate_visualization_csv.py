"""可視化用データ（散布図CSV, services.json）を一括生成するCLI.

使い方:
    python commands/generate_visualization_data.py \
        --dataset-file dataset/selected_projects.json \
        --output-dir dest/scatter \
        --filter-type all

仕様:
- 散布図用CSVの生成 (modules.build_scatter_dataset)
- サービス情報JSONの生成 (modules.build_services_json)
- ダッシュボード用JSONの生成
- filter-type=all のとき import/tks の全てのCSVを生成し、services.json に統計を含める.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from config import SELECTED_DATASET
from modules.visualization.build_scatter_dataset import (
    build_scatter_dataset_for_language,
)
from modules.visualization.build_enriched_fragments import (
    build_enriched_fragments_for_language,
)
import modules.visualization.logger_setup as logger_setup
from modules.identify_microservice import analyze_repo

logger = logging.getLogger(__name__)

# filter_type の選択肢.
# None=フィルタなし, "import"=import行除外, "tks"=TKSフィルタ.
FILTER_MODES: dict[str, list[str | None]] = {
    "all": [None, "import", "tks"],
    "import": ["import"],
    "tks": ["tks"],
    "none": [None],
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    """コマンドライン引数をパースする."""

    parser = argparse.ArgumentParser(
        description="Generate visualization data (scatter CSVs & services.json)."
    )
    parser.add_argument(
        "--dataset-file",
        type=Path,
        default=SELECTED_DATASET,
        help="selected_projects.json のパス（デフォルト: config.SELECTED_DATASET）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "dest/scatter",
        help="出力ディレクトリ（デフォルト: dest/scatter）",
    )
    parser.add_argument(
        "--clones-dir",
        type=Path,
        default=project_root / "dest/clones_json",
        help="クローン情報のディレクトリ（デフォルト: dest/clones_json）",
    )
    parser.add_argument(
        "--ms-detection-dir",
        type=Path,
        default=project_root / "dest/ms_detection",
        help="マイクロサービス検出結果のディレクトリ（デフォルト: dest/ms_detection）",
    )
    parser.add_argument(
        "--filter-type",
        choices=list(FILTER_MODES.keys()),
        default="import",
        help="生成するフィルタ種別（default: all）",
    )
    parser.add_argument(
        "--projects",
        nargs="*",
        default=None,
        help="対象プロジェクト名（<owner>.<repo>）を指定. 省略時は dest/analyzed_commits から自動選択.",
    )
    parser.add_argument(
        "--skip-csv",
        action="store_true",
        help="CSV生成をスキップし、JSON生成のみを行う",
    )
    return parser.parse_args(argv)


def load_target_project_names(
    *, project_root: Path, explicit: list[str] | None
) -> list[str]:
    """対象プロジェクト名一覧を取得する."""
    if explicit:
        return [p for p in explicit if p]

    analyzed_dir = project_root / "dest/analyzed_commits"
    if not analyzed_dir.exists():
        return []
    return sorted([p.stem for p in analyzed_dir.glob("*.json") if p.is_file()])


def load_dataset(dataset_path: Path) -> dict[str, dict[str, Any]]:
    """データセットをロードし、プロジェクト名をキーにした辞書を返す."""
    if not dataset_path.exists():
        raise FileNotFoundError(f"dataset file not found: {dataset_path}")
    try:
        data = json.loads(dataset_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid dataset json: {dataset_path}") from e

    result: dict[str, dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict) or "URL" not in item:
            continue
        url = str(item["URL"]).rstrip("/").split("/")
        if len(url_parts := url) >= 2:
            name = f"{url_parts[-2]}.{url_parts[-1]}"
            result[name] = item
    return result


def ensure_ms_detection_csv(
    *,
    project_name: str,
    project_def: Mapping[str, Any],
    project_root: Path,
    ms_detection_dir: Path,
) -> Path:
    """対象プロジェクトの ms_detection CSV を確実に作成する."""

    ms_detection_dir.mkdir(parents=True, exist_ok=True)
    output_csv = ms_detection_dir / f"{project_name}.csv"

    url = str(project_def.get("URL") or "").strip()
    if not url:
        raise ValueError(f"missing project URL. project={project_name}")

    workdir = project_root / "dest/projects" / project_name
    if not workdir.exists() or not workdir.is_dir():
        raise FileNotFoundError(
            f"local repo not found for ms_detection: {workdir}. run data collection pipeline first"
        )

    try:
        logger.info(
            "start ms_detection (rebuild): project=%s repo_dir=%s",
            project_name,
            workdir,
        )
        analyze_repo(url, project_name, str(workdir))
    except Exception as e:
        raise RuntimeError(
            f"failed to generate ms_detection csv. project={project_name}, url={url}, repo_dir={workdir}"
        ) from e

    if not output_csv.exists():
        raise FileNotFoundError(f"ms_detection csv was not generated: {output_csv}")

    logger.info("done ms_detection: project=%s path=%s", project_name, output_csv)
    return output_csv


def main(argv: list[str]) -> int:
    """エントリポイント."""
    args = parse_args(argv)

    # ロガーの設定: ファイル出力と標準出力の両方を行う
    # modules.logger_setup.setup_logger はファイル出力専用のロガーを返すが、
    # ここでは既存の logging の仕組みに乗せるため、ルートロガーにハンドラを追加する形をとる

    # まず標準出力の設定
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    # ファイル出力の設定を追加
    script_name = Path(__file__).stem
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = log_dir / f"{timestamp}_{script_name}.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)

    logging.getLogger().addHandler(file_handler)

    project_defs = load_dataset(args.dataset_file)
    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # フィルタタイプの決定
    filter_types = FILTER_MODES[args.filter_type]

    target_names = load_target_project_names(
        project_root=project_root, explicit=args.projects
    )
    if not target_names:
        logger.warning("no target projects found.")
        return 0

    logger.info(
        "targets: projects=%d filter_type=%s output_dir=%s",
        len(target_names),
        args.filter_type,
        out_dir,
    )

    dashboard_data = {"metrics": {}, "detailed_stats": {}}

    for project_index, project_name in enumerate(target_names, start=1):
        project_start = time.perf_counter()
        project_def = project_defs.get(project_name)
        if not project_def:
            logger.warning(
                "skip (project not found in dataset): project=%s", project_name
            )
            continue

        languages = project_def.get("languages")
        if not isinstance(languages, dict) or not languages:
            logger.warning("skip (no languages): project=%s", project_name)
            continue

        ensure_ms_detection_csv(
            project_name=project_name,
            project_def=project_def,
            project_root=project_root,
            ms_detection_dir=args.ms_detection_dir,
        )

        logger.info(
            "start project: %d/%d project=%s languages=%d",
            project_index,
            len(target_names),
            project_name,
            len(languages),
        )

        # 1. CSV生成 (Scatter Dataset)
        if not args.skip_csv:
            for language in languages.keys():
                for filter_type in filter_types:
                    try:
                        task_start = time.perf_counter()
                        logger.info(
                            "start scatter csv: project=%s language=%s filter=%s",
                            project_name,
                            language,
                            filter_type,
                        )
                        build_scatter_dataset_for_language(
                            project=project_def,
                            project_name=project_name,
                            language=language,
                            filter_type=filter_type,
                            project_root=project_root,
                            out_dir=out_dir,
                            ms_detection_dir=args.ms_detection_dir,
                        )
                        logger.info(
                            "done scatter csv: project=%s language=%s filter=%s elapsed=%.1fs",
                            project_name,
                            language,
                            filter_type,
                            time.perf_counter() - task_start,
                        )
                    except FileNotFoundError as e:
                        logger.warning("skip scatter csv (missing input): %s", e)
                        continue
                    except Exception as e:
                        logger.error("failed scatter csv: %s", e, exc_info=True)
                        continue
        else:
            logger.info("skip scatter csv (requested by --skip-csv)")

        # 2. Enriched Fragments CSV 生成 + services.json 拡充
        if not args.skip_csv:
            enriched_dir = project_root / "dest/enriched_fragments"
            enriched_dir.mkdir(parents=True, exist_ok=True)
            for language in languages.keys():
                for filter_type in filter_types:
                    try:
                        task_start = time.perf_counter()
                        logger.info(
                            "start enriched fragments: project=%s language=%s filter=%s",
                            project_name,
                            language,
                            filter_type,
                        )
                        build_enriched_fragments_for_language(
                            project_name=project_name,
                            language=language,
                            filter_type=filter_type,
                            project_root=project_root,
                            out_dir=enriched_dir,
                            ms_detection_dir=args.ms_detection_dir,
                        )
                        logger.info(
                            "done enriched fragments: project=%s language=%s filter=%s elapsed=%.1fs",
                            project_name,
                            language,
                            filter_type,
                            time.perf_counter() - task_start,
                        )
                    except FileNotFoundError as e:
                        logger.warning("skip enriched fragments (missing input): %s", e)
                        continue
                    except Exception as e:
                        logger.error("failed enriched fragments: %s", e, exc_info=True)
                        continue

        # 3. JSON生成 (Services JSON) — services.json は enriched fragments 生成時に拡充済み
        logger.info("services json enrichment done (via enriched fragments step)")

        # 4. クローンメトリクス JSON 生成
        if not args.skip_csv:
            metrics_dir = project_root / "dest/clone_metrics"
            metrics_dir.mkdir(parents=True, exist_ok=True)
            for language in languages.keys():
                for filter_type in filter_types:
                    try:
                        task_start = time.perf_counter()
                        ef_prefix = f"{filter_type}_" if filter_type else ""
                        enriched_csv = (
                            project_root
                            / "dest/enriched_fragments"
                            / project_name
                            / f"{ef_prefix}{language}.csv"
                        )
                        services_json = (
                            project_root / "dest/services_json" / f"{project_name}.json"
                        )
                        if not enriched_csv.exists():
                            logger.warning(
                                "skip clone metrics (enriched CSV not found): %s",
                                enriched_csv,
                            )
                            continue
                        if not services_json.exists():
                            logger.warning(
                                "skip clone metrics (services.json not found): %s",
                                services_json,
                            )
                            continue
                        logger.info(
                            "start clone metrics: project=%s language=%s filter=%s",
                            project_name,
                            language,
                            filter_type,
                        )
                        from modules.visualization.compute_clone_metrics import (
                            compute_all_metrics,
                        )

                        metrics = compute_all_metrics(
                            enriched_csv, services_json, language
                        )
                        metrics_path = metrics_dir / f"{project_name}_{language}.json"
                        metrics_path.write_text(
                            json.dumps(metrics, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        logger.info(
                            "done clone metrics: project=%s language=%s filter=%s elapsed=%.1fs",
                            project_name,
                            language,
                            filter_type,
                            time.perf_counter() - task_start,
                        )
                    except Exception as e:
                        logger.error("failed clone metrics: %s", e, exc_info=True)
                        continue

        logger.info(
            "done project: %d/%d project=%s elapsed=%.1fs",
            project_index,
            len(target_names),
            project_name,
            time.perf_counter() - project_start,
        )

    # 3. Dashboard JSON生成
    dashboard_path = out_dir / "dashboard.json"
    try:
        dashboard_path.write_text(
            json.dumps(dashboard_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"Generated {dashboard_path}")
    except Exception as e:
        logger.error(f"Failed to generate dashboard.json: {e}")

    return 0


if __name__ == "__main__":
    start_time = time.time()
    # 既存のlogger設定と競合しないように、ファイル出力用ロガーを別途設定するか、
    # あるいは既存のlogger設定の前にファイルハンドラを追加する形にする。
    # ここでは modules.logger_setup を使ってファイル出力を追加する。
    file_logger = logger_setup.setup_logger(__file__)
    # 既存のloggerにもファイルハンドラを追加したい場合は、setup_loggerの実装を調整する必要があるが、
    # 今回はシンプルに file_logger を使って開始/終了を記録し、
    # main処理中のログは既存の logging.basicConfig (標準出力) に任せる形とする。
    # ただし、main関数内で logging.basicConfig が呼ばれているため、
    # ファイルにもログを出したい場合は main 関数呼び出し前に設定する必要がある。

    # setup_logger はルートロガーではなく独自ロガーを返すため、
    # main関数内の logger (logging.getLogger(__name__)) とは別物になる可能性がある。
    # しかし、generate_visualization_data.py は logging.basicConfig を使っているため、
    # ここではシンプルに実行時間の記録用として file_logger を使う。

    file_logger.info("Start execution")

    try:
        ret = main(sys.argv[1:])
        logger_setup.log_execution_time(file_logger, start_time)
        raise SystemExit(ret)
    except Exception as e:
        file_logger.error("An error occurred", exc_info=True)
        logger_setup.log_execution_time(file_logger, start_time)
        raise
