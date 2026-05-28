"""Statistics dashboard layout (MVP).

Design A — KPI strip + language donut + per-language table + Top-N services h-bar.
コールバック (callbacks/statistics_callbacks.py) が project-selector の値に応じて
中身を差し替える. ここではプレースホルダ込みの static layout のみを宣言する.

ROC / Clone LOC は service.total_clone_line_count を sum すると同じ行が複数の
clone set で重複カウントされ実態より高く出てしまうため, MVP では KPI に含めない.
"""

from __future__ import annotations

from dash import dash_table, dcc, html

_SERVICE_TABLE_COLUMNS = [
    {"id": "service", "name": "Service", "type": "text"},
    {"id": "language", "name": "Language", "type": "text"},
    {"id": "n_files", "name": "Files", "type": "numeric"},
    {"id": "total_loc", "name": "LOC", "type": "numeric"},
    {"id": "n_clone_sets", "name": "Clone Sets", "type": "numeric"},
]


def _service_table_card() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Services by Language", className="statistics-card-title"),
                            html.Div(
                                "Per-service file / LOC / clone-set counts. Filter by language.",
                                className="statistics-card-subtitle",
                            ),
                        ]
                    ),
                    dcc.Dropdown(
                        id="statistics-service-lang-filter",
                        options=[{"label": "All", "value": "All"}],
                        value="All",
                        clearable=False,
                        style={"minWidth": "160px", "fontSize": "13px"},
                    ),
                ],
                className="statistics-card-head",
                style={"display": "flex", "alignItems": "flex-start", "justifyContent": "space-between"},
            ),
            dash_table.DataTable(
                id="statistics-service-table",
                columns=_SERVICE_TABLE_COLUMNS,
                data=[],
                sort_action="native",
                sort_mode="single",
                page_size=15,
                style_table={"overflowX": "auto"},
                style_header={
                    "backgroundColor": "#243241",
                    "color": "#f8fafc",
                    "fontWeight": "700",
                    "fontSize": "12px",
                    "border": "none",
                    "textAlign": "left",
                    "padding": "9px 12px",
                },
                style_cell={
                    "fontSize": "12px",
                    "padding": "8px 12px",
                    "borderBottom": "1px solid #e8edf3",
                    "borderTop": "none",
                    "borderLeft": "none",
                    "borderRight": "none",
                    "textAlign": "left",
                    "color": "#233044",
                    "fontFamily": "inherit",
                },
                style_data_conditional=[
                    {"if": {"row_index": "odd"}, "backgroundColor": "#f8fafc"},
                ],
                style_cell_conditional=[
                    {"if": {"column_type": "numeric"}, "textAlign": "right"},
                    {"if": {"column_id": "service"}, "fontWeight": "600"},
                ],
            ),
        ],
        className="statistics-card statistics-card-wide",
    )

# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------

KPI_DEFS: list[tuple[str, str, str]] = [
    # (id_suffix, label, help text)
    ("services", "Services", "Number of microservices detected in the project."),
    ("files", "Files", "Total source files across all languages."),
    ("clone_sets", "Clone Sets", "Total clone sets across all languages."),
    ("loc", "Total LOC", "Total lines of code across all languages."),
]


def _kpi_card(id_suffix: str, label: str, help_text: str) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Span(label, className="statistics-kpi-label"),
                    html.Span("?", className="statistics-kpi-help", title=help_text),
                ],
                className="statistics-kpi-head",
            ),
            html.Div(
                "—",
                id=f"statistics-kpi-{id_suffix}",
                className="statistics-kpi-value",
            ),
            html.Div(
                "",
                id=f"statistics-kpi-{id_suffix}-sub",
                className="statistics-kpi-sub",
            ),
        ],
        className="statistics-kpi-card",
    )


def _kpi_strip() -> html.Div:
    return html.Div(
        [_kpi_card(sid, label, ht) for sid, label, ht in KPI_DEFS],
        className="statistics-kpi-strip",
    )


# ---------------------------------------------------------------------------
# Chart cards
# ---------------------------------------------------------------------------


