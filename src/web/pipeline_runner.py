"""パイプライン実行モジュール.

Web UIから起動される分析パイプラインの全ステップを管理する.
各ステップ: リポジトリクローン → コミット選定 → クローン検出 →
分析 → 同時修正分析 → 可視化CSV生成.
"""

import json
import logging
import shutil
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class LogCapture:
    """print() 出力をメモリバッファに蓄積し,WebSocket で読み取れるようにする."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.lines: list[str] = []

    def write(self, text: str) -> None:
        """テキストをバッファに追加する."""
        if text.strip():
            self.lines.append(text.rstrip("\n"))
        sys.__stdout__.write(text)

    def flush(self) -> None:
        """標準出力をフラッシュする."""
        sys.__stdout__.flush()


def _format_elapsed(seconds: float) -> str:
    from modules.collect_datas import _format_elapsed as _shared_format_elapsed

    return _shared_format_elapsed(seconds)


def _build_languages_dict(workdir: Path) -> dict:
    """run_github_linguist で取得した言語情報を project['languages'] 形式に変換する."""
    from modules.github_linguist import run_github_linguist
    from config import TARGET_PROGRAMING_LANGUAGES

    raw = run_github_linguist(str(workdir))
    return {
        lang: data for lang, data in raw.items() if lang in TARGET_PROGRAMING_LANGUAGES
    }


def _clear_previous_results(repo_name: str, project_root: Path) -> None:
    """過去の分析出力を削除する.

    Args:
        repo_name: リポジトリ識別子 (<owner>.<repo>).
        project_root: プロジェクトルートパス.
    """
    targets = [
        project_root / "dest/clones_json" / repo_name,
        project_root / "dest/modified_clones" / repo_name,
        project_root / "dest/moving_lines" / repo_name,
        project_root / "dest/csv" / repo_name,
        project_root / "dest/temp/ccfswtxt" / repo_name,
    ]
    for target in targets:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    analyzed_file = project_root / "dest/analyzed_commits" / f"{repo_name}.json"
    if analyzed_file.exists():
        analyzed_file.unlink()


def _save_analysis_params(
    name: str, params: dict, project_root: Path, log: LogCapture
) -> None:
    """分析パラメータを JSON として保存する.

    ``dest/analysis_params/{name}.json`` に保存される.
    プロジェクト発見時にラベル構築に使用する.
    """
    params_dir = project_root / "dest/analysis_params"
    params_dir.mkdir(parents=True, exist_ok=True)
    params_path = params_dir / f"{name}.json"

    # 保存対象のパラメータ (UIから渡される分析条件)
    save_data = {
        "detection_method": params.get("detection_method", "normal"),
        "min_tokens": params.get("min_tokens", 50),
        "import_filter": params.get("import_filter", True),
        "comod_method": params.get("comod_method", "clone_set"),
        "analysis_method": params.get("analysis_method", "merge_commit"),
        "analysis_frequency": params.get("analysis_frequency", 1),
        "search_depth": params.get("search_depth", -1),
        "max_analyzed_commits": params.get("max_analyzed_commits", -1),
    }
    try:
        params_path.write_text(
            json.dumps(save_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.write(f"  Saved analysis params: {params_path.name}\n")
    except Exception as exc:
        log.write(f"  [warn] Failed to save analysis params: {exc}\n")


def _generate_visualization_csv(
    *,
    project: dict,
    name: str,
    url: str,
    params: dict,
    workdir: Path,
    log: LogCapture,
    project_root: Path,
) -> None:
    """分析結果から可視化用CSV (散布図データセット) を生成する.

    Args:
        project: {"URL": ..., "languages": {...}} 形式のプロジェクト辞書.
        name: <owner>.<repo> 形式の識別子.
        url: GitHub リポジトリURL.
        params: Web UIで検証済みのパラメータ辞書.
        workdir: ローカルリポジトリのパス.
        log: ログ出力先.
        project_root: プロジェクトルートパス.
    """
    languages = project.get("languages", {})
    if not languages:
        log.write("  No languages found, skipping visualization CSV.\n")
        return

    # ms_detection の実行 (JSON キャッシュがあればスキップ)
    ms_detection_dir = project_root / "dest/ms_detection"
    ms_detection_dir.mkdir(parents=True, exist_ok=True)
    services_json_dir = project_root / "dest/services_json"
    services_json_path = services_json_dir / f"{name}.json"

    if services_json_path.exists():
        log.write("  Services JSON cache found, skipping ms_detection.\n")
    else:
        log.write("  Running microservice detection (snapshot mode)...\n")
        import modules.identify_microservice

        modules.identify_microservice.analyze_repo_snapshot(url, name, str(workdir))
        if not services_json_path.exists():
            log.write(
                "  [warn] services JSON was not generated, "
                "no docker-compose found?\n"
            )
            return

    # 命名規則に基づくファイル名の生成
    from modules.visualization.naming import (
        build_visualization_csv_filename_from_params,
    )

    csv_stem = build_visualization_csv_filename_from_params(params)
    out_dir = project_root / "dest/scatter"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Web UIではimportフィルタは実行時にソースに適用済みのため,
    # 入力CSVは常にフィルタなし名 (<language>.csv) で格納されている.
    filter_type: str | None = None

    generate_scatter = params.get("generate_scatter_csv", True)

    if generate_scatter:
        generated_count = 0
        for language in languages.keys():
            try:
                log.write(f"  Generating scatter CSV: language={language}...\n")
                from modules.visualization.build_scatter_dataset import (
                    build_scatter_dataset_for_language,
                )

                resolved_path, unknown_path = build_scatter_dataset_for_language(
                    project=project,
                    project_name=name,
                    language=language,
                    filter_type=filter_type,
                    project_root=project_root,
                    out_dir=out_dir,
                    ms_detection_dir=ms_detection_dir,
                    output_csv_stem=f"{csv_stem}_{language}",
                )
                generated_count += 1
                log.write(f"  Done: {resolved_path.name}\n")
            except FileNotFoundError as exc:
                log.write(f"  [warn] Skip scatter CSV (missing input): {exc}\n")
            except Exception as exc:
                log.write(f"  [warn] Failed scatter CSV for {language}: {exc}\n")

        log.write(
            f"  Generated {generated_count}/{len(languages)} visualization CSVs.\n"
        )
    else:
        log.write("  Scatter CSV generation skipped (disabled by user).\n")

    # enriched_fragments.csv 生成 + services.json 拡充
    enriched_dir = project_root / "dest/enriched_fragments"
    enriched_dir.mkdir(parents=True, exist_ok=True)
    enriched_count = 0
    for language in languages.keys():
        try:
            log.write(f"  Generating enriched fragments: language={language}...\n")
            from modules.visualization.build_enriched_fragments import (
                build_enriched_fragments_for_language,
            )

            enriched_path = build_enriched_fragments_for_language(
                project_name=name,
                language=language,
                filter_type=filter_type,
                project_root=project_root,
                out_dir=enriched_dir,
                ms_detection_dir=ms_detection_dir,
            )
            enriched_count += 1
            log.write(f"  Done: {enriched_path.name}\n")
        except FileNotFoundError as exc:
            log.write(f"  [warn] Skip enriched fragments (missing input): {exc}\n")
        except Exception as exc:
            log.write(f"  [warn] Failed enriched fragments for {language}: {exc}\n")

    log.write(
        f"  Generated {enriched_count}/{len(languages)} enriched fragment CSVs.\n"
    )

    # クローンメトリクス JSON 生成
    metrics_dir = project_root / "dest/clone_metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_count = 0
    csv_prefix = f"{filter_type}_" if filter_type else ""
    for language in languages.keys():
        try:
            enriched_csv = enriched_dir / name / f"{csv_prefix}{language}.csv"
            services_json = project_root / "dest/services_json" / f"{name}.json"
            if not enriched_csv.exists():
                log.write(
                    f"  [warn] Skip metrics (enriched CSV not found): {enriched_csv}\n"
                )
                continue
            if not services_json.exists():
                log.write(
                    f"  [warn] Skip metrics (services.json not found): {services_json}\n"
                )
                continue

            log.write(f"  Computing clone metrics: language={language}...\n")
            from modules.visualization.compute_clone_metrics import (
                compute_all_metrics,
            )

            metrics = compute_all_metrics(enriched_csv, services_json, language)

            import json as _json

            metrics_path = metrics_dir / f"{name}_{language}.json"
            metrics_path.write_text(
                _json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            metrics_count += 1
            log.write(f"  Done: {metrics_path.name}\n")
        except Exception as exc:
            log.write(f"  [warn] Failed clone metrics for {language}: {exc}\n")

    log.write(f"  Generated {metrics_count}/{len(languages)} clone metrics JSONs.\n")


def run_job(
    job_id: str,
    params: dict,
    *,
    jobs: dict,
    stdout_proxy: object,
    project_root: Path,
) -> None:
    """分析パイプラインをバックグラウンドスレッドで実行する.

    Args:
        job_id: ジョブ識別子.
        params: 検証済みパラメータ辞書.
        jobs: ジョブ状態を格納する辞書 (共有).
        stdout_proxy: ThreadLocalStdoutProxy インスタンス.
        project_root: プロジェクトルートパス.
    """
    import traceback

    job = jobs[job_id]
    log = LogCapture(job_id)
    job["log"] = log
    with stdout_proxy.redirect(log):
        try:
            url: str = params["url"]
            name = url.split("/")[-2] + "." + url.split("/")[-1]
            job["status"] = "running"
            log.write(f"[job] Starting analysis for {url}\n")

            detection_method: str = params.get("detection_method", "normal")
            if detection_method != "normal":
                log.write(f"[error] Unsupported detection_method: {detection_method}\n")
                job["status"] = "error"
                return

            comod_method: str = params.get("comod_method", "clone_set")
            if comod_method != "clone_set":
                log.write(f"[error] Unsupported comod_method: {comod_method}\n")
                job["status"] = "error"
                return

            force_recompute = bool(params.get("force_recompute", True))
            if force_recompute:
                log.write(
                    "[job] Clearing previous results to apply selected filters.\n"
                )
                _clear_previous_results(name, project_root)

            # ------------------------------------------------------------------
            # 1. Clone repository
            # ------------------------------------------------------------------
            log.write("[step 1/6] Cloning repository...\n")
            import modules.clone_repo

            modules.clone_repo.clone_repo(url)
            workdir = project_root / "dest/projects" / name

            # ------------------------------------------------------------------
            # 2. Determine analysed commits  (overriding config values at runtime)
            # ------------------------------------------------------------------
            log.write("[step 2/6] Determining analysed commits...\n")
            analysis_method: str = params.get("analysis_method", "merge_commit")
            search_depth: int = int(params.get("search_depth", -1))
            max_commits: int = int(params.get("max_analyzed_commits", -1))
            frequency: int = int(params.get("analysis_frequency", 1))

            # Temporarily patch the config values used by determine_analyzed_commits
            import config as _cfg
            from commands.pipeline import determine_analyzed_commits as dac

            _orig_method = _cfg.ANALYSIS_METHOD
            _orig_depth = _cfg.SEARCH_DEPTH
            _orig_max = _cfg.MAX_ANALYZED_COMMITS
            _orig_freq = _cfg.ANALYSIS_FREQUENCY
            _cfg.ANALYSIS_METHOD = analysis_method
            _cfg.SEARCH_DEPTH = search_depth
            _cfg.MAX_ANALYZED_COMMITS = max_commits
            _cfg.ANALYSIS_FREQUENCY = frequency
            # Also patch the module that already imported them
            dac.ANALYSIS_METHOD = analysis_method
            dac.SEARCH_DEPTH = search_depth
            dac.MAX_ANALYZED_COMMITS = max_commits
            dac.ANALYSIS_FREQUENCY = frequency

            try:
                if analysis_method == "merge_commit":
                    target_commits = dac.determine_analyzed_commits_by_mergecommits(
                        workdir
                    )
                elif analysis_method == "tag":
                    target_commits = dac.determine_by_tag(workdir)
                elif analysis_method == "frequency":
                    target_commits = dac.determine_by_frequency(workdir)
                else:
                    target_commits = dac.determine_analyzed_commits_by_mergecommits(
                        workdir
                    )
            finally:
                _cfg.ANALYSIS_METHOD = _orig_method
                _cfg.SEARCH_DEPTH = _orig_depth
                _cfg.MAX_ANALYZED_COMMITS = _orig_max
                _cfg.ANALYSIS_FREQUENCY = _orig_freq

            if not target_commits:
                log.write("[error] No target commits found.\n")
                job["status"] = "error"
                return

            log.write(f"  Found {len(target_commits)} target commits.\n")
            analyzed_commits_dir = project_root / "dest/analyzed_commits"
            analyzed_commits_dir.mkdir(parents=True, exist_ok=True)
            with open(analyzed_commits_dir / f"{name}.json", "w") as f:
                json.dump(target_commits, f)

            # Build a project dict compatible with existing modules
            languages = _build_languages_dict(workdir)
            project = {"URL": url, "languages": languages}

            # ------------------------------------------------------------------
            # 3. Collect data (clone detection + moving lines)
            # ------------------------------------------------------------------
            log.write("[step 3/6] Collecting clone data...\n")
            clone_collection_start = time.perf_counter()

            # Runtime options for collect/detect
            min_tokens: int = int(params.get("min_tokens", 50))
            use_import_filter: bool = params.get("import_filter", True)
            import modules.collect_datas

            modules.collect_datas.collect_datas_of_repo(
                project,
                apply_import_filter=use_import_filter,
                min_tokens=min_tokens,
                log=log,
            )
            log.write(
                "[step 3/6] Clone data collection completed in "
                f"{_format_elapsed(time.perf_counter() - clone_collection_start)}.\n"
            )

            # ------------------------------------------------------------------
            # 4. Analyse code clones
            # ------------------------------------------------------------------
            log.write("[step 4/6] Analysing code clones...\n")
            import modules.analyze_cc

            modules.analyze_cc.analyze_repo(project)

            # ------------------------------------------------------------------
            # 5. Analyse co-modification
            # ------------------------------------------------------------------
            log.write("[step 5/6] Analysing co-modification...\n")
            import modules.analyze_modification

            modules.analyze_modification.analyze_repo(project)

            # ------------------------------------------------------------------
            # 6. Generate visualization CSV
            # ------------------------------------------------------------------
            log.write("[step 6/6] Generating visualization CSV...\n")
            try:
                _generate_visualization_csv(
                    project=project,
                    name=name,
                    url=url,
                    params=params,
                    workdir=workdir,
                    log=log,
                    project_root=project_root,
                )
            except Exception as exc:
                # 可視化CSV生成の失敗は全体を止めない
                log.write(f"[warn] Visualization CSV generation failed: {exc}\n")

            log.write("[job] All steps completed successfully.\n")

            # 分析パラメータを保存 (プロジェクト発見時に参照)
            _save_analysis_params(name, params, project_root, log)

            job["status"] = "completed"

        except Exception as exc:
            log.write(f"[error] {exc}\n")
            log.write(traceback.format_exc() + "\n")
            job["status"] = "error"
