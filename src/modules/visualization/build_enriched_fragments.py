"""enriched_fragments.csv を生成する.

断片CSV を読み込み, サービス解決・ファイル情報を付加して,
メトリクス計算に適した **フラグメント粒度** の中間データを出力する.

scatter CSV がクローンペア (O(n²)) に展開するのに対し,
本モジュールは断片をそのまま 1 行 = 1 フラグメントで出力する (O(n)).

出力カラム::

    clone_id, fragment_index, file_path, file_id, service,
    start_line, end_line, line_count, file_type,
    modified_commits (JSON), modified_count

出力先::

    dest/enriched_fragments/<project>/<filter_prefix><language>.csv
"""

from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from modules.util import FileMapper, get_file_type
from modules.visualization.build_scatter_dataset import (
    FragmentRow,
    iter_fragment_groups,
    normalize_file_path,
    parse_modified_commits,
    safe_get_file_id,
)
from modules.visualization.service_mapping import (
    ServiceContext,
    load_claim_service_contexts_for_repo,
    load_service_contexts_from_json,
    resolve_service_for_file_path,
)

logger = logging.getLogger(__name__)

_HEADER = [
    "clone_id",
    "fragment_index",
    "file_path",
    "file_id",
    "service",
    "start_line",
    "end_line",
    "line_count",
    "file_type",
    "modified_commits",
    "modified_count",
]


@dataclass(frozen=True)
class EnrichedFragment:
    """enriched_fragments.csv の 1 行."""

    clone_id: str
    fragment_index: int
    file_path: str
    file_id: int
    service: str
    start_line: int
    end_line: int
    line_count: int
    file_type: str
    modified_commits: str  # JSON array of commit hashes
    modified_count: int


def build_enriched_fragment(
    frag: FragmentRow,
    *,
    norm_path: str,
    service: str,
    file_id: int,
    commits: set[str],
    file_type: str,
) -> EnrichedFragment:
    """FragmentRow から EnrichedFragment を構築する.

    Args:
        frag: 元の断片行.
        norm_path: 正規化済みファイルパス.
        service: 解決済みサービス名 (未解決なら空文字).
        file_id: clones_json 由来の file_id.
        commits: 修正コミットハッシュの集合.
        file_type: ファイル種別.

    Returns:
        EnrichedFragment.
    """
    return EnrichedFragment(
        clone_id=frag.clone_id,
        fragment_index=frag.index,
        file_path=norm_path,
        file_id=file_id,
        service=service,
        start_line=frag.start_line,
        end_line=frag.end_line,
        line_count=frag.end_line - frag.start_line + 1,
        file_type=file_type,
        modified_commits=json.dumps(sorted(commits)),
        modified_count=len(commits),
    )


def _write_row(writer: csv.writer, frag: EnrichedFragment) -> None:
    """EnrichedFragment を CSV に 1 行書き込む."""
    writer.writerow(
        [
            frag.clone_id,
            frag.fragment_index,
            frag.file_path,
            frag.file_id,
            frag.service,
            frag.start_line,
            frag.end_line,
            frag.line_count,
            frag.file_type,
            frag.modified_commits,
            frag.modified_count,
        ]
    )


def _load_clones_json(
    project_root: Path,
    project_name: str,
    language: str,
) -> tuple[Path, dict[str, Any]]:
    """clones_json を読み込む.

    Returns:
        (workdir, clones_json_dict)

    Raises:
        FileNotFoundError: 必須ファイルが見つからない場合.
        ValueError: ファイル内容が不正な場合.
    """
    analyzed_commits_file = (
        project_root / "dest/analyzed_commits" / f"{project_name}.json"
    )
    if not analyzed_commits_file.exists():
        raise FileNotFoundError(f"analyzed_commits not found: {analyzed_commits_file}")
    analyzed_commits = json.loads(analyzed_commits_file.read_text(encoding="utf-8"))
    if not isinstance(analyzed_commits, list) or not analyzed_commits:
        raise ValueError(f"invalid analyzed_commits file: {analyzed_commits_file}")
    head_commit = str(analyzed_commits[0])

    clones_json_path = (
        project_root
        / "dest/clones_json"
        / project_name
        / head_commit
        / f"{language}.json"
    )
    if not clones_json_path.exists():
        raise FileNotFoundError(f"clones_json not found: {clones_json_path}")
    return (
        project_root / "dest/projects" / project_name,
        json.loads(clones_json_path.read_text(encoding="utf-8")),
    )


def _load_service_contexts(
    project_name: str,
    language: str,
    ms_detection_dir: Path,
) -> tuple[list[ServiceContext], Path]:
    """CLAIM サービスコンテキストを読み込む.

    JSON キャッシュを優先し, なければ ms_detection CSV にフォールバック.

    Returns:
        (claim_contexts, services_json_path)

    Raises:
        FileNotFoundError: ms_detection_dir が None またはファイルが無い場合.
        ValueError: コンテキストが空の場合.
    """
    claim_contexts: list[ServiceContext] = []
    services_json_dir = ms_detection_dir.parent / "services_json"
    services_json_path = services_json_dir / f"{project_name}.json"

    if services_json_path.exists():
        try:
            claim_contexts = load_service_contexts_from_json(services_json_path)
        except Exception as exc:
            logger.warning("Failed to load services JSON, falling back to CSV: %s", exc)
            claim_contexts = []

    if not claim_contexts:
        claim_csv_path = ms_detection_dir / f"{project_name}.csv"
        if not claim_csv_path.exists():
            raise FileNotFoundError(f"ms_detection csv not found: {claim_csv_path}")
        try:
            claim_contexts = load_claim_service_contexts_for_repo(
                project_name, claim_csv_path, chunk="latest"
            )
        except Exception as exc:
            raise RuntimeError(
                f"failed to load claim contexts: "
                f"project={project_name}, language={language}"
            ) from exc

    if not claim_contexts:
        raise ValueError(
            f"empty claim contexts: project={project_name}, language={language}"
        )

    return claim_contexts, services_json_path


