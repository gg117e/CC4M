from __future__ import annotations

import ast
import csv
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from modules.claim_parser import parse_uSs

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServiceContext:
    """サービス境界（ディレクトリprefix）を表す.

    Attributes:
            service_name: サービス名.
            context: リポジトリ相対のディレクトリprefix（例: "src/cartservice"）.
            source: context の由来（例: "claim:context" / "claim:dockerfile" / "selected_projects"）.
    """

    service_name: str
    context: str
    source: str


def normalize_repo_relative_path(path: str | None, repo_dir: Path | None = None) -> str:
    """パス文字列を "リポジトリ相対の / 区切り" に正規化する.

    Args:
            path: 元のパス（相対/絶対どちらでも可）.
            repo_dir: リポジトリのルートディレクトリ. 指定されていれば, その prefix を除去する.

    Returns:
            正規化したパス（空文字になり得る）.
    """

    if not path:
        return ""

    s = str(path).strip()
    if not s:
        return ""

    # Windows/Unix 混在を吸収
    s = s.replace("\\", "/")

    if repo_dir is not None:
        prefix = str(repo_dir).replace("\\", "/").rstrip("/") + "/"
        if s.startswith(prefix):
            s = s[len(prefix) :]

    # 先頭の ./ を落とす
    if s.startswith("./"):
        s = s[2:]

    return s.strip("/")


def choose_longest_prefix_match(
    path: str, contexts: Iterable[ServiceContext]
) -> ServiceContext | None:
    """path に対して最長prefix一致する ServiceContext を返す.

    Args:
            path: リポジトリ相対パス.
            contexts: 候補の ServiceContext 群.

    Returns:
            最長prefix一致した ServiceContext. 見つからなければ None.
    """

    best: ServiceContext | None = None
    for ctx in contexts:
        if not ctx.context:
            continue
        normalized = ctx.context.rstrip("/")
        if path == normalized or path.startswith(normalized + "/"):
            if best is None or len(normalized) > len(best.context.rstrip("/")):
                best = ctx
    return best


def load_claim_service_contexts_for_repo(
    repo_name: str,
    ms_detection_csv: Path,
    chunk: str = "latest",
) -> list[ServiceContext]:
    """CLAIM の ms_detection 出力から service context を抽出する.

    注意:
    - CLAIM はコミット履歴を "chunk"（連続コミット区間）に分けて結果を保存する.
    - `chunk` には "latest"（最後の行）/"first"（最初の行）/"all"（全行の和集合）を指定できる.

    Args:
            repo_name: 表示用のリポジトリ名.
            ms_detection_csv: `dest/ms_detection/<repo>.csv` のパス.
            chunk: "latest" | "first" | "all".

    Returns:
            ServiceContext のリスト.

    Raises:
            FileNotFoundError: ms_detection_csv が存在しない場合.
            ValueError: chunk 指定が不正な場合.
    """

    if not ms_detection_csv.exists():
        raise FileNotFoundError(f"ms_detection csv not found: {ms_detection_csv}")

    rows: list[Mapping[str, Any]] = []
    with ms_detection_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        return []

    if chunk == "latest":
        selected_rows = [rows[-1]]
    elif chunk == "first":
        selected_rows = [rows[0]]
    elif chunk == "all":
        selected_rows = rows
    else:
        raise ValueError(f"invalid chunk: {chunk}")

    contexts: dict[tuple[str, str], ServiceContext] = {}

    for row in selected_rows:
        uSs = row.get("uSs")
        if not uSs:
            continue

        microservices = parse_uSs(uSs)
        if not microservices:
            continue

        for ms in microservices:
            service_name = str(ms.get("name") or "").strip()
            if not service_name:
                continue

            build = ms.get("build") or {}
            raw_context = build.get("context")
            rel_dockerfile = build.get("rel_dockerfile")

            # 1) context が取れているなら最優先
            if raw_context and str(raw_context).strip() not in {".", "None"}:
                context = normalize_repo_relative_path(str(raw_context), repo_dir=None)
                if context:
                    contexts[(service_name, context)] = ServiceContext(
                        service_name=service_name,
                        context=context,
                        source="claim:context",
                    )
                    continue

            # 2) context が無い場合, Dockerfile の親ディレクトリから推定
            if rel_dockerfile:
                rel = normalize_repo_relative_path(str(rel_dockerfile), repo_dir=None)
                parent = str(Path(rel).parent).replace("\\", "/").strip("/")
                if parent and parent != ".":
                    contexts[(service_name, parent)] = ServiceContext(
                        service_name=service_name,
                        context=parent,
                        source="claim:dockerfile",
                    )

    if not contexts:
        logger.warning(
            "No claim contexts extracted for %s from %s", repo_name, ms_detection_csv
        )

    return list(contexts.values())


def save_service_contexts_to_json(
    contexts: Sequence[ServiceContext],
    url: str,
    output_path: Path,
) -> Path:
    """ServiceContext リストを JSON ファイルに保存する.

    出力形式は codebases_inter-service.json と同一:
    ``{"services": {"<context>": ["<service_name>", ...]}, "URL": "..."}``

    Args:
        contexts: 保存する ServiceContext のリスト.
        url: リポジトリの URL.
        output_path: 保存先の JSON ファイルパス.

    Returns:
        保存した JSON ファイルのパス.
    """
    services: dict[str, list[str]] = {}
    for ctx in contexts:
        key = ctx.context.rstrip("/") + "/"
        services.setdefault(key, [])
        if ctx.service_name not in services[key]:
            services[key].append(ctx.service_name)

    data = {"services": services, "URL": url}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(
        "Saved service contexts JSON: %s (%d services)", output_path, len(services)
    )
    return output_path


