"""Project-wide statistics aggregator for the Statistics dashboard.

services_json + dest/clone_metrics/<project>_<language>.json を読み, 言語横断の
KPI / 言語別サマリ / サービス別サマリ を返す純粋な集計レイヤ. UI には依存しない.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import (
    DEST_CLONE_METRICS,
    get_clone_metrics_path,
    get_enriched_csv_dir,
    get_scatter_csv_dir,
    get_services_json_path,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectKPI:
    """1 プロジェクト全体の合計指標."""

    n_services: int
    n_files: int
    n_clone_sets: int
    total_loc: int
    total_clone_loc: int
    roc_pct: float  # 0-100


@dataclass(frozen=True)
class LanguageStat:
    """言語ごとの集計値."""

    language: str
    n_services: int
    n_files: int
    total_loc: int
    n_clone_sets: int
    n_clone_pairs: int
    n_comod_clone_sets: int
    n_comod_clone_pairs: int
    total_clone_loc: int
    roc_pct: float  # 0-100


@dataclass(frozen=True)
class ServiceStat:
    """サービス単位の集計値 (言語横断)."""

    service: str
    languages: tuple[str, ...]
    n_files: int
    total_loc: int
    n_clone_sets: int
    total_clone_loc: int
    roc_pct: float


@dataclass(frozen=True)
class ServiceLangStat:
    """サービス × 言語 単位の集計値."""

    service: str
    language: str
    n_files: int
    total_loc: int
    n_clone_sets: int


@dataclass(frozen=True)
class ProjectStats:
    kpi: ProjectKPI
    languages: list[LanguageStat] = field(default_factory=list)
    services: list[ServiceStat] = field(default_factory=list)
    service_lang_rows: list[ServiceLangStat] = field(default_factory=list)


@dataclass(frozen=True)
class _PairSummary:
    n_clone_pairs: int = 0
    n_comod_clone_pairs: int = 0
    n_comod_clone_sets: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_project_stats(project: str) -> ProjectStats | None:
    """Build a `ProjectStats` for `project` from on-disk artifacts.

    Returns ``None`` when the project's services.json is missing/unreadable.
    Missing per-language clone_metrics files are tolerated (treated as 0).
    """
    services_path = get_services_json_path(project)
    if not services_path.exists():
        logger.warning(
            "services_json missing for project=%s at %s", project, services_path
        )
        return None

    try:
        services_raw = _read_json(services_path)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(
            f"failed to read services_json for project={project} at {services_path}"
        ) from e

    language_stats_raw: dict[str, dict] = services_raw.get("language_stats", {}) or {}
    languages = _discover_languages(project, list(language_stats_raw.keys()))

    lang_summaries: list[LanguageStat] = []
    service_acc: dict[str, _ServiceAcc] = {}
    service_lang_acc: dict[tuple[str, str], _ServiceLangAcc] = {}

    for lang in languages:
        lang_info = language_stats_raw.get(lang, {})
        metrics_path = get_clone_metrics_path(project, lang)
        metrics = _read_clone_metrics(metrics_path)
        pair_summary = _read_pair_summary(project, lang)
        lang_summaries.append(
            _build_language_stat(lang, lang_info, metrics, pair_summary)
        )
        _accumulate_services(service_acc, lang, lang_info, metrics)
        _accumulate_service_lang(service_lang_acc, lang, lang_info, metrics)

    service_summaries = sorted(
        (acc.to_stat() for acc in service_acc.values()),
        key=lambda s: s.n_clone_sets,
        reverse=True,
    )
    service_lang_rows = sorted(
        (acc.to_stat() for acc in service_lang_acc.values()),
        key=lambda r: (r.language, r.service),
    )

    kpi = _build_kpi(lang_summaries, service_summaries)
    return ProjectStats(
        kpi=kpi,
        languages=lang_summaries,
        services=service_summaries,
        service_lang_rows=service_lang_rows,
    )


# ---------------------------------------------------------------------------
# Aggregation internals
# ---------------------------------------------------------------------------


@dataclass
class _ServiceAcc:
    service: str
    languages: set[str] = field(default_factory=set)
    n_files: int = 0
    total_loc: int = 0
    n_clone_sets: int = 0
    total_clone_loc: int = 0

    def to_stat(self) -> ServiceStat:
        roc = (
            (self.total_clone_loc / self.total_loc) * 100.0
            if self.total_loc > 0
            else 0.0
        )
        return ServiceStat(
            service=self.service,
            languages=tuple(sorted(self.languages)),
            n_files=self.n_files,
            total_loc=self.total_loc,
            n_clone_sets=self.n_clone_sets,
            total_clone_loc=self.total_clone_loc,
            roc_pct=round(roc, 2),
        )


@dataclass
class _ServiceLangAcc:
    service: str
    language: str
    n_files: int = 0
    total_loc: int = 0
    n_clone_sets: int = 0

    def to_stat(self) -> ServiceLangStat:
        return ServiceLangStat(
            service=self.service,
            language=self.language,
            n_files=self.n_files,
            total_loc=self.total_loc,
            n_clone_sets=self.n_clone_sets,
        )


def _accumulate_service_lang(
    acc: dict[tuple[str, str], _ServiceLangAcc],
    language: str,
    lang_info: dict,
    metrics: dict | None,
) -> None:
    services_dict = lang_info.get("services", {}) or {}
    for svc_name, svc_info in services_dict.items():
        key = (svc_name, language)
        entry = acc.setdefault(key, _ServiceLangAcc(service=svc_name, language=language))
        entry.n_files += int(svc_info.get("file_count", 0) or 0)
        entry.total_loc += int(svc_info.get("total_loc", 0) or 0)

    if metrics is None:
        return

    for svc_metric in metrics.get("service", []) or []:
        svc_name = svc_metric.get("service")
        if not svc_name:
            continue
        key = (svc_name, language)
        entry = acc.setdefault(key, _ServiceLangAcc(service=svc_name, language=language))
        entry.n_clone_sets += int(svc_metric.get("clone_set_count", 0) or 0)


def _build_language_stat(
    language: str,
    lang_info: dict,
    metrics: dict | None,
    pair_summary: _PairSummary,
) -> LanguageStat:
    total_loc = int(lang_info.get("total_loc", 0) or 0)
    total_files = int(lang_info.get("total_files", 0) or 0)
    services_dict = lang_info.get("services", {}) or {}
    n_services = len(services_dict)

    n_clone_sets = 0
    n_comod_clone_sets = pair_summary.n_comod_clone_sets
    total_clone_loc = 0
    if metrics is not None:
        clone_set_rows = metrics.get("clone_set", []) or []
        n_clone_sets = len(clone_set_rows)
        has_comod_count = any(
            "comod_count" in row
            for row in clone_set_rows
            if isinstance(row, dict)
        )
        if has_comod_count:
            n_comod_clone_sets = sum(
                1
                for row in clone_set_rows
                if isinstance(row, dict)
                and _to_int(row.get("comod_count", 0)) > 0
            )
        for svc_metric in metrics.get("service", []) or []:
            total_clone_loc += int(svc_metric.get("total_clone_line_count", 0) or 0)

    roc = (total_clone_loc / total_loc) * 100.0 if total_loc > 0 else 0.0
    return LanguageStat(
        language=language,
        n_services=n_services,
        n_files=total_files,
        total_loc=total_loc,
        n_clone_sets=n_clone_sets,
        n_clone_pairs=pair_summary.n_clone_pairs,
        n_comod_clone_sets=n_comod_clone_sets,
        n_comod_clone_pairs=pair_summary.n_comod_clone_pairs,
        total_clone_loc=total_clone_loc,
        roc_pct=round(roc, 2),
    )


def _accumulate_services(
    acc: dict[str, _ServiceAcc],
    language: str,
    lang_info: dict,
    metrics: dict | None,
) -> None:
    """Merge per-language per-service data into the cross-language accumulator."""
    services_dict = lang_info.get("services", {}) or {}
    for svc_name, svc_info in services_dict.items():
        entry = acc.setdefault(svc_name, _ServiceAcc(service=svc_name))
        entry.languages.add(language)
        entry.n_files += int(svc_info.get("file_count", 0) or 0)
        entry.total_loc += int(svc_info.get("total_loc", 0) or 0)

    if metrics is None:
        return

    for svc_metric in metrics.get("service", []) or []:
        svc_name = svc_metric.get("service")
        if not svc_name:
            continue
        entry = acc.setdefault(svc_name, _ServiceAcc(service=svc_name))
        entry.languages.add(language)
        entry.n_clone_sets += int(svc_metric.get("clone_set_count", 0) or 0)
        entry.total_clone_loc += int(svc_metric.get("total_clone_line_count", 0) or 0)


def _build_kpi(
    languages: list[LanguageStat],
    services: list[ServiceStat],
) -> ProjectKPI:
    n_services = len(services)
    n_files = sum(lang.n_files for lang in languages)
    total_loc = sum(lang.total_loc for lang in languages)
    total_clone_loc = sum(lang.total_clone_loc for lang in languages)
    n_clone_sets = sum(lang.n_clone_sets for lang in languages)
    roc = (total_clone_loc / total_loc) * 100.0 if total_loc > 0 else 0.0
    return ProjectKPI(
        n_services=n_services,
        n_files=n_files,
        n_clone_sets=n_clone_sets,
        total_loc=total_loc,
        total_clone_loc=total_clone_loc,
        roc_pct=round(roc, 2),
    )


# ---------------------------------------------------------------------------
# Clone pair summaries
# ---------------------------------------------------------------------------


def _read_pair_summary(project: str, language: str) -> _PairSummary:
    """Read clone-pair counts for one language.

    The scatter CSV is already row-per-clone-pair, so prefer it when available.
    If it has not been generated yet, fall back to enriched fragments and derive
    pair counts from each clone set's fragment combinations.
    """
    scatter_csv = _select_scatter_csv(project, language)
    if scatter_csv is not None:
        return _read_scatter_pair_summary(scatter_csv)
    return _read_enriched_pair_summary(project, language)


def _select_scatter_csv(project: str, language: str) -> Path | None:
    csv_dir = get_scatter_csv_dir(project)
    if not csv_dir.exists():
        return None

    from .project_discovery import _parse_scatter_csv_filename

    candidates: list[tuple[tuple[int, int, int, int], Path]] = []
    for csv_path in csv_dir.iterdir():
        if not csv_path.is_file() or csv_path.suffix != ".csv":
            continue
        if csv_path.name.endswith("_unknown.csv"):
            continue
        info = _parse_scatter_csv_filename(csv_path.name)
        if not info:
            continue
        if str(info.get("language", "")).lower() != language.lower():
            continue
        try:
            date_rank = int(info.get("date") or 0)
        except (TypeError, ValueError):
            date_rank = 0
        filtered_rank = 1 if info.get("filter") == "filtered" else 0
        cloneset_rank = 1 if info.get("comod") == "cloneset" else 0
        size_rank = csv_path.stat().st_size
        candidates.append(
            ((date_rank, filtered_rank, cloneset_rank, size_rank), csv_path)
        )

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _read_scatter_pair_summary(csv_path: Path) -> _PairSummary:
    n_pairs = 0
    n_comod_pairs = 0
    comod_clone_ids: set[str] = set()

    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                n_pairs += 1
                is_comod = _row_is_comodified(row)
                if not is_comod:
                    continue
                n_comod_pairs += 1
                clone_id = str(row.get("clone_id") or "").strip()
                if clone_id:
                    comod_clone_ids.add(clone_id)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        logger.warning("failed to read scatter pair summary at %s: %s", csv_path, e)
        return _PairSummary()

    return _PairSummary(
        n_clone_pairs=n_pairs,
        n_comod_clone_pairs=n_comod_pairs,
        n_comod_clone_sets=len(comod_clone_ids),
    )


def _row_is_comodified(row: dict) -> bool:
    if "comodification_count" in row:
        return _to_int(row.get("comodification_count", 0)) > 0
    raw = str(row.get("comodified", "")).strip().lower()
    return raw in {"1", "true", "yes"}


def _read_enriched_pair_summary(project: str, language: str) -> _PairSummary:
    csv_path = get_enriched_csv_dir(project) / f"{language}.csv"
    if not csv_path.exists():
        return _PairSummary()

    grouped_commits: dict[str, list[set[str]]] = {}
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            delimiter = _detect_delimiter(sample)
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                clone_id = str(row.get("clone_id") or "").strip()
                if not clone_id:
                    continue
                commits = _parse_commit_list(row.get("modified_commits", "[]"))
                grouped_commits.setdefault(clone_id, []).append(commits)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        logger.warning("failed to read enriched pair summary at %s: %s", csv_path, e)
        return _PairSummary()

    n_pairs = 0
    n_comod_pairs = 0
    n_comod_sets = 0
    for commit_sets in grouped_commits.values():
        n = len(commit_sets)
        n_pairs += n * (n - 1) // 2
        set_has_comod = False
        for i in range(n):
            for j in range(i + 1, n):
                if commit_sets[i] & commit_sets[j]:
                    n_comod_pairs += 1
                    set_has_comod = True
        if set_has_comod:
            n_comod_sets += 1

    return _PairSummary(
        n_clone_pairs=n_pairs,
        n_comod_clone_pairs=n_comod_pairs,
        n_comod_clone_sets=n_comod_sets,
    )


def _detect_delimiter(sample: str) -> str:
    first_line = sample.splitlines()[0] if sample.splitlines() else sample
    if first_line.count(";") > first_line.count(","):
        return ";"
    return ","


def _parse_commit_list(raw: object) -> set[str]:
    if not raw:
        return set()
    try:
        data = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return set()
    if not isinstance(data, list):
        return set()

    commits: set[str] = set()
    for item in data:
        if isinstance(item, str) and item:
            commits.add(item)
        elif isinstance(item, dict):
            commit = item.get("commit")
            if isinstance(commit, str) and commit:
                commits.add(commit)
    return commits


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_clone_metrics(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return _read_json(path)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("failed to read clone_metrics at %s: %s", path, e)
        raise RuntimeError(f"failed to read clone_metrics at {path}") from e


def _discover_languages(project: str, declared: list[str]) -> list[str]:
    """services_json に出ていない言語もディスクから拾う.

    過去データで language_stats が無い場合に備え,
    dest/clone_metrics/<project>_<lang>.json から逆引きで補完する.
    """
    seen = {lang for lang in declared if lang}
    prefix = f"{project}_"
    if DEST_CLONE_METRICS.exists():
        for child in DEST_CLONE_METRICS.iterdir():
            if not child.is_file() or child.suffix != ".json":
                continue
            name = child.stem
            if not name.startswith(prefix):
                continue
            lang = name[len(prefix):]
            if lang and lang not in seen:
                seen.add(lang)
    return sorted(seen)
