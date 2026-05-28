"""services.json にファイル統計 (file_count, total_loc) を追記する.

既存の ``services.json`` に言語ごとの ``language_stats`` セクションを追加し,
各サービスのファイル数と LOC を記録する.  メトリクス計算で ROC（Clone Ratio）等
の分母として利用する.

出力形式 (``language_stats`` 部分)::

    {
      "services": { ... },          # 既存: 変更しない
      "URL": "...",                  # 既存: 変更しない
      "language_stats": {
        "Python": {
          "services": {
            "worker": {"file_count": 5, "total_loc": 500},
            "vote":   {"file_count": 3, "total_loc": 200}
          },
          "total_files": 20,
          "total_loc": 5000,
          "unresolved_files": 12,
          "unresolved_loc": 4300
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from modules.visualization.build_scatter_dataset import normalize_file_path
from modules.visualization.service_mapping import (
    ServiceContext,
    resolve_service_for_file_path,
)

logger = logging.getLogger(__name__)


@dataclass
class ServiceFileStats:
    """サービス 1 つ分のファイル統計."""

    file_count: int = 0
    total_loc: int = 0


def compute_service_file_stats(
    file_data: list[dict[str, Any]],
    claim_contexts: Sequence[ServiceContext],
    project_dir: Path,
) -> tuple[dict[str, ServiceFileStats], int, int, int, int]:
    """clones_json の file_data からサービスごとのファイル統計を計算する.

    Args:
        file_data: clones_json の ``file_data``
            (各要素に ``file_path``, ``loc`` を持つ).
        claim_contexts: CLAIM 由来の ServiceContext リスト.
        project_dir: ``dest/projects/<project>``.

    Returns:
        (per_service_stats, total_files, total_loc,
         unresolved_files, unresolved_loc)
    """
    per_service: dict[str, ServiceFileStats] = {}
    total_files = len(file_data)
    total_loc = 0
    unresolved_files = 0
    unresolved_loc = 0

    for entry in file_data:
        file_path = str(entry.get("file_path", ""))
        loc = int(entry.get("loc", 0))
        total_loc += loc

        norm_path = normalize_file_path(file_path, project_dir)
        ctx = resolve_service_for_file_path(
            norm_path, claim_contexts, [], repo_dir=project_dir
        )
        if ctx is None:
            unresolved_files += 1
            unresolved_loc += loc
        else:
            svc = ctx.service_name
            if svc not in per_service:
                per_service[svc] = ServiceFileStats()
            per_service[svc].file_count += 1
            per_service[svc].total_loc += loc

    return per_service, total_files, total_loc, unresolved_files, unresolved_loc


def _ids_to_contiguous_ranges(ids: list[int]) -> list[list[int]]:
    """ソート済み整数リストから連続する範囲をまとめる.

    例: [0, 1, 2, 5, 6, 10] -> [[0, 2], [5, 6], [10, 10]]
    """
    if not ids:
        return []
    sorted_ids = sorted(ids)
    ranges: list[list[int]] = []
    start = sorted_ids[0]
    prev = start
    for fid in sorted_ids[1:]:
        if fid == prev + 1:
            prev = fid
        else:
            ranges.append([start, prev])
            start = fid
            prev = fid
    ranges.append([start, prev])
    return ranges


def compute_service_file_ranges(
    file_data: list[dict[str, Any]],
    claim_contexts: Sequence[ServiceContext],
    project_dir: Path,
) -> dict[str, list[list[int]]]:
    """clones_json の file_data からサービスごとの file_id 範囲を計算する.

    散布図のサービス境界線描画に使用される.
    CCFinderSW が割り当てた file_id とサービス解決結果から,
    各サービスが占める連続 file_id 範囲を算出する.

    Args:
        file_data: clones_json の ``file_data``
            (各要素に ``file_id``, ``file_path`` を持つ).
        claim_contexts: CLAIM 由来の ServiceContext リスト.
        project_dir: ``dest/projects/<project>``.

    Returns:
        ``{"service_name": [[start, end], ...], ...}``
    """
    service_file_ids: dict[str, list[int]] = {}

    for entry in file_data:
        file_path = str(entry.get("file_path", ""))
        file_id = int(entry.get("file_id", -1))
        if file_id < 0:
            continue

        norm_path = normalize_file_path(file_path, project_dir)
        ctx = resolve_service_for_file_path(
            norm_path, claim_contexts, [], repo_dir=project_dir
        )
        if ctx is None:
            continue
        svc = ctx.service_name
        service_file_ids.setdefault(svc, []).append(file_id)

    return {
        svc: _ids_to_contiguous_ranges(ids)
        for svc, ids in sorted(service_file_ids.items())
    }


def enrich_services_json(
    *,
    services_json_path: Path,
    language: str,
    file_data: list[dict[str, Any]],
    claim_contexts: Sequence[ServiceContext],
    project_dir: Path,
) -> Path:
    """既存の services.json に ``language_stats`` を追記する.

    同一言語で再実行すると上書きされる.  他言語のエントリは維持される.

    Args:
        services_json_path: ``dest/services_json/<project>.json``.
        language: 言語名 (e.g. ``"Python"``).
        file_data: clones_json の ``file_data``.
        claim_contexts: CLAIM 由来の ServiceContext リスト.
        project_dir: ``dest/projects/<project>``.

    Returns:
        更新した JSON のパス.

    Raises:
        FileNotFoundError: services_json_path が存在しない場合.
    """
    if not services_json_path.exists():
        raise FileNotFoundError(f"services json not found: {services_json_path}")

    with services_json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    per_service, total_files, total_loc, unresolved_files, unresolved_loc = (
        compute_service_file_stats(file_data, claim_contexts, project_dir)
    )
    file_ranges = compute_service_file_ranges(file_data, claim_contexts, project_dir)

    language_stats: dict[str, Any] = data.setdefault("language_stats", {})
    language_stats[language] = {
        "services": {
            svc: {"file_count": stats.file_count, "total_loc": stats.total_loc}
            for svc, stats in sorted(per_service.items())
        },
        "total_files": total_files,
        "total_loc": total_loc,
        "unresolved_files": unresolved_files,
        "unresolved_loc": unresolved_loc,
        "file_ranges": file_ranges,
    }

    with services_json_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(
        "Enriched services JSON: %s language=%s services=%d "
        "total_files=%d total_loc=%d unresolved=%d",
        services_json_path,
        language,
        len(per_service),
        total_files,
        total_loc,
        unresolved_files,
    )
    return services_json_path