def build_enriched_fragments_for_language(
    *,
    project_name: str,
    language: str,
    filter_type: str | None,
    project_root: Path,
    out_dir: Path,
    ms_detection_dir: Path | None = None,
    enrich_services: bool = True,
) -> Path:
    """1 プロジェクト × 1 言語の enriched_fragments.csv を生成する.

    ``enrich_services=True`` (デフォルト) の場合,
    services.json の ``language_stats`` セクションも同時に更新する.

    Args:
        project_name: ``<owner>.<repo>`` 形式の識別子.
        language: 言語名.
        filter_type: ``None`` / ``"import"`` / ``"tks"``.
        project_root: リポジトリ root.
        out_dir: 出力ベースディレクトリ
            (``dest/enriched_fragments`` を想定).
        ms_detection_dir: ms_detection CSV のディレクトリ.
        enrich_services: services.json に file_stats を追記するか.

    Returns:
        出力した CSV のパス.

    Raises:
        FileNotFoundError: 必須入力ファイルが見つからない場合.
        ValueError: 入力データが不正な場合.
    """
    if ms_detection_dir is None:
        raise FileNotFoundError("ms_detection_dir is required for service resolution")

    csv_prefix = f"{filter_type}_" if filter_type else ""
    fragment_csv = (
        project_root / "dest/csv" / project_name / f"{csv_prefix}{language}.csv"
    )
    if not fragment_csv.exists():
        raise FileNotFoundError(f"fragment csv not found: {fragment_csv}")

    # --- 共通セットアップ ---
    workdir, clones_json = _load_clones_json(project_root, project_name, language)

    file_data = clones_json.get("file_data")
    if not isinstance(file_data, list):
        raise ValueError(f"invalid clones_json file_data: project={project_name}")
    file_mapper = FileMapper(file_data, str(workdir))

    claim_contexts, services_json_path = _load_service_contexts(
        project_name, language, ms_detection_dir
    )

    # --- services.json 拡充 ---
    if enrich_services and services_json_path.exists():
        from modules.visualization.enrich_services import (
            enrich_services_json,
        )

        enrich_services_json(
            services_json_path=services_json_path,
            language=language,
            file_data=file_data,
            claim_contexts=claim_contexts,
            project_dir=workdir,
        )

    # --- enriched_fragments.csv 生成 ---
    out_project_dir = out_dir / project_name
    out_project_dir.mkdir(parents=True, exist_ok=True)
    output_csv = out_project_dir / f"{csv_prefix}{language}.csv"

    service_cache: dict[str, str] = {}
    file_id_cache: dict[str, int] = {}
    file_text_cache: dict[str, str] = {}
    row_count = 0
    groups_processed = 0
    start_time = time.perf_counter()

    logger.info(
        "start build enriched fragments: project=%s language=%s filter=%s",
        project_name,
        language,
        filter_type,
    )

    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=",", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(_HEADER)

        for fragments in iter_fragment_groups(fragment_csv):
            for frag in fragments:
                norm_path = normalize_file_path(frag.file_path, workdir)

                # service (cached)
                if norm_path in service_cache:
                    service = service_cache[norm_path]
                else:
                    ctx = resolve_service_for_file_path(
                        norm_path,
                        claim_contexts,
                        [],
                        repo_dir=workdir,
                    )
                    service = ctx.service_name if ctx else ""
                    service_cache[norm_path] = service

                # file_id (cached)
                if norm_path in file_id_cache:
                    file_id = file_id_cache[norm_path]
                else:
                    file_id = safe_get_file_id(file_mapper, norm_path)
                    file_id_cache[norm_path] = file_id

                commits = parse_modified_commits(frag.modification_raw)

                file_type = get_file_type(
                    norm_path,
                    language=language,
                )

                enriched = build_enriched_fragment(
                    frag,
                    norm_path=norm_path,
                    service=service,
                    file_id=file_id,
                    commits=commits,
                    file_type=file_type,
                )
                _write_row(writer, enriched)
                row_count += 1

            groups_processed += 1
            if groups_processed % 500 == 0:
                elapsed = time.perf_counter() - start_time
                logger.info(
                    "progress enriched fragments: project=%s language=%s "
                    "groups=%d rows=%d elapsed=%.1fs",
                    project_name,
                    language,
                    groups_processed,
                    row_count,
                    elapsed,
                )

    elapsed_total = time.perf_counter() - start_time
    logger.info(
        "built enriched fragments: project=%s language=%s "
        "groups=%d rows=%d elapsed=%.1fs output=%s",
        project_name,
        language,
        groups_processed,
        row_count,
        elapsed_total,
        output_csv,
    )
    return output_csv