def _chart_card(
    *,
    title: str,
    subtitle: str,
    graph_id: str,
    extra_class: str = "",
) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(title, className="statistics-card-title"),
                    html.Div(subtitle, className="statistics-card-subtitle"),
                ],
                className="statistics-card-head",
            ),
            dcc.Loading(
                type="dot",
                color="#2563eb",
                children=dcc.Graph(
                    id=graph_id,
                    figure={},
                    config={"displayModeBar": False, "responsive": True},
                    style={"height": "320px"},
                ),
            ),
        ],
        className=f"statistics-card {extra_class}".strip(),
    )


_LANG_TABLE_COLUMNS = [
    {"id": "language", "name": "Language", "type": "text"},
    {"id": "n_services", "name": "Services", "type": "numeric"},
    {"id": "n_files", "name": "Files", "type": "numeric"},
    {"id": "total_loc", "name": "LOC", "type": "numeric"},
    {"id": "n_clone_sets", "name": "Clone Sets", "type": "numeric"},
    {"id": "n_clone_pairs", "name": "Clone Pairs", "type": "numeric"},
    {"id": "n_comod_clone_sets", "name": "Co-mod Sets", "type": "numeric"},
    {"id": "n_comod_clone_pairs", "name": "Co-mod Pairs", "type": "numeric"},
]


def _language_table_card() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Per-Language Breakdown", className="statistics-card-title"),
                    html.Div(
                        "Services, files, LOC, clone sets, and co-modification counts for each language.",
                        className="statistics-card-subtitle",
                    ),
                ],
                className="statistics-card-head",
            ),
            dash_table.DataTable(
                id="statistics-language-table",
                columns=_LANG_TABLE_COLUMNS,
                data=[],
                sort_action="native",
                sort_mode="single",
                style_table={"overflowX": "auto"},
                style_header={
                    "backgroundColor": "#243241",
                    "color": "#f8fafc",
                    "fontWeight": "700",
                    "fontSize": "12px",
                    "border": "none",
                    "textAlign": "left",
                    "padding": "9px 12px",
                },
                style_cell={
                    "fontSize": "12px",
                    "padding": "8px 12px",
                    "borderBottom": "1px solid #e8edf3",
                    "borderTop": "none",
                    "borderLeft": "none",
                    "borderRight": "none",
                    "textAlign": "left",
                    "color": "#233044",
                    "fontFamily": "inherit",
                },
                style_data_conditional=[
                    {"if": {"row_index": "odd"}, "backgroundColor": "#f8fafc"},
                ],
                style_cell_conditional=[
                    {"if": {"column_type": "numeric"}, "textAlign": "right"},
                    {"if": {"column_id": "language"}, "fontWeight": "600"},
                ],
            ),
        ],
        className="statistics-card statistics-card-wide",
    )


def _placeholder_state() -> html.Div:
    return html.Div(
        [
            html.I(className="bi bi-bar-chart-line statistics-empty-icon"),
            html.Div(
                "Select a project to view its statistics.",
                className="statistics-empty-title",
            ),
            html.Div(
                "Choose a project and dataset in the top bar.",
                className="statistics-empty-copy",
            ),
        ],
        id="statistics-empty-state",
        className="statistics-empty-state",
    )


# ---------------------------------------------------------------------------
# Public layout
# ---------------------------------------------------------------------------


def create_statistics_dashboard() -> html.Div:
    """Build the Statistics dashboard layout."""
    return html.Div(
        id="statistics-dashboard",
        className="statistics-dashboard",
        children=[
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                "Project Statistics",
                                className="statistics-title",
                            ),
                            html.Div(
                                id="statistics-subtitle",
                                className="statistics-subtitle",
                                children="—",
                            ),
                        ],
                        className="statistics-header-block",
                    ),
                ],
                className="statistics-header",
            ),
            dcc.Store(id="statistics-service-lang-store"),
            _placeholder_state(),
            html.Div(
                [
                    _kpi_strip(),
                    html.Div(
                        [
                            _chart_card(
                                title="Language Mix",
                                subtitle="Total LOC share by language.",
                                graph_id="statistics-language-donut",
                            ),
                            _chart_card(
                                title="Clone Sets by Language",
                                subtitle="Number of clone sets detected per language.",
                                graph_id="statistics-language-cs",
                            ),
                            _language_table_card(),
                            _service_table_card(),
                        ],
                        className="statistics-chart-grid",
                    ),
                ],
                id="statistics-content",
                className="statistics-content",
                style={"display": "none"},
            ),
        ],
    )
