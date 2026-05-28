"""Statistics dashboard callbacks.

project-selector の値変化に応じて KPI と 3 つのビュー
(Language Donut / Clone Sets per Language Bar / Per-Language Table /
Top-N Services h-bar) を更新する.

ROC と Clone LOC は service.total_clone_line_count の合算で重複カウントが
発生するため, MVP では露出しない.
"""

from __future__ import annotations

import logging

import plotly.graph_objects as go
from dash import Input, Output

from ..data_loader.project_stats import (
    LanguageStat,
    ProjectStats,
    ServiceLangStat,
    load_project_stats,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Colors (consistent across charts)
# ---------------------------------------------------------------------------

_LANG_PALETTE = [
    "#2563eb",  # blue
    "#f59e0b",  # amber
    "#10b981",  # emerald
    "#ef4444",  # red
    "#8b5cf6",  # violet
    "#0ea5e9",  # sky
    "#ec4899",  # pink
    "#84cc16",  # lime
]

def _lang_color(idx: int) -> str:
    return _LANG_PALETTE[idx % len(_LANG_PALETTE)]


# ---------------------------------------------------------------------------
# Number formatting
# ---------------------------------------------------------------------------


def _fmt_int(n: int) -> str:
    return f"{n:,}"


# ---------------------------------------------------------------------------
# Figure builders
# ---------------------------------------------------------------------------


def _empty_fig(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"color": "#94a3b8", "size": 13},
            }
        ],
        xaxis={"visible": False},
        yaxis={"visible": False},
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _language_donut(languages: list[LanguageStat]) -> go.Figure:
    rows = [lang for lang in languages if lang.total_loc > 0]
    if not rows:
        return _empty_fig("No language stats available.")
    labels = [lang.language for lang in rows]
    values = [lang.total_loc for lang in rows]
    colors = [_lang_color(i) for i in range(len(rows))]
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker={"colors": colors, "line": {"color": "#ffffff", "width": 1}},
                textinfo="label+percent",
                textfont={"size": 12},
                hovertemplate="<b>%{label}</b><br>LOC: %{value:,}<br>Share: %{percent}<extra></extra>",
                sort=False,
            )
        ]
    )
    total = sum(values)
    fig.update_layout(
        margin={"l": 16, "r": 16, "t": 16, "b": 16},
        showlegend=False,
        annotations=[
            {
                "text": (
                    f"<b>{_fmt_int(total)}</b><br>"
                    "<span style='font-size:11px;color:#64748b'>Total LOC</span>"
                ),
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 16, "color": "#1e293b"},
            }
        ],
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _language_cs_bar(languages: list[LanguageStat]) -> go.Figure:
    """言語ごとの clone set 数を縦棒で表示."""
    rows = [lang for lang in languages]
    if not rows:
        return _empty_fig("No language stats available.")
    langs = [lang.language for lang in rows]
    counts = [lang.n_clone_sets for lang in rows]
    colors = [_lang_color(i) for i in range(len(rows))]
    fig = go.Figure(
        data=[
            go.Bar(
                x=langs,
                y=counts,
                marker_color=colors,
                hovertemplate="<b>%{x}</b><br>Clone Sets: %{y:,}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        margin={"l": 48, "r": 16, "t": 16, "b": 40},
        yaxis={
            "title": {"text": "Clone Sets", "font": {"size": 11}},
            "gridcolor": "#e2e8f0",
            "zerolinecolor": "#e2e8f0",
        },
        xaxis={"title": None},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"size": 11, "color": "#334155"},
        showlegend=False,
    )
    return fig



# ---------------------------------------------------------------------------
# Service × language table helpers
# ---------------------------------------------------------------------------


def _service_lang_store_data(rows: list[ServiceLangStat]) -> list[dict]:
    return [
        {
            "service": r.service,
            "language": r.language,
            "n_files": r.n_files,
            "total_loc": r.total_loc,
            "n_clone_sets": r.n_clone_sets,
        }
        for r in rows
    ]


def _service_lang_options(rows: list[ServiceLangStat]) -> list[dict]:
    langs = sorted({r.language for r in rows})
    return [{"label": "All", "value": "All"}] + [
        {"label": lang, "value": lang} for lang in langs
    ]


# ---------------------------------------------------------------------------
# Per-language table rows
# ---------------------------------------------------------------------------


def _language_table_rows(languages: list[LanguageStat]) -> list[dict]:
    rows: list[dict] = []
    for lang in languages:
        rows.append(
            {
                "language": lang.language,
                "n_services": lang.n_services,
                "n_files": lang.n_files,
                "total_loc": lang.total_loc,
                "n_clone_sets": lang.n_clone_sets,
                "n_clone_pairs": lang.n_clone_pairs,
                "n_comod_clone_sets": lang.n_comod_clone_sets,
                "n_comod_clone_pairs": lang.n_comod_clone_pairs,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------


def register_statistics_callbacks(app, app_data) -> None:  # noqa: ARG001
    """Wire the Statistics dashboard up to project-selector changes."""

    @app.callback(
        Output("statistics-service-table", "data"),
        Input("statistics-service-lang-store", "data"),
        Input("statistics-service-lang-filter", "value"),
    )
    def filter_service_table(rows: list[dict] | None, lang: str | None) -> list[dict]:
        if not rows:
            return []
        if not lang or lang == "All":
            return rows
        return [r for r in rows if r["language"] == lang]

    @app.callback(
        [
            Output("statistics-subtitle", "children"),
            Output("statistics-empty-state", "style"),
            Output("statistics-content", "style"),
            Output("statistics-kpi-services", "children"),
            Output("statistics-kpi-services-sub", "children"),
            Output("statistics-kpi-files", "children"),
            Output("statistics-kpi-files-sub", "children"),
            Output("statistics-kpi-clone_sets", "children"),
            Output("statistics-kpi-clone_sets-sub", "children"),
            Output("statistics-kpi-loc", "children"),
            Output("statistics-kpi-loc-sub", "children"),
            Output("statistics-language-donut", "figure"),
            Output("statistics-language-cs", "figure"),
            Output("statistics-language-table", "data"),
            Output("statistics-service-lang-store", "data"),
            Output("statistics-service-lang-filter", "options"),
        ],
        [
            Input("project-name-selector", "value"),
            Input("project-selector", "value"),
        ],
    )
    def update_statistics(project_name: str | None, project_value: str | None):
        # project-selector の値は "project|||scatter_file:...|||language" の
        # 合成値. 集計には project 部分のみを使う.
        project = _extract_project(project_value)
        if not project:
            return (
                "—",
                {"display": "flex"},
                {"display": "none"},
                *(_kpi_blank_payload()),
                _empty_fig("Select a project."),
                _empty_fig("Select a project."),
                [],
                [],
                [{"label": "All", "value": "All"}],
            )

        try:
            stats = load_project_stats(project)
        except RuntimeError as e:
            logger.exception("load_project_stats failed for %s: %s", project, e)
            raise RuntimeError(f"failed to load stats for {project}") from e

        if stats is None:
            return (
                f"{project_name or project} — no stats available",
                {"display": "flex"},
                {"display": "none"},
                *(_kpi_blank_payload()),
                _empty_fig("No data."),
                _empty_fig("No data."),
                [],
                [],
                [{"label": "All", "value": "All"}],
            )

        subtitle = _build_subtitle(project_name or project, stats)
        lang_options = _service_lang_options(stats.service_lang_rows)
        return (
            subtitle,
            {"display": "none"},
            {"display": "block"},
            *_kpi_payload(stats),
            _language_donut(stats.languages),
            _language_cs_bar(stats.languages),
            _language_table_rows(stats.languages),
            _service_lang_store_data(stats.service_lang_rows),
            lang_options,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_project(project_value: str | None) -> str | None:
    """`project|||scatter_file:...|||language` の先頭セグメントを返す.

    分離子がない素のプロジェクト名でも (将来の互換) そのまま受け付ける.
    """
    if not project_value:
        return None
    head = project_value.split("|||", 1)[0].strip()
    return head or None


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _build_subtitle(project_label: str, stats: ProjectStats) -> str:
    langs = ", ".join(lang.language for lang in stats.languages) or "no languages"
    return f"{project_label}  ·  Languages: {langs}"


def _kpi_blank_payload() -> tuple[str, ...]:
    return tuple(["—", ""] * 4)  # 4 KPI cards × (value, sub)


def _kpi_payload(stats: ProjectStats) -> tuple[str, ...]:
    kpi = stats.kpi
    n_langs = sum(1 for lang in stats.languages if lang.total_loc > 0)
    services_sub = f"{n_langs} language{'s' if n_langs != 1 else ''}"
    files_sub = (
        f"{kpi.n_files / max(kpi.n_services, 1):.1f} per service"
        if kpi.n_services
        else ""
    )
    clone_sets_sub = (
        f"{kpi.n_clone_sets / max(kpi.n_services, 1):.1f} per service"
        if kpi.n_services
        else ""
    )
    loc_sub = (
        f"{kpi.total_loc / max(kpi.n_files, 1):.0f} per file"
        if kpi.n_files
        else ""
    )
    return (
        _fmt_int(kpi.n_services), services_sub,
        _fmt_int(kpi.n_files), files_sub,
        _fmt_int(kpi.n_clone_sets), clone_sets_sub,
        _fmt_int(kpi.total_loc), loc_sub,
    )
