"""散布図用データセット（行=クローンペア）を生成するモジュール.

入力:
- dest/csv/<project>/<filter_prefix><language>.csv
  (clone_id, index, file_path, start_line, end_line, ..., modification)

付加情報:
- selected_projects.json の project["languages"][language] にある
  context -> [service名...] を用いた service 解決
- dest/clones_json/<project>/<head_commit>/<language>.json の file_data を
  FileMapper で読み, file_path -> file_id を解決

出力:
- 行=クローンペアのCSV（unknownは別ファイルに分離可能）

注意:
- 断片CSVは過去資産の都合で delimiter が ';' の場合があるため, 読み取りは自動判定する.
- 出力CSVは delimiter=',' に統一する.
- 断片CSVの file_path は相対/絶対の混在があり得るため, project_dir を使って正規化する.
"""

from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from modules.visualization.service_mapping import (
    ServiceContext,
    load_claim_service_contexts_for_repo,
    load_service_contexts_from_json,
    resolve_service_for_file_path as resolve_service_context_for_file_path,
)
from modules.util import FileMapper, get_file_type


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FragmentRow:
    """入力CSVの1行（クローン断片）."""

    clone_id: str
    index: int
    file_path: str
    start_line: int
    end_line: int
    modification_raw: str


@dataclass(frozen=True)
class PairRow:
    """散布図用CSVの1行（クローンペア）."""

    clone_id: str
    file_path_x: str
    file_path_y: str
    file_id_x: int
    file_id_y: int
    start_line_x: int
    end_line_x: int
    start_line_y: int
    end_line_y: int
    service_x: str
    service_y: str
    relation: str
    comodified: int
    comodified_commits: str
    comodification_count: int
    file_type_x: str
    file_type_y: str
    token_count: int


def normalize_file_path(file_path: str | None, project_dir: Path) -> str:
    """file_path をリポジトリ相対に正規化する.

    Args:
        file_path: CSVやclones_json内の file_path（相対/絶対どちらもあり得る）.
        project_dir: dest/projects/<project> のパス.

    Returns:
        可能なら project_dir からの相対パス. 正規化できない場合は, 入力を軽く整形して返す.
    """

    if not file_path:
        return ""

    raw = str(file_path).strip().replace("\\", "/")
    if raw.startswith("./"):
        raw = raw[2:]

    project_prefix = str(project_dir).replace("\\", "/").rstrip("/") + "/"
    if raw.startswith(project_prefix):
        return raw[len(project_prefix) :]

    return raw


def detect_csv_delimiter(csv_path: Path) -> str:
    """CSVの区切り文字を推定する.

    Args:
        csv_path: 対象CSVパス.

    Returns:
        "," もしくは ";".

    Raises:
        FileNotFoundError: csv_path が存在しない場合.
    """

    if not csv_path.exists():
        raise FileNotFoundError(f"csv not found: {csv_path}")

    sample = csv_path.read_text(encoding="utf-8", errors="replace")[:4096]
    if not sample:
        return ","

    # 先頭行（ヘッダ）を最優先で判定する.
    # tks系CSVは modification 列に JSON が入り, JSON 内の "," によって Sniffer が "," を誤推定しやすい.
    first_line = sample.splitlines()[0] if sample.splitlines() else sample
    header_commas = first_line.count(",")
    header_semicolons = first_line.count(";")
    if header_semicolons and not header_commas:
        return ";"
    if header_commas and not header_semicolons:
        return ","

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";"])
        if getattr(dialect, "delimiter", None) in {",", ";"}:
            return str(dialect.delimiter)
    except csv.Error:
        pass

    # フォールバック: ヘッダ内の出現回数が多い方を採用.
    if header_semicolons > header_commas:
        return ";"
    return ","


