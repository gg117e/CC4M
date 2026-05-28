"""既存の dest/ms_detection/*.csv から dest/services_json/*.json を一括生成する.

CLAIM の ms_detection を再実行せずに, CSV パース結果を JSON キャッシュとして保存する.
既に JSON が存在するリポジトリはスキップする (--force で上書き可能).

Usage:
    python scripts/migrate_ms_detection_to_json.py
    python scripts/migrate_ms_detection_to_json.py --force
    python scripts/migrate_ms_detection_to_json.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))

from modules.visualization.service_mapping import (
    load_claim_service_contexts_for_repo,
    save_service_contexts_to_json,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _guess_url_from_name(repo_name: str) -> str:
    """owner.repo 形式の名前から GitHub URL を推測する.

    Args:
        repo_name: owner.repo (例: "FudanSELab.train-ticket").

    Returns:
        推測した URL.
    """
    parts = repo_name.split(".", 1)
    if len(parts) == 2:
        return f"https://github.com/{parts[0]}/{parts[1]}"
    return f"https://github.com/{repo_name}"


def _try_read_url_from_csv(csv_path: Path) -> str | None:
    """ms_detection CSV から URL カラムを取得する (存在すれば)."""
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("URL") or row.get("url")
                if url:
                    return str(url).strip()
    except Exception:
        pass
    return None


def migrate(
    ms_detection_dir: Path,
    services_json_dir: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """ms_detection CSV → services_json JSON の一括変換.

    Args:
        ms_detection_dir: dest/ms_detection ディレクトリ.
        services_json_dir: dest/services_json ディレクトリ.
        force: 既存 JSON を上書きするか.
        dry_run: 実際には書き込まない.

    Returns:
        (処理数, 成功数, スキップ数).
    """
    if not ms_detection_dir.exists():
        logger.warning("ms_detection directory not found: %s", ms_detection_dir)
        return 0, 0, 0

    csv_files = sorted(ms_detection_dir.glob("*.csv"))
    if not csv_files:
        logger.info("No CSV files found in %s", ms_detection_dir)
        return 0, 0, 0

    total = len(csv_files)
    success = 0
    skipped = 0

    for csv_path in csv_files:
        repo_name = csv_path.stem
        json_path = services_json_dir / f"{repo_name}.json"

        if json_path.exists() and not force:
            logger.info("  SKIP (exists): %s", repo_name)
            skipped += 1
            continue

        # URL を推測
        url = _try_read_url_from_csv(csv_path) or _guess_url_from_name(repo_name)

        try:
            contexts = load_claim_service_contexts_for_repo(
                repo_name, csv_path, chunk="latest"
            )
            if not contexts:
                logger.warning("  EMPTY: %s (no service contexts extracted)", repo_name)
                skipped += 1
                continue

            if dry_run:
                logger.info(
                    "  DRY-RUN: %s -> %s (%d contexts)",
                    repo_name,
                    json_path,
                    len(contexts),
                )
            else:
                save_service_contexts_to_json(contexts, url, json_path)
                logger.info("  OK: %s (%d contexts)", repo_name, len(contexts))
            success += 1

        except Exception as e:
            logger.error("  FAIL: %s — %s", repo_name, e)

    return total, success, skipped


def main() -> None:
    """エントリポイント."""
    parser = argparse.ArgumentParser(
        description="既存の ms_detection CSV から services_json を一括生成する."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存の JSON を上書きする.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際には書き込まず, 処理内容だけ表示する.",
    )
    parser.add_argument(
        "--ms-detection-dir",
        type=Path,
        default=_project_root / "dest" / "ms_detection",
        help="ms_detection CSV のディレクトリ (default: dest/ms_detection).",
    )
    parser.add_argument(
        "--services-json-dir",
        type=Path,
        default=_project_root / "dest" / "services_json",
        help="出力先ディレクトリ (default: dest/services_json).",
    )
    args = parser.parse_args()

    logger.info("Source:  %s", args.ms_detection_dir)
    logger.info("Output:  %s", args.services_json_dir)
    if args.dry_run:
        logger.info("Mode:    DRY-RUN")
    elif args.force:
        logger.info("Mode:    FORCE (overwrite existing)")

    total, success, skipped = migrate(
        args.ms_detection_dir,
        args.services_json_dir,
        force=args.force,
        dry_run=args.dry_run,
    )

    logger.info("--- Summary ---")
    logger.info("Total CSVs:  %d", total)
    logger.info("Converted:   %d", success)
    logger.info("Skipped:     %d", skipped)
    logger.info("Failed:      %d", total - success - skipped)


if __name__ == "__main__":
    main()
