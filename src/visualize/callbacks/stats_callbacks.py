"""Callbacks for the Metric View clone metrics explorer — 3-tab edition.

タブ:
  Service Base — service テーブル
  CS Base      — clone_set テーブル + ドリルダウン (fragments/code)
  File Base    — file テーブル

Service/File Base は関連 Clone Sets 一覧を挟んで同じ fragments/code 詳細に進む.
"""

from __future__ import annotations

import logging
from html import escape
from pathlib import Path
from typing import Any

import dash
import pandas as pd
from dash import Input, Output, State, callback_context, html, no_update

from ..components.stats_metrics_explorer import (
    CS_RANGE_FIELDS,
    CS_TABLE_COLUMNS,
    DEFAULT_PAGE_SIZE,
    FILE_RANGE_FIELDS,
    FILE_TABLE_COLUMNS,
    MS_RANGE_FIELDS,
    MS_TABLE_COLUMNS,
    _range_value_label_id,
    stats_fragment_columns,
    stats_table_data_conditional,
)
from ..data_loader.metrics_loader import load_metrics_dataframes
from .list_view_callbacks import _build_dual_code_panes, _build_single_code_pane

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------------------------


def _parse_project(project_value: str | None) -> tuple[str | None, str | None, str | None]:
    if not project_value:
        return None, None, None
    try:
        project, commit, language = project_value.split("|||", 2)
        return project, commit, language
    except (ValueError, AttributeError):
        return None, None, None


def _as_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value)


def _csv_tokens(value: object) -> set[str]:
    return {token.strip() for token in _as_text(value).split(",") if token.strip()}