def iter_fragment_rows(csv_path: Path) -> Iterable[FragmentRow]:
    """断片CSVを逐次読み込みする.

    Args:
        csv_path: dest/csv/<project>/<filter_prefix><language>.csv

    Yields:
        FragmentRow.

    Raises:
        FileNotFoundError: csv_path が存在しない場合.
        ValueError: 必須列が欠けている/型変換に失敗する場合.
    """

    delimiter = detect_csv_delimiter(csv_path)
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        required = {
            "clone_id",
            "index",
            "file_path",
            "start_line",
            "end_line",
            "modification",
        }
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"fragment csv missing required columns. path={csv_path}, fieldnames={reader.fieldnames}"
            )

        for row in reader:
            if not row:
                continue
            clone_id = (row.get("clone_id") or "").strip()
            if not clone_id:
                continue

            try:
                index = int((row.get("index") or "").strip())
                start_line = int((row.get("start_line") or "").strip())
                end_line = int((row.get("end_line") or "").strip())
            except Exception as e:
                raise ValueError(
                    f"invalid numeric column. path={csv_path}, row={row}"
                ) from e

            yield FragmentRow(
                clone_id=clone_id,
                index=index,
                file_path=(row.get("file_path") or "").strip(),
                start_line=start_line,
                end_line=end_line,
                modification_raw=(row.get("modification") or "").strip(),
            )


def iter_fragment_groups(csv_path: Path) -> Iterable[list[FragmentRow]]:
    """clone_id ごとに断片をまとめて逐次返す.

    断片CSVが clone_id で連続している前提（生成系の仕様）で, 低メモリで処理する.

    Args:
        csv_path: 断片CSV.

    Yields:
        同一 clone_id の FragmentRow リスト.

    Raises:
        ValueError: clone_id が非連続（同一clone_idが離れて再出現）した場合.
    """

    current_id: str | None = None
    buf: list[FragmentRow] = []
    closed_ids: set[str] = set()

    for frag in iter_fragment_rows(csv_path):
        if current_id is None:
            current_id = frag.clone_id
            buf.append(frag)
            continue

        if frag.clone_id == current_id:
            buf.append(frag)
            continue

        closed_ids.add(current_id)
        yield buf

        if frag.clone_id in closed_ids:
            raise ValueError(
                f"fragment csv is not grouped by clone_id: path={csv_path}, clone_id={frag.clone_id}"
            )

        current_id = frag.clone_id
        buf = [frag]

    if buf:
        yield buf


def parse_modified_commits(modification_raw: str) -> set[str]:
    """modification JSON 文字列から modified commit の集合を返す."""

    if not modification_raw:
        return set()
    try:
        data = json.loads(modification_raw)
    except json.JSONDecodeError:
        logger.warning("failed to parse modification json: %s", modification_raw)
        return set()

    if not isinstance(data, list):
        return set()

    commits: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "modified":
            continue
        commit = item.get("commit")
        if isinstance(commit, str) and commit:
            commits.add(commit)
    return commits


def compute_pair_comodified(fragment_x: FragmentRow, fragment_y: FragmentRow) -> int:
    """2断片が同時修正されているかを 0/1 で返す."""

    commits_x = parse_modified_commits(fragment_x.modification_raw)
    commits_y = parse_modified_commits(fragment_y.modification_raw)
    return 1 if compute_pair_common_commits_from_sets(commits_x, commits_y) else 0


def compute_pair_common_commits_from_sets(
    commits_x: set[str], commits_y: set[str]
) -> list[str]:
    """Return all commits that modified both fragments in a deterministic order."""

    return sorted(commits_x.intersection(commits_y))


def compute_pair_comodified_from_sets(commits_x: set[str], commits_y: set[str]) -> int:
    """2つの commit 集合が共通要素を持つかを 0/1 で返す."""

    return 1 if compute_pair_common_commits_from_sets(commits_x, commits_y) else 0


def safe_get_file_id(file_mapper: FileMapper, file_path: str) -> int:
    """FileMapper から file_id を取得する（見つからない場合は -1）."""

    if not file_path:
        return -1
    try:
        return int(file_mapper.get_file_id(file_path))
    except KeyError:
        logger.warning("file_id not found for file_path: %s", file_path)
        return -1