def load_service_contexts_from_json(
    json_path: Path,
) -> list[ServiceContext]:
    """JSON キャッシュから ServiceContext リストを読み込む.

    Args:
        json_path: ``dest/services_json/<repo>.json`` のパス.

    Returns:
        ServiceContext のリスト.

    Raises:
        FileNotFoundError: json_path が存在しない場合.
    """
    if not json_path.exists():
        raise FileNotFoundError(f"services json not found: {json_path}")

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    services = data.get("services", {})
    # languages ラッパー形式にも対応 (codebases_inter-service.json 互換)
    if not services and "languages" in data:
        for _lang, lang_map in data["languages"].items():
            if isinstance(lang_map, dict):
                for ctx_key, svc_names in lang_map.items():
                    services.setdefault(ctx_key, []).extend(
                        n for n in svc_names if n not in services.get(ctx_key, [])
                    )

    contexts: list[ServiceContext] = []
    for context_key, service_names in services.items():
        ctx = normalize_repo_relative_path(str(context_key), repo_dir=None)
        if not ctx:
            continue
        for name in service_names:
            contexts.append(
                ServiceContext(
                    service_name=str(name),
                    context=ctx,
                    source="services_json",
                )
            )

    logger.info(
        "Loaded service contexts from JSON: %s (%d contexts)", json_path, len(contexts)
    )
    return contexts


def load_selected_projects_contexts(
    project: Mapping[str, Any], language: str
) -> list[ServiceContext]:
    """selected_projects.json の context->service を ServiceContext 化する.

    Args:
            project: selected_projects の project dict.
            language: 対象言語.

    Returns:
            ServiceContext のリスト.
    """

    languages = project.get("languages") or {}
    lang_map: Mapping[str, Any] = languages.get(language) or {}

    result: list[ServiceContext] = []
    for context, service_names in lang_map.items():
        ctx = normalize_repo_relative_path(str(context), repo_dir=None)
        if not ctx:
            continue
        for name in service_names or []:
            result.append(
                ServiceContext(
                    service_name=str(name), context=ctx, source="selected_projects"
                )
            )
    return result


def resolve_service_for_file_path(
    file_path: str,
    claim_contexts: Sequence[ServiceContext],
    fallback_contexts: Sequence[ServiceContext],
    repo_dir: Path | None = None,
) -> ServiceContext | None:
    """file_path をサービスに割り当てる（CLAIM優先, ダメならフォールバック）.

    Args:
            file_path: ファイルパス（相対/絶対どちらでも可）.
            claim_contexts: CLAIM から得た候補.
            fallback_contexts: selected_projects 等のフォールバック候補.
            repo_dir: リポジトリのルート. 指定時は file_path から prefix 除去に使う.

    Returns:
            割り当てられた ServiceContext. 見つからなければ None.
    """

    rel = normalize_repo_relative_path(file_path, repo_dir=repo_dir)
    if not rel:
        return None

    best = choose_longest_prefix_match(rel, claim_contexts)
    if best is not None:
        return best

    return choose_longest_prefix_match(rel, fallback_contexts)


def extract_repo_name_from_url(url: str) -> str:
    """URL から dest/projects 用の repo 名（owner.repo）を作る.

    Args:
            url: GitHub URL.

    Returns:
            owner.repo
    """

    parts = url.rstrip("/").split("/")
    return f"{parts[-2]}.{parts[-1]}"


def read_unique_file_paths_from_fragment_csv(csv_path: Path) -> list[str]:
    """dest/csv のフラグメントCSVから, file_path をユニークに取り出す.

    Args:
            csv_path: `dest/csv/<repo>/<prefix><lang>.csv`.

    Returns:
            file_path のユニークリスト.

    Raises:
            FileNotFoundError: csv_path が存在しない場合.
    """

    if not csv_path.exists():
        raise FileNotFoundError(f"fragment csv not found: {csv_path}")

    seen: set[str] = set()
    out: list[str] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            fp = row.get("file_path")
            if not fp:
                continue
            s = str(fp)
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
    return out


def count_service_assignment(
    file_paths: Sequence[str],
    claim_contexts: Sequence[ServiceContext],
    fallback_contexts: Sequence[ServiceContext],
    repo_dir: Path | None,
) -> tuple[int, int, dict[str, int], int]:
    """file_paths を service に割り当て, カバレッジを集計する.

    Args:
            file_paths: 対象ファイルパス群.
            claim_contexts: CLAIM の候補.
            fallback_contexts: フォールバック候補.
            repo_dir: リポジトリルート.

    Returns:
            (total, resolved, per_service_counts, resolved_by_fallback)
    """

    per_service: dict[str, int] = {}
    resolved = 0
    resolved_by_fallback = 0

    for fp in file_paths:
        rel = normalize_repo_relative_path(fp, repo_dir=repo_dir)
        if not rel:
            continue

        claim_match = choose_longest_prefix_match(rel, claim_contexts)
        if claim_match is not None:
            resolved += 1
            per_service.setdefault(claim_match.service_name, 0)
            per_service[claim_match.service_name] += 1
            continue

        fallback_match = choose_longest_prefix_match(rel, fallback_contexts)
        if fallback_match is not None:
            resolved += 1
            resolved_by_fallback += 1
            per_service.setdefault(fallback_match.service_name, 0)
            per_service[fallback_match.service_name] += 1

    return len(file_paths), resolved, per_service, resolved_by_fallback


def looks_like_test_name_false_positive(path: str) -> bool:
    """ "test" の部分一致が誤判定になりそうな例を検出する（デバッグ用）.

    Args:
            path: ファイルパス.

    Returns:
            誤判定候補なら True.
    """

    return bool(re.search(r"(contest|latest|attest)", path, re.IGNORECASE))