def _num(value: object, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        val = float(value)
        if pd.isna(val):
            return default
        return val
    except (TypeError, ValueError):
        return default


def _apply_range(
    df: pd.DataFrame,
    column: str,
    min_value: object,
    max_value: object,
) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return df
    series = pd.to_numeric(df[column], errors="coerce")
    low = _num(min_value)
    high = _num(max_value)
    if low is not None:
        df = df[series >= low]
        series = pd.to_numeric(df[column], errors="coerce")
    if high is not None:
        df = df[series <= high]
    return df


def _summary_card(label: str, value: object) -> html.Div:
    return html.Div(
        [
            html.Div(label, className="stats-summary-label"),
            html.Div(str(value), className="stats-summary-value"),
        ],
        className="stats-summary-card",
    )


def _empty_summary(message: str = "Select a project to inspect clone metrics.") -> list:
    return [
        html.Div(
            [
                html.Div("Status", className="stats-summary-label"),
                html.Div(message, className="stats-summary-value"),
            ],
            className="stats-summary-card",
        )
    ]


def _cs_tooltip_data(records: list[dict]) -> list[dict]:
    """カンマ区切りで詰めた file_types / involved_services を hover で全文表示."""
    tooltips: list[dict] = []
    for row in records:
        cell_tips: dict[str, dict] = {}
        for col in ("file_types", "involved_services"):
            text = _as_text(row.get(col))
            if text:
                cell_tips[col] = {"value": text, "type": "text"}
        tooltips.append(cell_tips)
    return tooltips


def _format_number_for_label(value: object, step: float | int) -> str:
    number = _num(value)
    if number is None:
        return "-"
    if float(step).is_integer() and float(number).is_integer():
        return f"{int(number):,}"
    return f"{number:,.1f}".rstrip("0").rstrip(".")


def _range_value_label(value: list | tuple | None, unit: str, step: float | int) -> str:
    if not value or len(value) != 2:
        return "-"
    suffix = f" {unit}" if unit else ""
    lo = _format_number_for_label(value[0], step)
    hi = _format_number_for_label(value[1], step)
    return f"{lo} - {hi}{suffix}"


def _compact_services_markdown(value: object, limit: int = 3) -> str:
    services = [token.strip() for token in _as_text(value).split(",") if token.strip()]
    if len(services) <= limit:
        return ", ".join(escape(service) for service in services)

    shown = ", ".join(escape(service) for service in services[:limit])
    hidden = "<br>".join(escape(service) for service in services[limit:])
    total = len(services)
    remaining = total - limit
    return (
        f"{shown}"
        f"<details class=\"stats-services-details\">"
        f"<summary>Show all {total} services (+{remaining})</summary>"
        f"<div class=\"stats-services-details-body\">{hidden}</div>"
        f"</details>"
    )


def _compact_services_records(records: list[dict]) -> list[dict]:
    compacted: list[dict] = []
    for record in records:
        next_record = dict(record)
        next_record["involved_services"] = _compact_services_markdown(
            record.get("involved_services")
        )
        compacted.append(next_record)
    return compacted


def _records_for_table(df: pd.DataFrame, columns: list[dict]) -> list[dict]:
    if df.empty:
        return []
    col_ids = [c["id"] for c in columns]
    out = df.copy()
    for col in col_ids:
        if col not in out.columns:
            out[col] = None
    return out[col_ids].where(pd.notna(out[col_ids]), None).to_dict("records")


def _options_from_tokens(df: pd.DataFrame, column: str) -> list[dict]:
    if df.empty or column not in df.columns:
        return []
    values: set[str] = set()
    for value in df[column].dropna():
        values.update(_csv_tokens(value))
    return [{"label": item, "value": item} for item in sorted(values, key=str.lower)]


def _options_from_unique(df: pd.DataFrame, column: str) -> list[dict]:
    if df.empty or column not in df.columns:
        return []
    values = sorted({str(v) for v in df[column].dropna() if str(v)})
    return [{"label": v, "value": v} for v in values]


def _column_range(df: pd.DataFrame, column: str, step: float | int) -> tuple[float, float]:
    """データから (min, max) を求める. 値が無ければ (0, 1) を返す."""
    if df.empty or column not in df.columns:
        return (0.0, 1.0)
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    if series.empty:
        return (0.0, 1.0)
    lo = float(series.min())
    hi = float(series.max())
    if lo == hi:
        hi = lo + (1.0 if step >= 1 else 0.1)
    if step >= 1:
        lo = float(int(lo))
        hi = float(int(hi) + (1 if hi != int(hi) else 0))
    else:
        lo = round(lo, 2)
        hi = round(hi, 2)
    return (lo, hi)


def _page_info_text(total_rows: int, page_current: int | None, page_size: int | None) -> str:
    if total_rows <= 0:
        return "0 rows"
    size = page_size or DEFAULT_PAGE_SIZE
    current = (page_current or 0) + 1
    pages = max(1, (total_rows + size - 1) // size)
    start = (current - 1) * size + 1
    end = min(current * size, total_rows)
    return f"{start:,}-{end:,} / {total_rows:,} rows  ·  Page {current} / {pages}"


def _default_context() -> dict[str, Any]:
    return {"scope_type": "all", "scope_value": None, "scope_label": ""}


def _context_type(context: dict | None) -> str:
    if not isinstance(context, dict):
        return "all"
    return str(context.get("scope_type") or "all")


def _context_label(context: dict | None) -> str:
    if not isinstance(context, dict):
        return ""
    return _as_text(context.get("scope_label") or context.get("scope_value"))


def _is_scoped_context(context: dict | None) -> bool:
    return _context_type(context) in {"ms", "file"} and bool(
        isinstance(context, dict) and context.get("scope_value")
    )


def _base_label(tab: str | None) -> str:
    return {
        "ms": "Service Base",
        "cs": "Clone Set Base",
        "file": "File Base",
    }.get(tab or "", "Metric View")


def _is_loading_state(value: object) -> bool:
    return isinstance(value, dict) and bool(value.get("is_loading"))


def _home_guide(title: str, copy: str, *, loading: bool = False) -> list:
    title_children: list[Any] = []
    if loading:
        title_children.append(html.Span(className="stats-home-loading-spinner"))
    title_children.append(html.Span(title))
    return [
        html.Div(title_children, className="stats-home-guide-title"),
        html.Div(copy, className="stats-home-guide-copy"),
    ]


# ---------------------------------------------------------------------------
# データ構築
# ---------------------------------------------------------------------------


def _build_ms_dataframe(metrics: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = metrics.get("service", pd.DataFrame()).copy()
    if df.empty or "service" not in df.columns:
        return df
    if "roc" in df.columns:
        df["roc_pct"] = (pd.to_numeric(df["roc"], errors="coerce") * 100).round(2)
    return df


def _build_cs_dataframe(metrics: dict[str, pd.DataFrame]) -> pd.DataFrame:
    cs_df = metrics.get("clone_set", pd.DataFrame()).copy()
    frags = metrics.get("fragments", pd.DataFrame())
    if cs_df.empty or "clone_id" not in cs_df.columns:
        return cs_df

    cs_df["clone_id"] = cs_df["clone_id"].astype(str)

    if "cross_service_fragment_ratio" in cs_df.columns:
        cs_df["inter_frag_ratio_pct"] = (
            pd.to_numeric(cs_df["cross_service_fragment_ratio"], errors="coerce") * 100
        ).round(1)
    if "comod_fragment_ratio" in cs_df.columns:
        cs_df["comod_frag_ratio_pct"] = (
            pd.to_numeric(cs_df["comod_fragment_ratio"], errors="coerce") * 100
        ).round(1)

    if not frags.empty and "clone_id" in frags.columns:
        frag_ids = frags["clone_id"].astype(str)
        frag_counts = frag_ids.value_counts().rename("n_total_fragments")
        if "n_total_fragments" not in cs_df.columns:
            cs_df["n_total_fragments"] = cs_df["clone_id"].map(frag_counts).fillna(0).astype(int)

        if "file_types" not in cs_df.columns and "file_type" in frags.columns:
            file_type_map = (
                frags.assign(_clone_id=frag_ids)
                .groupby("_clone_id")["file_type"]
                .agg(lambda s: ", ".join(sorted({str(x) for x in s.dropna() if str(x)})))
            )
            cs_df["file_types"] = cs_df["clone_id"].map(file_type_map).fillna("")

        if "involved_services" not in cs_df.columns and "service" in frags.columns:
            svc_map = (
                frags.assign(_clone_id=frag_ids)
                .groupby("_clone_id")["service"]
                .agg(lambda s: ", ".join(sorted({str(x) for x in s.dropna() if str(x)})))
            )
            cs_df["involved_services"] = cs_df["clone_id"].map(svc_map).fillna("")

    for col in ("file_types", "involved_services"):
        if col not in cs_df.columns:
            cs_df[col] = ""
        cs_df[col] = cs_df[col].astype("string").fillna("").astype(str)

    if "n_total_fragments" not in cs_df.columns:
        cs_df["n_total_fragments"] = 0

    return cs_df


def _build_file_dataframe(metrics: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = metrics.get("file", pd.DataFrame()).copy()
    if df.empty or "file_path" not in df.columns:
        return df
    df["file_name"] = df["file_path"].astype(str).apply(lambda p: Path(p).name)
    if "sharing_service_ratio" in df.columns:
        df["sharing_service_ratio_pct"] = (
            pd.to_numeric(df["sharing_service_ratio"], errors="coerce") * 100
        ).round(1)
    if "cross_service_clone_set_ratio" in df.columns:
        df["cross_cs_ratio_pct"] = (
            pd.to_numeric(df["cross_service_clone_set_ratio"], errors="coerce") * 100
        ).round(1)
    if "service" in df.columns:
        df["service"] = df["service"].astype("string").fillna("").astype(str)
    if "file_type" in df.columns:
        df["file_type"] = df["file_type"].astype("string").fillna("").astype(str)
    return df


def _apply_cs_context(
    df: pd.DataFrame,
    metrics: dict[str, pd.DataFrame],
    context: dict | None,
) -> pd.DataFrame:
    """Limit clone sets to the selected MS/file context before table filters."""
    if df.empty or not _is_scoped_context(context):
        return df
    frags = metrics.get("fragments", pd.DataFrame())
    if frags.empty or "clone_id" not in frags.columns:
        return df.iloc[0:0].copy()

    scope_type = _context_type(context)
    scope_value = _as_text(context.get("scope_value") if isinstance(context, dict) else "")
    if not scope_value:
        return df

    if scope_type == "ms":
        if "service" not in frags.columns:
            return df.iloc[0:0].copy()
        matches = frags[frags["service"].astype(str) == scope_value]
    elif scope_type == "file":
        if "file_path" not in frags.columns:
            return df.iloc[0:0].copy()
        matches = frags[frags["file_path"].astype(str) == scope_value]
    else:
        return df

    clone_ids = set(matches["clone_id"].astype(str))
    if not clone_ids:
        return df.iloc[0:0].copy()
    return df[df["clone_id"].astype(str).isin(clone_ids)].copy()


# ---------------------------------------------------------------------------
# CS 用フィルタ
# ---------------------------------------------------------------------------


def _filter_cs_dataframe(
    df: pd.DataFrame,
    *,
    preset: str | None,
    ranges: dict[str, tuple[object, object]],
    file_types: list[str] | None,
    services: list[str] | None,
    clone_id_query: str | None,
) -> pd.DataFrame:
    filtered = df.copy()

    if preset == "cross2":
        filtered = _apply_range(filtered, "service_count", 2, None)
    elif preset == "comod1":
        filtered = _apply_range(filtered, "comod_count", 1, None)
    elif preset == "top_inter_loc" and "cross_service_line_count" in filtered.columns:
        loc = pd.to_numeric(filtered["cross_service_line_count"], errors="coerce")
        threshold = loc.quantile(0.75)
        if pd.notna(threshold):
            filtered = filtered[loc >= threshold]

    for col, (lo, hi) in ranges.items():
        filtered = _apply_range(filtered, col, lo, hi)

    if file_types:
        wanted = {str(x).lower() for x in file_types}
        filtered = filtered[
            filtered["file_types"].apply(
                lambda value: bool({x.lower() for x in _csv_tokens(value)} & wanted)
            )
        ]

    if services:
        wanted_services = {str(x) for x in services}
        filtered = filtered[
            filtered["involved_services"].apply(
                lambda value: bool(_csv_tokens(value) & wanted_services)
            )
        ]

    if clone_id_query:
        query = str(clone_id_query).strip().lower()
        if query:
            filtered = filtered[filtered["clone_id"].str.lower().str.contains(query, na=False)]

    sort_cols = [
        col
        for col in ("comod_count", "service_count", "cross_service_line_count")
        if col in filtered.columns
    ]
    if sort_cols:
        filtered = filtered.sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last")
    return filtered


def _filter_ms_dataframe(
    df: pd.DataFrame,
    *,
    ranges: dict[str, tuple[object, object]],
    name_query: str | None,
) -> pd.DataFrame:
    filtered = df.copy()
    for col, (lo, hi) in ranges.items():
        filtered = _apply_range(filtered, col, lo, hi)
    if name_query:
        q = str(name_query).strip().lower()
        if q:
            filtered = filtered[filtered["service"].astype(str).str.lower().str.contains(q, na=False)]
    sort_cols = [c for c in ("clone_set_count", "inter_clone_set_count") if c in filtered.columns]
    if sort_cols:
        filtered = filtered.sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last")
    return filtered


def _filter_file_dataframe(
    df: pd.DataFrame,
    *,
    ranges: dict[str, tuple[object, object]],
    file_type: str | None,
    services: list[str] | None,
    name_query: str | None,
) -> pd.DataFrame:
    filtered = df.copy()
    for col, (lo, hi) in ranges.items():
        filtered = _apply_range(filtered, col, lo, hi)
    if file_type and file_type != "all" and "file_type" in filtered.columns:
        filtered = filtered[filtered["file_type"].astype(str).str.lower() == file_type.lower()]
    if services:
        wanted = {str(x) for x in services}
        filtered = filtered[filtered["service"].astype(str).isin(wanted)]
    if name_query:
        q = str(name_query).strip().lower()
        if q:
            filtered = filtered[filtered["file_name"].astype(str).str.lower().str.contains(q, na=False)]
    sort_cols = [c for c in ("sharing_service_count", "cross_service_clone_set_count") if c in filtered.columns]
    if sort_cols:
        filtered = filtered.sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last")
    return filtered


# ---------------------------------------------------------------------------
# 詳細パネル (CS Step 2)
# ---------------------------------------------------------------------------


def _empty_detail_panel() -> html.Div:
    return html.Div(
        [
            html.I(className="bi bi-diagram-3 stats-empty-icon"),
            html.Div("Select a clone set", className="stats-empty-title"),
            html.Div(
                "Click a clone set row to view its fragments.",
                className="stats-empty-copy",
            ),
        ],
        className="stats-detail-empty",
    )


def _detail_summary(clone_id: str, metrics: dict[str, pd.DataFrame]) -> html.Div:
    cs_df = _build_cs_dataframe(metrics)
    row = cs_df[cs_df["clone_id"] == str(clone_id)]
    if row.empty:
        return _empty_detail_panel()
    item = row.iloc[0]

    def badge(label: str, value: Any) -> html.Span:
        return html.Span(
            [
                html.Span(f"{label}: ", className="stats-cs-badge-label"),
                html.Span(_as_text(value) or "-"),
            ],
            className="stats-cs-badge",
        )

    return html.Div(
        [
            html.Div(f"Clone Set #{clone_id}", className="stats-cs-title"),
            html.Div(
                [
                    badge("Service Span", item.get("service_count")),
                    badge("Comod", item.get("comod_count")),
                    badge("Comod Frag %", item.get("comod_frag_ratio_pct")),
                    badge("Inter LOC", item.get("cross_service_line_count")),
                    badge("Inter %", item.get("inter_frag_ratio_pct")),
                    badge("Category", item.get("file_types")),
                ],
                className="stats-cs-badges",
            ),
        ],
        className="stats-cs-summary-bar",
    )


def _fragment_records(clone_id: str, metrics: dict[str, pd.DataFrame]) -> list[dict]:
    frags = metrics.get("fragments", pd.DataFrame())
    if frags.empty or "clone_id" not in frags.columns:
        return []
    subset = frags[frags["clone_id"].astype(str) == str(clone_id)].copy()
    if subset.empty:
        return []
    if "file_path" in subset.columns:
        subset["file_short"] = subset["file_path"].apply(lambda p: Path(str(p)).name)
    else:
        subset["file_short"] = ""
    if {"start_line", "end_line"}.issubset(subset.columns):
        subset["lines"] = subset["start_line"].astype(str) + "-" + subset["end_line"].astype(str)
    else:
        subset["lines"] = ""
    for col in ("service", "file_type"):
        if col not in subset.columns:
            subset[col] = ""
        subset[col] = subset[col].astype("string").fillna("").astype(str)

    if "modified_count" in subset.columns:
        subset["mod_count"] = pd.to_numeric(subset["modified_count"], errors="coerce").astype("Int64")
    else:
        subset["mod_count"] = None

    def _abbrev_commits(raw) -> str:
        if not raw or str(raw) in ("", "[]", "nan"):
            return ""
        try:
            import json as _json
            commits = _json.loads(str(raw))
        except Exception:
            return ""
        if not isinstance(commits, list):
            return ""
        short = [str(c)[:7] for c in commits if c]
        if len(short) <= 3:
            return ", ".join(short)
        return ", ".join(short[:3]) + f" …+{len(short) - 3}"

    if "modified_commits" in subset.columns:
        subset["mod_commits"] = subset["modified_commits"].apply(_abbrev_commits)
    else:
        subset["mod_commits"] = ""

    visible_ids = [c["id"] for c in stats_fragment_columns()]
    hidden_ids = ["file_path", "start_line", "end_line"]
    all_ids = visible_ids + [c for c in hidden_ids if c not in visible_ids]
    for col in all_ids:
        if col not in subset.columns:
            subset[col] = None
    return subset[all_ids].where(pd.notna(subset[all_ids]), None).to_dict("records")


def _code_placeholder(text: str = "Select one or two fragments to view code.") -> html.Div:
    return html.Div(text, className="stats-code-placeholder")


def _hidden_breadcrumb_back_link() -> html.Li:
    return html.Li(
        html.Button(
            "Clone Sets",
            id="stats-breadcrumb-clone-sets-link",
            className="stats-breadcrumb-link",
            n_clicks=0,
        ),
        className="stats-breadcrumb-item",
        style={"display": "none"},
    )


def _hidden_breadcrumb_home_link() -> html.Li:
    return html.Li(
        html.Button(
            "Metric View",
            id="stats-breadcrumb-home-link",
            className="stats-breadcrumb-link",
            n_clicks=0,
        ),
        className="stats-breadcrumb-item",
        style={"display": "none"},
    )


def _hidden_breadcrumb_base_link() -> html.Li:
    return html.Li(
        html.Button(
            "Metric Base",
            id="stats-breadcrumb-base-link",
            className="stats-breadcrumb-link",
            n_clicks=0,
        ),
        className="stats-breadcrumb-item",
        style={"display": "none"},
    )


def _breadcrumb_root_link() -> html.Li:
    return html.Li(
        html.Button(
            "Metric View",
            id="stats-breadcrumb-home-link",
            className="stats-breadcrumb-link",
            n_clicks=0,
        ),
        className="stats-breadcrumb-item",
    )


def _breadcrumb_base_link(tab: str | None) -> html.Li:
    return html.Li(
        html.Button(
            _base_label(tab),
            id="stats-breadcrumb-base-link",
            className="stats-breadcrumb-link",
            n_clicks=0,
        ),
        className="stats-breadcrumb-item",
    )


def _breadcrumb_active(tab: str) -> list:
    return [
        _breadcrumb_root_link(),
        _hidden_breadcrumb_base_link(),
        _hidden_breadcrumb_back_link(),
        html.Li(
            html.Span(_base_label(tab), className="stats-breadcrumb-current"),
            className="stats-breadcrumb-item active",
        ),
    ]


def _breadcrumb_clone_sets() -> list:
    return [
        _breadcrumb_root_link(),
        _hidden_breadcrumb_base_link(),
        _hidden_breadcrumb_back_link(),
        html.Li(
            html.Span("Clone Set Base", className="stats-breadcrumb-current"),
            className="stats-breadcrumb-item active",
        ),
    ]


def _breadcrumb_context_clone_sets(active_tab: str | None, context: dict | None) -> list:
    label = _context_label(context)
    return [
        _breadcrumb_root_link(),
        _breadcrumb_base_link(active_tab),
        _hidden_breadcrumb_back_link(),
        html.Li(
            html.Span(label or "Clone Sets", className="stats-breadcrumb-current"),
            className="stats-breadcrumb-item active",
        ),
    ]


def _breadcrumb_fragments(
    clone_id: str,
    active_tab: str | None = "cs",
    context: dict | None = None,
) -> list:
    if _is_scoped_context(context):
        return [
            _breadcrumb_root_link(),
            _breadcrumb_base_link(active_tab),
            html.Li(
                html.Button(
                    _context_label(context) or "Clone Sets",
                    id="stats-breadcrumb-clone-sets-link",
                    className="stats-breadcrumb-link",
                    n_clicks=0,
                ),
                className="stats-breadcrumb-item",
            ),
            html.Li(
                html.Span(f"Clone Set #{clone_id}", className="stats-breadcrumb-current"),
                className="stats-breadcrumb-item active",
            ),
        ]
    return [
        _breadcrumb_root_link(),
        _hidden_breadcrumb_base_link(),
        html.Li(
            html.Button(
                "Clone Set Base",
                id="stats-breadcrumb-clone-sets-link",
                className="stats-breadcrumb-link",
                n_clicks=0,
            ),
            className="stats-breadcrumb-item",
        ),
        html.Li(
            html.Span(f"Clone Set #{clone_id}", className="stats-breadcrumb-current"),
            className="stats-breadcrumb-item active",
        ),
    ]


def _summary_for_dataset(metrics: dict[str, pd.DataFrame]) -> list:
    ms_df = _build_ms_dataframe(metrics)
    cs_df = _build_cs_dataframe(metrics)
    file_df = _build_file_dataframe(metrics)
    return [
        _summary_card("# Services", f"{len(ms_df):,}"),
        _summary_card("# Clone Sets", f"{len(cs_df):,}"),
        _summary_card("# Files", f"{len(file_df):,}"),
    ]


# ---------------------------------------------------------------------------
# RangeSlider 同期ヘルパー
# ---------------------------------------------------------------------------


def _resolve_range_value(
    slider_value: list | None,
    min_input: object,
    max_input: object,
    bounds: tuple[float, float],
    triggered_id: str | None,
    slider_id: str,
    min_id: str,
    max_id: str,
) -> tuple[list[float], float | None, float | None]:
    """slider / min input / max input を同期した最終 (value, min_in, max_in) を返す."""
    lo_bound, hi_bound = bounds
    # initial / no source: full range
    if slider_value is None and min_input in (None, "") and max_input in (None, ""):
        return [lo_bound, hi_bound], lo_bound, hi_bound
    if triggered_id == min_id or triggered_id == max_id:
        lo_v = _num(min_input, lo_bound)
        hi_v = _num(max_input, hi_bound)
        if lo_v is None:
            lo_v = lo_bound
        if hi_v is None:
            hi_v = hi_bound
        if lo_v > hi_v:
            lo_v, hi_v = hi_v, lo_v
        lo_v = max(lo_bound, min(hi_bound, lo_v))
        hi_v = max(lo_bound, min(hi_bound, hi_v))
        return [lo_v, hi_v], lo_v, hi_v
    # slider drives
    if slider_value and len(slider_value) == 2:
        lo_v = float(slider_value[0])
        hi_v = float(slider_value[1])
        return [lo_v, hi_v], lo_v, hi_v
    return [lo_bound, hi_bound], lo_bound, hi_bound


# ---------------------------------------------------------------------------
# Callback 登録
# ---------------------------------------------------------------------------


def register_stats_callbacks(app: dash.Dash, app_data: dict) -> None:
    """Register callbacks for the 3-tab Statistics clone metrics explorer."""

    _register_tab_switcher(app)
    _register_home_state(app)
    _register_summary(app)
    _register_range_sliders(app, "ms", MS_RANGE_FIELDS, _build_ms_dataframe)
    _register_range_sliders(app, "cs", CS_RANGE_FIELDS, _build_cs_dataframe)
    _register_range_sliders(app, "file", FILE_RANGE_FIELDS, _build_file_dataframe)
    _register_ms_table(app)
    _register_cs_table(app)
    _register_file_table(app)
    _register_drilldown(app)
    _register_fragment_detail(app)


# ── タブ切替 ────────────────────────────────────────────────────────────


def _register_tab_switcher(app: dash.Dash) -> None:
    @app.callback(
        [
            Output("stats-active-tab", "data"),
            Output("stats-drilldown-step", "data", allow_duplicate=True),
            Output("stats-selected-clone-store", "data", allow_duplicate=True),
            Output("stats-drilldown-context-store", "data", allow_duplicate=True),
            Output("stats-tab-ms", "className"),
            Output("stats-tab-cs", "className"),
            Output("stats-tab-file", "className"),
        ],
        [
            Input("stats-tab-ms", "n_clicks"),
            Input("stats-tab-cs", "n_clicks"),
            Input("stats-tab-file", "n_clicks"),
            Input("stats-breadcrumb-home-link", "n_clicks"),
        ],
        [
            State("stats-active-tab", "data"),
            State("project-name-selector", "value"),
            State("project-selector", "value"),
        ],
        prevent_initial_call=True,
    )
    def switch_tab(_ms_n, _cs_n, _file_n, _home_n, current, project_name, dataset):
        triggered = callback_context.triggered_id
        active = current or "home"
        if triggered == "stats-breadcrumb-home-link":
            if (
                not callback_context.triggered
                or not callback_context.triggered[0].get("value")
            ):
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                )
            active = "home"
        elif triggered == "stats-tab-ms":
            if not project_name or not dataset:
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update
            active = "ms"
        elif triggered == "stats-tab-cs":
            if not project_name or not dataset:
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update
            active = "cs"
        elif triggered == "stats-tab-file":
            if not project_name or not dataset:
                return no_update, no_update, no_update, no_update, no_update, no_update, no_update
            active = "file"

        def cls(tab: str) -> str:
            return "stats-home-card active" if active == tab else "stats-home-card"

        step = "clone_sets" if active == "cs" else "base"
        return active, step, None, _default_context(), cls("ms"), cls("cs"), cls("file")

    @app.callback(
        [
            Output("stats-home-step", "style"),
            Output("stats-explorer-header", "style"),
            Output("stats-breadcrumb", "style"),
            Output("stats-step-ms", "style"),
            Output("stats-step-cs", "style"),
            Output("stats-step-file", "style"),
            Output("stats-step-fragments", "style"),
            Output("stats-breadcrumb-list", "children"),
            Output("stats-breadcrumb-back-to-list", "style"),
        ],
        [
            Input("stats-active-tab", "data"),
            Input("stats-drilldown-step", "data"),
            Input("stats-selected-clone-store", "data"),
            Input("stats-drilldown-context-store", "data"),
        ],
        prevent_initial_call=False,
    )
    def update_visibility(active_tab, step, clone_id, context):
        active_tab = active_tab or "home"
        step = step or ("clone_sets" if active_tab == "cs" else "base")
        hidden = {"display": "none"}
        home_visible = {
            "display": "flex",
            "flexDirection": "column",
        }
        header_visible = {}
        breadcrumb_visible = {}
        table_visible = {"display": "grid"}
        fragments_visible = {"display": "flex", "flexDirection": "column"}

        if active_tab == "home":
            return (
                home_visible,
                header_visible,
                {"display": "none"},
                hidden,
                hidden,
                hidden,
                hidden,
                [
                    _hidden_breadcrumb_home_link(),
                    _hidden_breadcrumb_base_link(),
                    _hidden_breadcrumb_back_link(),
                ],
                {"display": "none"},
            )

        if step == "fragments" and clone_id:
            return (
                hidden,
                hidden,
                breadcrumb_visible,
                hidden,
                hidden,
                hidden,
                fragments_visible,
                _breadcrumb_fragments(str(clone_id), active_tab, context),
                {"display": "none"},
            )

        if active_tab in ("ms", "file") and step == "clone_sets" and _is_scoped_context(context):
            return (
                hidden,
                hidden,
                breadcrumb_visible,
                hidden,
                table_visible,
                hidden,
                hidden,
                _breadcrumb_context_clone_sets(active_tab, context),
                {"display": "none"},
            )

        if active_tab == "cs":
            return (
                hidden,
                hidden,
                breadcrumb_visible,
                hidden,
                table_visible,
                hidden,
                hidden,
                _breadcrumb_clone_sets(),
                {"display": "none"},
            )

        return (
            hidden,
            hidden,
            breadcrumb_visible,
            table_visible if active_tab == "ms" else hidden,
            hidden,
            table_visible if active_tab == "file" else hidden,
            hidden,
            _breadcrumb_active(active_tab),
            {"display": "none"},
        )


def _register_home_state(app: dash.Dash) -> None:
    @app.callback(
        [
            Output("stats-tab-ms", "disabled"),
            Output("stats-tab-cs", "disabled"),
            Output("stats-tab-file", "disabled"),
            Output("stats-home-selection-guide", "children"),
            Output("stats-home-selection-guide", "className"),
        ],
        [
            Input("project-name-selector", "value"),
            Input("project-selector", "value"),
            Input("project-name-selector", "loading_state"),
            Input("project-selector", "loading_state"),
            Input("project-selector", "options"),
            Input("project-selector", "disabled"),
        ],
        prevent_initial_call=False,
    )
    def update_home_state(
        project_name,
        dataset,
        project_loading_state,
        dataset_loading_state,
        dataset_options,
        dataset_disabled,
    ):
        dataset_project, _commit, _language = _parse_project(dataset)
        dataset_matches_project = bool(project_name and dataset_project == project_name)
        project_loading = _is_loading_state(project_loading_state)
        dataset_loading = _is_loading_state(dataset_loading_state)
        triggered = callback_context.triggered_id
        ready = bool(project_name and dataset and dataset_matches_project)

        if project_loading:
            guide = _home_guide(
                "Loading projects...",
                "Metric View will be available after the project list is ready.",
                loading=True,
            )
            return True, True, True, guide, "stats-home-selection-guide loading"

        if project_name and not ready and dataset_loading:
            guide = _home_guide(
                "Loading datasets...",
                "Please wait while datasets for the selected project are loaded.",
                loading=True,
            )
            return True, True, True, guide, "stats-home-selection-guide loading"

        if project_name and not ready and triggered == "project-name-selector":
            guide = _home_guide(
                "Loading datasets...",
                "Please wait while datasets for the selected project are loaded.",
                loading=True,
            )
            return True, True, True, guide, "stats-home-selection-guide loading"

        if project_name and dataset and not dataset_matches_project:
            guide = _home_guide(
                "Loading datasets...",
                "The dataset selector is updating for the selected project.",
                loading=True,
            )
            return True, True, True, guide, "stats-home-selection-guide loading"

        if ready:
            guide = _home_guide(
                "Dataset ready.",
                "Choose a metric base below to start drilling down into clone sets and code fragments.",
            )
            return False, False, False, guide, "stats-home-selection-guide ready"

        if project_name and not dataset:
            if dataset_disabled and not dataset_options:
                guide = _home_guide(
                    "No datasets available for this project.",
                    "Select another project, or generate visualization datasets first.",
                )
                return True, True, True, guide, "stats-home-selection-guide"
            guide = _home_guide(
                "Select a dataset to continue.",
                "Use the Dataset selector in the top bar, then choose Service Base, Clone Set Base, or File Base.",
            )
        else:
            guide = _home_guide(
                "Select a project and dataset to begin.",
                "Use the Project selector in the top bar first, then select a Dataset.",
            )
        return True, True, True, guide, "stats-home-selection-guide"


# ── サマリ ──────────────────────────────────────────────────────────────


def _register_summary(app: dash.Dash) -> None:
    @app.callback(
        Output("stats-summary-bar", "children"),
        [
            Input("project-name-selector", "value"),
            Input("project-selector", "value"),
        ],
        prevent_initial_call=False,
    )
    def update_summary(project_name, project_value):
        if not project_name:
            return []
        project, _commit, language = _parse_project(project_value)
        if not project or not language:
            return []
        try:
            metrics = load_metrics_dataframes(project, language)
        except Exception as exc:
            logger.error("Error loading metrics summary: %s", exc)
            return _empty_summary("Metrics unavailable")
        return _summary_for_dataset(metrics)


# ── RangeSlider と数値入力の同期 ─────────────────────────────────────────


def _register_range_sliders(
    app: dash.Dash,
    tab: str,
    range_fields: list[tuple],
    df_builder,
) -> None:
    """各レンジ指標に対し,
       (1) project変更時に min/max/value をリセット
       (2) slider <-> input の双方向同期
    の 2 つのコールバックを登録する.
    """
    for label, col, slider_id, min_id, max_id, unit, step in range_fields:

        # (1) project 変更時のリセット
        @app.callback(
            [
                Output(slider_id, "min"),
                Output(slider_id, "max"),
                Output(slider_id, "value"),
                Output(slider_id, "step"),
                Output(min_id, "min"),
                Output(min_id, "max"),
                Output(min_id, "value"),
                Output(max_id, "min"),
                Output(max_id, "max"),
                Output(max_id, "value"),
                Output(_range_value_label_id(slider_id), "children"),
            ],
            Input("project-selector", "value"),
            prevent_initial_call=False,
        )
        def reset_range(
            project_value,
            _col=col,
            _unit=unit,
            _step=step,
            _builder=df_builder,
        ):
            project, _commit, language = _parse_project(project_value)
            if not project or not language:
                value = [0, 1]
                return (
                    0,
                    1,
                    value,
                    _step,
                    0,
                    1,
                    None,
                    0,
                    1,
                    None,
                    _range_value_label(value, _unit, _step),
                )
            try:
                metrics = load_metrics_dataframes(project, language)
            except Exception:
                value = [0, 1]
                return (
                    0,
                    1,
                    value,
                    _step,
                    0,
                    1,
                    None,
                    0,
                    1,
                    None,
                    _range_value_label(value, _unit, _step),
                )
            df = _builder(metrics)
            lo, hi = _column_range(df, _col, _step)
            value = [lo, hi]
            return (
                lo,
                hi,
                value,
                _step,
                lo,
                hi,
                lo,
                lo,
                hi,
                hi,
                _range_value_label(value, _unit, _step),
            )

        # (2) slider <-> input 同期
        @app.callback(
            [
                Output(slider_id, "value", allow_duplicate=True),
                Output(min_id, "value", allow_duplicate=True),
                Output(max_id, "value", allow_duplicate=True),
                Output(
                    _range_value_label_id(slider_id),
                    "children",
                    allow_duplicate=True,
                ),
            ],
            [
                Input(slider_id, "value"),
                Input(min_id, "value"),
                Input(max_id, "value"),
            ],
            [
                State(slider_id, "min"),
                State(slider_id, "max"),
            ],
            prevent_initial_call=True,
        )
        def sync_range(
            sv, mi, ma, lo_bound, hi_bound,
            _slider_id=slider_id,
            _min_id=min_id,
            _max_id=max_id,
            _unit=unit,
            _step=step,
        ):
            triggered = callback_context.triggered_id
            try:
                lo_b = float(lo_bound) if lo_bound is not None else 0.0
                hi_b = float(hi_bound) if hi_bound is not None else 1.0
            except (TypeError, ValueError):
                lo_b, hi_b = 0.0, 1.0
            value, min_out, max_out = _resolve_range_value(
                sv, mi, ma, (lo_b, hi_b), triggered, _slider_id, _min_id, _max_id,
            )
            return value, min_out, max_out, _range_value_label(value, _unit, _step)


# ── MS テーブル ─────────────────────────────────────────────────────────


def _ms_range_inputs() -> list[Input]:
    return [Input(f[2], "value") for f in MS_RANGE_FIELDS]


def _cs_range_inputs() -> list[Input]:
    return [Input(f[2], "value") for f in CS_RANGE_FIELDS]


def _file_range_inputs() -> list[Input]:
    return [Input(f[2], "value") for f in FILE_RANGE_FIELDS]


def _ranges_from_slider_values(fields: list[tuple], values: tuple) -> dict[str, tuple]:
    out: dict[str, tuple] = {}
    for (label, col, *_rest), val in zip(fields, values):
        if isinstance(val, (list, tuple)) and len(val) == 2:
            out[col] = (val[0], val[1])
    return out


def _register_ms_table(app: dash.Dash) -> None:
    @app.callback(
        [
            Output("stats-ms-table", "columns"),
            Output("stats-ms-table", "data"),
            Output("stats-ms-result-count", "children"),
            Output("stats-ms-page-info", "children"),
        ],
        [
            Input("project-selector", "value"),
            Input("stats-ms-name-search", "value"),
            Input("stats-ms-table", "page_current"),
            Input("stats-ms-table", "page_size"),
            *_ms_range_inputs(),
        ],
        prevent_initial_call=False,
    )
    def render_ms_table(project_value, name_query, page_current, page_size, *range_values):
        project, _c, language = _parse_project(project_value)
        if not project or not language:
            return MS_TABLE_COLUMNS, [], "Select a project", "0 rows"
        try:
            metrics = load_metrics_dataframes(project, language)
        except Exception as exc:
            logger.error("Error loading MS metrics: %s", exc)
            return MS_TABLE_COLUMNS, [], "Metrics unavailable", "0 rows"
        total_df = _build_ms_dataframe(metrics)
        if total_df.empty:
            return MS_TABLE_COLUMNS, [], "0 services", "0 rows"
        ranges = _ranges_from_slider_values(MS_RANGE_FIELDS, range_values)
        filtered = _filter_ms_dataframe(total_df, ranges=ranges, name_query=name_query)
        data = _records_for_table(filtered, MS_TABLE_COLUMNS)
        count = f"{len(filtered):,} / {len(total_df):,} services"
        info = _page_info_text(len(filtered), page_current, page_size)
        return MS_TABLE_COLUMNS, data, count, info

    @app.callback(
        Output("stats-ms-table", "page_size"),
        Input("stats-ms-page-size", "value"),
    )
    def update_ms_page_size(size):
        return int(size or DEFAULT_PAGE_SIZE)


# ── CS テーブル ─────────────────────────────────────────────────────────


def _register_cs_table(app: dash.Dash) -> None:
    @app.callback(
        [
            Output("stats-clone-table", "columns"),
            Output("stats-clone-table", "data"),
            Output("stats-clone-table", "tooltip_data"),
            Output("stats-result-count", "children"),
            Output("stats-cs-page-info", "children"),
            Output("stats-file-type-filter", "options"),
            Output("stats-service-filter", "options"),
            Output("stats-filter-store", "data"),
        ],
        [
            Input("project-selector", "value"),
            Input("stats-preset-filter", "value"),
            Input("stats-file-type-filter", "value"),
            Input("stats-service-filter", "value"),
            Input("stats-clone-id-search", "value"),
            Input("stats-clone-table", "page_current"),
            Input("stats-clone-table", "page_size"),
            Input("stats-drilldown-context-store", "data"),
            *_cs_range_inputs(),
        ],
        prevent_initial_call=False,
    )
    def render_cs_table(
        project_value, preset, file_types, services, clone_id_query,
        page_current, page_size, context, *range_values,
    ):
        project, _c, language = _parse_project(project_value)
        filter_state = {
            "preset": preset or "all",
            "file_types": file_types or [],
            "services": services or [],
            "clone_id_query": clone_id_query or "",
            "context": context or _default_context(),
        }
        if not project or not language:
            return CS_TABLE_COLUMNS, [], [], "Select a project", "0 rows", [], [], filter_state
        try:
            metrics = load_metrics_dataframes(project, language)
        except Exception as exc:
            logger.error("Error loading CS metrics: %s", exc)
            return CS_TABLE_COLUMNS, [], [], "Metrics unavailable", "0 rows", [], [], filter_state
        total_df = _build_cs_dataframe(metrics)
        if total_df.empty:
            return CS_TABLE_COLUMNS, [], [], "0 clone sets", "0 rows", [], [], filter_state
        scoped_df = _apply_cs_context(total_df, metrics, context)
        file_type_options = _options_from_tokens(scoped_df, "file_types")
        service_options = _options_from_tokens(scoped_df, "involved_services")
        ranges = _ranges_from_slider_values(CS_RANGE_FIELDS, range_values)
        filtered = _filter_cs_dataframe(
            scoped_df,
            preset=preset,
            ranges=ranges,
            file_types=file_types or [],
            services=services or [],
            clone_id_query=clone_id_query,
        )
        data = _records_for_table(filtered, CS_TABLE_COLUMNS)
        tooltips = _cs_tooltip_data(data)
        display_data = _compact_services_records(data)
        count = f"{len(filtered):,} / {len(scoped_df):,} clone sets"
        if _is_scoped_context(context):
            count = f"{count} in {_context_label(context)}"
        info = _page_info_text(len(filtered), page_current, page_size)
        return (
            CS_TABLE_COLUMNS,
            display_data,
            tooltips,
            count,
            info,
            file_type_options,
            service_options,
            filter_state,
        )

    @app.callback(
        Output("stats-clone-table", "page_size"),
        Input("stats-cs-page-size", "value"),
    )
    def update_cs_page_size(size):
        return int(size or DEFAULT_PAGE_SIZE)

    @app.callback(
        [
            Output("stats-preset-filter", "value"),
            Output("stats-file-type-filter", "value"),
            Output("stats-service-filter", "value"),
            Output("stats-clone-id-search", "value"),
        ],
        [
            Input("project-selector", "value"),
            Input("stats-drilldown-context-store", "data"),
        ],
        prevent_initial_call=True,
    )
    def reset_cs_filters(_project_value, _context):
        return "all", [], [], ""


# ── File テーブル ───────────────────────────────────────────────────────


def _register_file_table(app: dash.Dash) -> None:
    @app.callback(
        [
            Output("stats-file-table", "columns"),
            Output("stats-file-table", "data"),
            Output("stats-file-result-count", "children"),
            Output("stats-file-page-info", "children"),
            Output("stats-file-service-filter", "options"),
        ],
        [
            Input("project-selector", "value"),
            Input("stats-file-type-filter-file", "value"),
            Input("stats-file-service-filter", "value"),
            Input("stats-file-name-search", "value"),
            Input("stats-file-table", "page_current"),
            Input("stats-file-table", "page_size"),
            *_file_range_inputs(),
        ],
        prevent_initial_call=False,
    )
    def render_file_table(
        project_value, file_type, services, name_query,
        page_current, page_size, *range_values,
    ):
        project, _c, language = _parse_project(project_value)
        if not project or not language:
            return FILE_TABLE_COLUMNS, [], "Select a project", "0 rows", []
        try:
            metrics = load_metrics_dataframes(project, language)
        except Exception as exc:
            logger.error("Error loading file metrics: %s", exc)
            return FILE_TABLE_COLUMNS, [], "Metrics unavailable", "0 rows", []
        total_df = _build_file_dataframe(metrics)
        if total_df.empty:
            return FILE_TABLE_COLUMNS, [], "0 files", "0 rows", []
        service_options = _options_from_unique(total_df, "service")
        ranges = _ranges_from_slider_values(FILE_RANGE_FIELDS, range_values)
        filtered = _filter_file_dataframe(
            total_df,
            ranges=ranges,
            file_type=file_type,
            services=services or [],
            name_query=name_query,
        )
        data = _records_for_table(filtered, FILE_TABLE_COLUMNS)
        if "file_path" in filtered.columns:
            file_paths = (
                filtered["file_path"]
                .where(pd.notna(filtered["file_path"]), None)
                .tolist()
            )
            for row, file_path in zip(data, file_paths):
                row["file_path"] = file_path
        count = f"{len(filtered):,} / {len(total_df):,} files"
        info = _page_info_text(len(filtered), page_current, page_size)
        return FILE_TABLE_COLUMNS, data, count, info, service_options

    @app.callback(
        Output("stats-file-table", "page_size"),
        Input("stats-file-page-size", "value"),
    )
    def update_file_page_size(size):
        return int(size or DEFAULT_PAGE_SIZE)

    @app.callback(
        [
            Output("stats-file-type-filter-file", "value"),
            Output("stats-file-service-filter", "value"),
            Output("stats-file-name-search", "value"),
        ],
        Input("project-selector", "value"),
        prevent_initial_call=True,
    )
    def reset_file_filters(_project_value):
        return "all", [], ""


# ── ドリルダウン ──────────────────────────────────────────────────────


def _register_drilldown(app: dash.Dash) -> None:
    @app.callback(
        [
            Output("stats-drilldown-step", "data"),
            Output("stats-selected-clone-store", "data"),
            Output("stats-drilldown-context-store", "data"),
        ],
        [
            Input("stats-clone-table", "active_cell"),
            Input("stats-ms-table", "active_cell"),
            Input("stats-file-table", "active_cell"),
            Input("stats-breadcrumb-back-to-list", "n_clicks"),
            Input("stats-breadcrumb-clone-sets-link", "n_clicks"),
            Input("stats-breadcrumb-base-link", "n_clicks"),
            Input("project-selector", "value"),
            Input("stats-active-tab", "data"),
        ],
        [
            State("stats-clone-table", "data"),
            State("stats-clone-table", "derived_virtual_data"),
            State("stats-ms-table", "data"),
            State("stats-ms-table", "derived_virtual_data"),
            State("stats-file-table", "data"),
            State("stats-file-table", "derived_virtual_data"),
        ],
        prevent_initial_call=True,
    )
    def handle_drilldown(
        clone_active_cell,
        ms_active_cell,
        file_active_cell,
        _bc_clicks,
        _bc_link_clicks,
        _bc_base_clicks,
        _project,
        active_tab,
        clone_table_data,
        clone_virtual_data,
        ms_table_data,
        ms_virtual_data,
        file_table_data,
        file_virtual_data,
    ):
        triggered = callback_context.triggered_id
        if triggered in (
            "stats-breadcrumb-back-to-list",
            "stats-breadcrumb-clone-sets-link",
        ):
            if (
                not callback_context.triggered
                or not callback_context.triggered[0].get("value")
            ):
                return no_update, no_update, no_update
            return "clone_sets", None, no_update
        if triggered == "stats-breadcrumb-base-link":
            if (
                not callback_context.triggered
                or not callback_context.triggered[0].get("value")
            ):
                return no_update, no_update, no_update
            return "base", None, _default_context()
        if triggered in ("project-selector", "stats-active-tab"):
            step = "clone_sets" if active_tab == "cs" else "base"
            return step, None, _default_context()
        if triggered == "stats-ms-table" and ms_active_cell is not None:
            current = ms_virtual_data if ms_virtual_data is not None else ms_table_data
            if not current:
                return no_update, no_update, no_update
            row_idx = ms_active_cell.get("row", 0)
            if row_idx >= len(current):
                return no_update, no_update, no_update
            service = current[row_idx].get("service")
            if service not in (None, ""):
                service_text = str(service)
                return (
                    "clone_sets",
                    None,
                    {
                        "scope_type": "ms",
                        "scope_value": service_text,
                        "scope_label": service_text,
                    },
                )
        if triggered == "stats-file-table" and file_active_cell is not None:
            current = file_virtual_data if file_virtual_data is not None else file_table_data
            if not current:
                return no_update, no_update, no_update
            row_idx = file_active_cell.get("row", 0)
            if row_idx >= len(current):
                return no_update, no_update, no_update
            file_path = current[row_idx].get("file_path")
            if file_path not in (None, ""):
                file_name = current[row_idx].get("file_name") or Path(str(file_path)).name
                return (
                    "clone_sets",
                    None,
                    {
                        "scope_type": "file",
                        "scope_value": str(file_path),
                        "scope_label": str(file_name),
                    },
                )
        if triggered == "stats-clone-table" and clone_active_cell is not None:
            if clone_active_cell.get("column_id") == "involved_services":
                return no_update, no_update, no_update
            current = clone_virtual_data if clone_virtual_data is not None else clone_table_data
            if not current:
                return no_update, no_update, no_update
            row_idx = clone_active_cell.get("row", 0)
            if row_idx >= len(current):
                return no_update, no_update, no_update
            clone_id = current[row_idx].get("clone_id")
            if clone_id not in (None, ""):
                return "fragments", str(clone_id), no_update
        return no_update, no_update, no_update


# ── フラグメント詳細 ────────────────────────────────────────────────────


def _register_fragment_detail(app: dash.Dash) -> None:
    @app.callback(
        [
            Output("stats-detail-summary", "children"),
            Output("stats-frag-table", "data"),
            Output("stats-frag-table", "columns"),
            Output("stats-frag-header", "children"),
            Output("stats-frag-selected-store", "data"),
        ],
        [
            Input("stats-selected-clone-store", "data"),
            Input("project-selector", "value"),
        ],
        prevent_initial_call=False,
    )
    def render_clone_detail(clone_id, project_value):
        project, _commit, language = _parse_project(project_value)
        if not clone_id or not project or not language:
            return _empty_detail_panel(), [], stats_fragment_columns(), "Fragments", []
        try:
            metrics = load_metrics_dataframes(project, language)
        except Exception as exc:
            logger.error("Error loading selected clone detail: %s", exc)
            return _empty_detail_panel(), [], stats_fragment_columns(), "Fragments", []
        frag_data = _fragment_records(str(clone_id), metrics)
        header = f"{len(frag_data)} fragments"
        return _detail_summary(str(clone_id), metrics), frag_data, stats_fragment_columns(), header, []

    @app.callback(
        Output("stats-frag-selected-store", "data", allow_duplicate=True),
        Input("stats-frag-table", "active_cell"),
        State("stats-frag-selected-store", "data"),
        prevent_initial_call=True,
    )
    def update_selected_fragments(active_cell, selected):
        if active_cell is None:
            return no_update
        row_idx = active_cell.get("row", 0)
        current = list(selected) if selected else []
        if row_idx in current:
            current.remove(row_idx)
        else:
            current.append(row_idx)
            if len(current) > 2:
                current.pop(0)
        return current

    @app.callback(
        [
            Output("stats-code-area", "children"),
            Output("stats-frag-table", "style_data_conditional"),
        ],
        Input("stats-frag-selected-store", "data"),
        [
            State("stats-frag-table", "data"),
            State("project-selector", "value"),
        ],
        prevent_initial_call=False,
    )
    def render_fragment_code(selected, frag_data, project_value):
        base_cond = stats_table_data_conditional()
        if not selected or not frag_data:
            return _code_placeholder(), base_cond
        project, _commit, _language = _parse_project(project_value)
        if not project:
            return _code_placeholder(), base_cond
        valid = [idx for idx in selected if isinstance(idx, int) and 0 <= idx < len(frag_data)]
        selected_cond = base_cond + [
            {
                "if": {"row_index": idx},
                "backgroundColor": "#dbeafe",
                "border": "1px solid #2563eb",
            }
            for idx in valid
        ]
        if not valid:
            return _code_placeholder(), selected_cond
        if len(valid) == 1:
            return (
                _build_single_code_pane(frag_data[valid[0]], project, compact=True),
                selected_cond,
            )
        return (
            _build_dual_code_panes(
                frag_data[valid[0]],
                frag_data[valid[1]],
                project,
                compact=True,
            ),
            selected_cond,
        )