MAX_FRAGMENTS_PER_GROUP = 1000


def build_pair_rows(
    fragments: Sequence[FragmentRow],
    *,
    language: str,
    claim_contexts: Sequence[ServiceContext],
    project_dir: Path,
    file_mapper: FileMapper,
    service_cache: dict[str, str],
    file_id_cache: dict[str, int],
    file_text_cache: dict[str, str],
    token_count_map: dict[str, int],
) -> tuple[list[PairRow], list[PairRow]]:
    """clone_id ひとかたまりの断片からペア行を生成する.

    Args:
        fragments: 同一 clone_id の断片.
        language: 対象言語名.
        claim_contexts: CLAIM/ms_detection 由来の service context.
        project_dir: dest/projects/<project>.
        file_mapper: clones_json の file_data 由来.
        file_text_cache: ファイル先頭テキストの実行内キャッシュ.

    Returns:
        (resolved_pairs, unknown_pairs)
    """

    if len(fragments) <= 1:
        return ([], [])

    if len(fragments) > MAX_FRAGMENTS_PER_GROUP:
        logger.warning(
            "skip clone_id due to too many fragments: clone_id=%s, count=%d",
            fragments[0].clone_id,
            len(fragments),
        )
        return ([], [])

    ordered = sorted(fragments, key=lambda r: r.index)

    enriched: list[tuple[FragmentRow, str, str, int, set[str], str]]
    enriched = []
    for frag in ordered:
        norm_path = normalize_file_path(frag.file_path, project_dir)

        if norm_path in service_cache:
            service = service_cache[norm_path]
        else:
            service_context = resolve_service_context_for_file_path(
                norm_path,
                claim_contexts,
                [],
                repo_dir=project_dir,
            )
            service = service_context.service_name if service_context else ""
            service_cache[norm_path] = service

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
        enriched.append((frag, norm_path, service, file_id, commits, file_type))

    resolved: list[PairRow] = []
    unknown: list[PairRow] = []

    token_count = token_count_map.get(ordered[0].clone_id, 0)

    for i in range(len(enriched)):
        for j in range(i + 1, len(enriched)):
            x, norm_x, service_x, file_id_x, commits_x, file_type_x = enriched[i]
            y, norm_y, service_y, file_id_y, commits_y, file_type_y = enriched[j]
            relation = ""
            if service_x and service_y:
                relation = "intra" if service_x == service_y else "inter"

            common_commits = compute_pair_common_commits_from_sets(commits_x, commits_y)
            comodification_count = len(common_commits)
            row = PairRow(
                clone_id=x.clone_id,
                file_path_x=norm_x,
                file_path_y=norm_y,
                file_id_x=file_id_x,
                file_id_y=file_id_y,
                start_line_x=x.start_line,
                end_line_x=x.end_line,
                start_line_y=y.start_line,
                end_line_y=y.end_line,
                service_x=service_x,
                service_y=service_y,
                relation=relation,
                comodified=1 if comodification_count else 0,
                comodified_commits=json.dumps(common_commits),
                comodification_count=comodification_count,
                file_type_x=file_type_x,
                file_type_y=file_type_y,
                token_count=token_count,
            )

            if service_x and service_y:
                resolved.append(row)
            else:
                unknown.append(row)

    return (resolved, unknown)


def write_pair_csv_header(writer: csv.writer) -> None:
    """散布図用CSVのヘッダを書き込む."""

    writer.writerow(
        [
            "clone_id",
            "file_path_x",
            "file_path_y",
            "file_id_x",
            "file_id_y",
            "start_line_x",
            "end_line_x",
            "start_line_y",
            "end_line_y",
            "service_x",
            "service_y",
            "relation",
            "comodified",
            "comodified_commits",
            "comodification_count",
            "file_type_x",
            "file_type_y",
            "token_count",
        ]
    )


