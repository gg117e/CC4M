from pathlib import Path
import csv
import logging
import traceback
import json
import git  # GitPython
import sys


logger = logging.getLogger(__name__)


def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))
import modules.CLAIM.dc_choice as dc_choice
import modules.CLAIM.ms_detection as ms_detection
from lib.CLAIM.src.claim import claim as claim_snapshot
from lib.CLAIM.src.utils.print_utils import print_progress, print_major_step, print_info
from lib.CLAIM.src.utils.repo import clear_repo
from modules.github_linguist import run_github_linguist
from modules.visualization.service_mapping import (
    ServiceContext,
    load_claim_service_contexts_for_repo,
    normalize_repo_relative_path,
    save_service_contexts_to_json,
)
from config import BASED_DATASET


def analyze_repo_by_linguist(workdir: str, name: str):
    output_json = run_github_linguist(workdir)

    result_dir = project_root / "dest/github_linguist"
    result_dir.mkdir(parents=True, exist_ok=True)
    result_file = result_dir / f"{name}.json"
    with open(result_file, "w") as result_output:
        result_output.write(json.dumps(output_json, indent=4))


def analyze_repo_by_clim(url: str, name: str, workdir: str):
    """CLAIM による Docker Compose 分析とマイクロサービス検出を実行する.

    ms_detection 完了後, 結果を ``dest/services_json/<name>.json`` にも保存する.

    Args:
        url: リポジトリの URL.
        name: owner.repo 形式のリポジトリ名.
        workdir: ローカルリポジトリのパス.
    """
    try:
        res = dc_choice.analyze_repo(name, workdir)
        dc_choice.print_results(url, res)
        dc_choice.save_results(url, res)
        res = ms_detection.analyze_repo(name, workdir)
        ms_detection.print_results(url, res)
        ms_detection.save_results(url, res)

        # ms_detection CSV → services_json キャッシュ
        _save_services_json_cache(url, name)
    except Exception as e:
        raise RuntimeError(f"CLAIM analysis failed: repo={name}, url={url}") from e


def _save_services_json_cache(url: str, name: str) -> None:
    """ms_detection CSV を解析し, dest/services_json に JSON キャッシュを保存する.

    Args:
        url: リポジトリの URL.
        name: owner.repo 形式のリポジトリ名.
    """
    ms_detection_csv = project_root / "dest" / "ms_detection" / f"{name}.csv"
    if not ms_detection_csv.exists():
        logger.warning(
            "ms_detection CSV not found, skipping JSON cache: %s", ms_detection_csv
        )
        return

    try:
        contexts = load_claim_service_contexts_for_repo(
            name, ms_detection_csv, chunk="latest"
        )
        if not contexts:
            logger.warning(
                "No service contexts extracted, skipping JSON cache: %s", name
            )
            return

        services_json_dir = project_root / "dest" / "services_json"
        output_path = services_json_dir / f"{name}.json"
        save_service_contexts_to_json(contexts, url, output_path)
    except Exception as e:
        logger.warning("Failed to save services JSON cache for %s: %s", name, e)


def analyze_repo_snapshot(url: str, name: str, workdir: str) -> Path:
    """CLAIM の単一スナップショットモードでマイクロサービスを検出する.

    コミット履歴を走査せず, 現在のワークツリーのみを解析するため
    数秒で完了する（フル履歴走査の ``analyze_repo_by_clim`` は数時間かかる）.

    結果は ``dest/services_json/<name>.json`` に保存される.

    Args:
        url: リポジトリの URL.
        name: owner.repo 形式のリポジトリ名.
        workdir: ローカルリポジトリのパス.

    Returns:
        保存した JSON ファイルのパス.

    Raises:
        RuntimeError: CLAIM 解析に失敗した場合.
    """
    try:
        microservices = claim_snapshot(name, workdir)
    except Exception as e:
        raise RuntimeError(
            f"CLAIM snapshot analysis failed: repo={name}, url={url}"
        ) from e

    contexts: list[ServiceContext] = []
    for ms in microservices:
        service_name = (ms.name or "").strip()
        if not service_name:
            continue

        build = ms.build
        if build is not None and build.context:
            raw = str(build.context).strip()
            if raw and raw not in {".", "None"}:
                ctx = normalize_repo_relative_path(raw, repo_dir=None)
                if ctx:
                    contexts.append(
                        ServiceContext(
                            service_name=service_name,
                            context=ctx,
                            source="claim:snapshot",
                        )
                    )
                    continue

            # context が "." や空の場合, Dockerfile パスから推定
            if build.rel_dockerfile:
                rel = normalize_repo_relative_path(
                    str(build.rel_dockerfile), repo_dir=None
                )
                parent = str(Path(rel).parent).replace("\\", "/").strip("/")
                if parent and parent != ".":
                    contexts.append(
                        ServiceContext(
                            service_name=service_name,
                            context=parent,
                            source="claim:snapshot:dockerfile",
                        )
                    )

    if not contexts:
        logger.warning("No service contexts detected by snapshot for %s", name)

    services_json_dir = project_root / "dest" / "services_json"
    output_path = services_json_dir / f"{name}.json"
    save_service_contexts_to_json(contexts, url, output_path)
    logger.info("Snapshot analysis complete: %s (%d services)", name, len(contexts))
    return output_path


def analyze_repo(url: str, name: str, workdir: str):
    """リポジトリの言語解析と CLAIM マイクロサービス検出を実行する.

    Args:
        url: リポジトリの URL.
        name: owner.repo 形式のリポジトリ名.
        workdir: ローカルリポジトリのパス.
    """
    try:
        analyze_repo_by_linguist(workdir, name)
        analyze_repo_by_clim(url, name, workdir)
    except Exception as e:
        raise RuntimeError(f"analyze_repo failed: repo={name}, url={url}") from e


def analyze_dataset():
    dataset_file = BASED_DATASET

    total_repos = -1
    for _ in open(dataset_file):
        total_repos += 1

    with open(dataset_file) as dataset:
        repos = csv.DictReader(dataset, delimiter=";")
        for index, repo in enumerate(repos):
            print_progress(f"Processing {index + 1}/{total_repos}")
            url = repo["URL"]
            name = url.split("/")[-2] + "." + url.split("/")[-1]
            workdir = str(project_root / "dest/temp/clones" / name)
            try:
                git.Repo.clone_from(url, workdir, depth=1)
                analyze_repo(url, name, workdir)
            except Exception as e:
                logger.error(
                    "Error processing repo %s: %s", url, traceback.format_exc()
                )
                continue
            finally:
                print_info("   Clearing temporary directories")
                clear_repo(Path(workdir))


def main():
    print_major_step("# Start dataset analysis")
    analyze_dataset()


if __name__ == "__main__":
    main()
