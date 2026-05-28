"""クローン比率 (ROC) をプロジェクト単位で計算する.

enriched_fragments.csv と services.json を使い,
サービスごとの ROC 平均値を返す.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# dest ディレクトリのデフォルト探索パス
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/visualize -> repo root


def calculate_project_average_clone_ratio(project_name: str) -> float:
    """プロジェクトの平均クローン比率 (ROC) を計算する.

    enriched_fragments.csv と services.json が存在する場合に
    サービスごとの ROC 平均を返す. ファイルが見つからない場合は 0.0.

    Args:
        project_name: ``<owner>.<repo>`` 形式のプロジェクト名.

    Returns:
        平均 ROC (0.0 ～ 1.0). データなしの場合は 0.0.
    """
    try:
        from modules.visualization.compute_clone_metrics import (
            compute_service_metrics,
            load_enriched_fragments,
            load_language_stats,
        )
    except ImportError:
        logger.debug("compute_clone_metrics not available")
        return 0.0

    dest = _PROJECT_ROOT / "dest"
    enriched_dir = dest / "enriched_fragments" / project_name
    services_json = dest / "services_json" / f"{project_name}.json"

    if not enriched_dir.exists() or not services_json.exists():
        return 0.0

    csv_files = sorted(enriched_dir.glob("*.csv"))
    if not csv_files:
        return 0.0

    all_rocs: list[float] = []
    for csv_path in csv_files:
        language = csv_path.stem
        # filter prefix を除去
        for prefix in ("import_", "tks_"):
            if language.startswith(prefix):
                language = language[len(prefix) :]
                break
        try:
            df = load_enriched_fragments(csv_path)
            lang_stats = load_language_stats(services_json, language)
            metrics = compute_service_metrics(df, lang_stats)
            for m in metrics:
                if m.roc > 0:
                    all_rocs.append(m.roc)
        except Exception as exc:
            logger.warning(
                "failed to compute ROC for %s/%s: %s",
                project_name,
                csv_path.name,
                exc,
            )

    if not all_rocs:
        return 0.0
    return sum(all_rocs) / len(all_rocs)