def write_pair_csv_row(writer: csv.writer, r: PairRow) -> None:
    """散布図用CSVに1行書き込む."""

    writer.writerow(
        [
            r.clone_id,
            r.file_path_x,
            r.file_path_y,
            r.file_id_x,
            r.file_id_y,
            r.start_line_x,
            r.end_line_x,
            r.start_line_y,
            r.end_line_y,
            r.service_x,
            r.service_y,
            r.relation,
            r.comodified,
            r.comodified_commits,
            r.comodification_count,
            r.file_type_x,
            r.file_type_y,
            r.token_count,
        ]
    )


def build_scatter_dataset_for_language(
    *,
    project: Mapping[str, Any],
    project_name: str,
    language: str,
    filter_type: str | None,
    project_root: Path,
    out_dir: Path,
    ms_detection_dir: Path | None = None,
    output_csv_stem: str | None = None,
) -> tuple[Path, Path]:
    """1プロジェクト×1言語の散布図データセットを生成する.

    Args:
        project: selected_projects.json の1要素.
        project_name: <owner>.<repo> 形式の識別子.
        language: 言語名.
        filter_type: None/import/tks.
        project_root: リポジトリroot.
        out_dir: 出力ディレクトリ（プロジェクト別の下に作る）.
        ms_detection_dir: ms_detection CSV のディレクトリ.
        output_csv_stem: 出力CSVの拡張子なしファイル名.
            指定時はこの名前で resolved/unknown を出力する.
            省略時は従来の "{csv_prefix}{language}_scatter" 形式を使う.

    Returns:
        (resolved_csv_path, unknown_csv_path)
    """

    csv_prefix = f"{filter_type}_" if filter_type else ""
    fragment_csv = (
        project_root / "dest/csv" / project_name / f"{csv_prefix}{language}.csv"
    )

    workdir = project_root / "dest/projects" / project_name
    analyzed_commits_file = (
        project_root / "dest/analyzed_commits" / f"{project_name}.json"
    )
    if not analyzed_commits_file.exists():
        raise FileNotFoundError(f"analyzed_commits not found: {analyzed_commits_file}")
    analyzed_commits = json.loads(analyzed_commits_file.read_text(encoding="utf-8"))
    if not isinstance(analyzed_commits, list) or not analyzed_commits:
        raise ValueError(f"invalid analyzed_commits file: {analyzed_commits_file}")
    head_commit = str(analyzed_commits[0])

    clones_json_dir = "clones_json"
    clones_json_path = (
        project_root
        / "dest"
        / clones_json_dir
        / project_name
        / head_commit
        / f"{language}.json"
    )
    if not clones_json_path.exists():
        raise FileNotFoundError(f"clones_json not found: {clones_json_path}")
    clones_json = json.loads(clones_json_path.read_text(encoding="utf-8"))
    file_data = clones_json.get("file_data")
    if not isinstance(file_data, list):
        raise ValueError(f"invalid clones_json file_data: path={clones_json_path}")
    file_mapper = FileMapper(file_data, str(workdir))

    clone_sets = clones_json.get("clone_sets", {})
    token_count_map = {}
    if isinstance(clone_sets, dict):
        for cid, data in clone_sets.items():
            if isinstance(data, dict):
                token_count_map[str(cid)] = int(data.get("token_count", 0))

    claim_contexts: list[ServiceContext] = []
    if ms_detection_dir is None:
        raise FileNotFoundError("ms_detection_dir is required for service resolution")

    # JSON キャッシュを優先的に使用 (eval() 不要で高速かつ安全)
    services_json_dir = ms_detection_dir.parent / "services_json"
    services_json_path = services_json_dir / f"{project_name}.json"
    if services_json_path.exists():
        try:
            claim_contexts = load_service_contexts_from_json(services_json_path)
        except Exception as e:
            logger.warning(
                "Failed to load services JSON cache, falling back to CSV: %s", e
            )
            claim_contexts = []

    # JSON キャッシュがなければ従来の CSV パースにフォールバック
    if not claim_contexts:
        claim_csv_path = ms_detection_dir / f"{project_name}.csv"
        if not claim_csv_path.exists():
            raise FileNotFoundError(f"ms_detection csv not found: {claim_csv_path}")
        try:
            claim_contexts = load_claim_service_contexts_for_repo(
                project_name,
                claim_csv_path,
                chunk="latest",
            )
        except Exception as e:
            raise RuntimeError(
                f"failed to load claim contexts. project={project_name}, language={language}, path={claim_csv_path}"
            ) from e

    if not claim_contexts:
        raise ValueError(
            f"empty claim contexts. project={project_name}, language={language}"
        )

    out_project_dir = out_dir / project_name / "csv"
    if output_csv_stem:
        resolved_csv_path = out_project_dir / f"{output_csv_stem}.csv"
        unknown_csv_path = out_project_dir / f"{output_csv_stem}_unknown.csv"
    else:
        resolved_csv_path = out_project_dir / f"{csv_prefix}{language}_scatter.csv"
        unknown_csv_path = (
            out_project_dir / f"{csv_prefix}{language}_scatter_unknown.csv"
        )
    out_project_dir.mkdir(parents=True, exist_ok=True)

    resolved_count = 0
    unknown_count = 0
    groups_processed = 0
    start_time = time.perf_counter()
    last_progress_time = start_time
    service_cache: dict[str, str] = {}
    file_id_cache: dict[str, int] = {}
    file_text_cache: dict[str, str] = {}

    logger.info(
        "start build scatter dataset: project=%s language=%s filter=%s fragment_csv=%s",
        project_name,
        language,
        filter_type,
        fragment_csv,
    )

    with (
        resolved_csv_path.open("w", encoding="utf-8", newline="") as resolved_f,
        unknown_csv_path.open("w", encoding="utf-8", newline="") as unknown_f,
    ):
        resolved_writer = csv.writer(
            resolved_f, delimiter=",", quoting=csv.QUOTE_MINIMAL
        )
        unknown_writer = csv.writer(unknown_f, delimiter=",", quoting=csv.QUOTE_MINIMAL)
        write_pair_csv_header(resolved_writer)
        write_pair_csv_header(unknown_writer)

        for fragments in iter_fragment_groups(fragment_csv):
            clone_id = fragments[0].clone_id if fragments else ""
            try:
                resolved, unknown = build_pair_rows(
                    fragments,
                    language=language,
                    claim_contexts=claim_contexts,
                    project_dir=workdir,
                    file_mapper=file_mapper,
                    service_cache=service_cache,
                    file_id_cache=file_id_cache,
                    file_text_cache=file_text_cache,
                    token_count_map=token_count_map,
                )
            except Exception as e:
                raise RuntimeError(
                    f"failed to build pair rows. project={project_name}, language={language}, clone_id={clone_id}"
                ) from e

            for r in resolved:
                write_pair_csv_row(resolved_writer, r)
                resolved_count += 1
            for r in unknown:
                write_pair_csv_row(unknown_writer, r)
                unknown_count += 1

            groups_processed += 1
            now = time.perf_counter()
            if (groups_processed % 200 == 0) or (now - last_progress_time >= 10.0):
                elapsed = now - start_time
                logger.info(
                    "progress build scatter dataset: project=%s language=%s filter=%s groups=%d resolved=%d unknown=%d elapsed=%.1fs last_clone_id=%s",
                    project_name,
                    language,
                    filter_type,
                    groups_processed,
                    resolved_count,
                    unknown_count,
                    elapsed,
                    clone_id,
                )
                last_progress_time = now

    elapsed_total = time.perf_counter() - start_time
    logger.info(
        "built scatter dataset: project=%s language=%s filter=%s groups=%d resolved=%d unknown=%d elapsed=%.1fs",
        project_name,
        language,
        filter_type,
        groups_processed,
        resolved_count,
        unknown_count,
        elapsed_total,
    )

    return (resolved_csv_path, unknown_csv_path)
