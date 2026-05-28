"""Metric View clone metrics explorer layout — 3-tab edition.

タブ構成:
  Service Base   — マイクロサービスメトリクス一覧
  Clone Set Base — クローンセット一覧 (ドリルダウンで fragments/コード表示)
  File Base      — ファイルメトリクス一覧

各タブは固有のフィルタサイドバー + RangeSlider + テーブルを持つ.
Service/File タブは関連 Clone Sets 一覧を経由して fragments/code へドリルダウンする.
"""

from __future__ import annotations

from dash import dash_table, dcc, html

# ---------------------------------------------------------------------------
# テーブル共通スタイル
# ---------------------------------------------------------------------------

_TABLE_STYLE_HEADER = {
    "backgroundColor": "#243241",
    "color": "#f8fafc",
    "fontWeight": "700",
    "fontSize": "12px",
    "border": "none",
    "textAlign": "left",
    "padding": "9px 12px",
}

_TABLE_STYLE_CELL = {
    "fontSize": "12px",
    "padding": "8px 12px",
    "borderBottom": "1px solid #e8edf3",
    "borderTop": "none",
    "borderLeft": "none",
    "borderRight": "none",
    "textAlign": "left",
    "whiteSpace": "nowrap",
    "overflow": "hidden",
    "textOverflow": "ellipsis",
    "color": "#233044",
    "minWidth": "64px",
}

_TABLE_STYLE_DATA_CONDITIONAL = [
    {"if": {"row_index": "odd"}, "backgroundColor": "#f8fafc"},
    {
        "if": {"state": "active"},
        "backgroundColor": "#dbeafe",
        "border": "1px solid #60a5fa",
    },
    {
        "if": {"state": "selected"},
        "backgroundColor": "#dbeafe",
        "border": "1px solid #60a5fa",
    },
]

_FRAG_COLUMNS = [
    {"id": "fragment_index", "name": "#", "type": "numeric"},
    {"id": "service", "name": "Service", "type": "text"},
    {"id": "file_short", "name": "File", "type": "text"},
    {"id": "lines", "name": "Lines", "type": "text"},
    {"id": "line_count", "name": "LOC", "type": "numeric"},
    {"id": "file_type", "name": "Category", "type": "text"},
    {"id": "mod_count", "name": "Mod", "type": "numeric"},
    {"id": "mod_commits", "name": "Commits", "type": "text"},
]

# ---------------------------------------------------------------------------
# フィルタのヘルプ文 (column_id / filter key → 日本語説明)
# ---------------------------------------------------------------------------

FILTER_HELP: dict[str, str] = {
    # MS tab
    "clone_set_count": "Show microservices with this many clone sets.",
    "inter_clone_set_count": "Show microservices with this many clone sets shared with other services.",
    "total_clone_line_count": "Show microservices with this total amount of cloned lines of code.",
    "roc_pct": "Show microservices by clone density: cloned LOC divided by total LOC.",
    "clone_avg_line_count": "Show microservices by the average size of their clone fragments.",
    "clone_file_count": "Show microservices by how many files contain cloned code.",
    "comod_count": "Show items by how often clone fragments changed together in the same commit.",
    "comod_other_service_count": "Show microservices by how many other services are linked through co-modification.",
    # Clone Set tab
    "service_count": "Show clone sets that involve this many services.",
    "cross_service_line_count": "Show clone sets by the amount of cross-service cloned LOC.",
    "inter_frag_ratio_pct": "Show clone sets by the percentage of fragments involved in cross-service cloning.",
    "comod_frag_ratio_pct": "Show clone sets by the percentage of fragments that were co-modified.",
    "n_total_fragments": "Show clone sets by the number of code fragments they contain.",
    "cross_service_fragment_count": "Show clone sets by how many fragments cross service boundaries.",
    "cross_service_scale": "Show clone sets by a combined cross-service scale score.",
    # File tab
    "sharing_service_count": "Show files by how many services share clones with them.",
    "sharing_service_ratio_pct": "Show files by the percentage of services that share clones with them.",
    "cross_service_clone_set_count": "Show files by how many clone sets cross service boundaries.",
    "cross_cs_ratio_pct": "Show files by the percentage of their clone sets that are cross-service.",
    "cross_service_comod_count": "Show files by how often cross-service clones changed together.",
    # Text / dropdown filters
    "stats-ms-name-search": "Search microservices by name.",
    "stats-preset-filter": "Apply a common clone-set filter preset on top of the other filters.",
    "stats-file-type-filter": "Show clone sets that include at least one selected file category.",
    "stats-service-filter": "Show clone sets that include at least one selected service.",
    "stats-clone-id-search": "Search clone sets by Clone ID.",
    "stats-file-type-filter-file": "Show only files with the selected file category.",
    "stats-file-service-filter": "Show only files that belong to the selected services.",
    "stats-file-name-search": "Search files by name.",
}

TABLE_COLUMN_HELP: dict[str, str] = {
    "service": "Microservice name.",
    "clone_id": "Clone set identifier. Click a row to inspect its fragments.",
    "clone_set_count": "Total clone sets that include this microservice.",
    "inter_clone_set_count": "Inter-service clone sets: clone sets this microservice shares with at least one other service.",
    "total_clone_line_count": "Total cloned lines of code.",
    "roc_pct": "ROC (Ratio of Cloned LOC). Clone density = cloned LOC / total LOC of the service.",
    "clone_avg_line_count": "Average LOC per clone fragment.",
    "clone_file_count": "Number of files that contain cloned code.",
    "comod_count": "Comod (Co-modification): number of commits where two or more clone fragments changed together.",
    "comod_other_service_count": "Number of other services linked to this service through co-modification.",
    "service_count": "Number of services involved in this clone set.",
    "file_types": "File categories included in this clone set.",
    "involved_services": "Services involved in this clone set.",
    "cross_service_line_count": "Inter LOC (cross-service): LOC from fragments that cross service boundaries.",
    "inter_frag_ratio_pct": "Inter % (cross-service): percentage of fragments involved in cross-service cloning.",
    "comod_frag_ratio_pct": "Comod Frag %: percentage of fragments that were co-modified.",
    "n_total_fragments": "Total number of fragments in this clone set.",
    "cross_service_fragment_count": "Inter Frags: number of fragments that cross service boundaries.",
    "cross_service_scale": "Combined score for cross-service clone size and spread (higher = larger & more dispersed).",
    "file_name": "File name.",
    "file_type": "Detected file category (Logic / Test / Data / Config).",
    "sharing_service_count": "Number of services sharing clones with this file.",
    "sharing_service_ratio_pct": "Percentage of services sharing clones with this file.",
    "total_service_count": "Total number of services in the project.",
    "cross_service_clone_set_count": "Inter CS (cross-service clone sets) involving this file.",
    "cross_cs_ratio_pct": "Inter CS %: percentage of this file's clone sets that are cross-service.",
    "cross_service_comod_count": "Inter Comod: number of co-modifications involving fragments that cross service boundaries.",
    "comod_shared_service_count": "Number of services linked to this file through co-modification.",
    # Fragment table
    "fragment_index": "Position of this fragment within the clone set (1-based).",
    "file_short": "File name where this fragment is located. Click to view the source code.",
    "lines": "Line range of this fragment in the source file (start-end).",
    "line_count": "Number of lines of code in this fragment.",
    "mod_count": "Number of commits that modified this fragment.",
    "mod_commits": "Short hashes of commits that modified this fragment.",
}


def _help_icon(help_text: str | None) -> html.Span | None:
    if not help_text:
        return None
    return html.Span(
        "?",
        className="stats-help-icon",
        title=help_text,
    )

# ---------------------------------------------------------------------------
# RangeSlider + 数値入力のハイブリッド
# ---------------------------------------------------------------------------

PAGE_SIZE_OPTIONS = [25, 50, 100, 200]
DEFAULT_PAGE_SIZE = 50


def _range_value_label_id(slider_id: str) -> str:
    return f"{slider_id}-current-value"


def _range_filter(
    label: str,
    slider_id: str,
    min_input_id: str,
    max_input_id: str,
    unit: str = "",
    step: float | int = 1,
    help_text: str | None = None,
) -> html.Div:
    """RangeSlider 1 本 + min/max 数値入力 2 本のハイブリッド UI.

    実値は slider の value がソース. min/max input は表示と直接入力を担う
    (callback で双方向に同期する).
    """
    # ラベルが既に単位 (例: "Inter %") を含む場合は "(%)" を二重に付けない
    label_has_unit = bool(unit) and label.rstrip().endswith(unit)
    unit_label = f" ({unit})" if unit and not label_has_unit else ""
    label_children: list = [html.Span(f"{label}{unit_label}")]
    icon = _help_icon(help_text)
    if icon is not None:
        label_children.append(icon)
    return html.Div(
        [
            html.Label(label_children, className="stats-filter-label"),
            html.Div(
                dcc.RangeSlider(
                    id=slider_id,
                    min=0,
                    max=1,
                    value=[0, 1],
                    step=step,
                    marks=None,
                    tooltip={"always_visible": False, "placement": "bottom"},
                    allowCross=False,
                    pushable=False,
                    updatemode="mouseup",
                ),
                className="stats-range-slider-wrap",
            ),
            html.Div(
                "0 - 1",
                id=_range_value_label_id(slider_id),
                className="stats-range-current-value",
            ),
            html.Div(
                [
                    dcc.Input(
                        id=min_input_id,
                        type="number",
                        debounce=True,
                        className="stats-range-input",
                    ),
                    dcc.Input(
                        id=max_input_id,
                        type="number",
                        debounce=True,
                        className="stats-range-input",
                    ),
                ],
                className="stats-range-row",
                style={"display": "none"},
            ),
        ],
        className="stats-filter-field",
    )


# ---------------------------------------------------------------------------
# 各タブのフィルタ定義
# ---------------------------------------------------------------------------

# (label, column_id, slider_id, min_input_id, max_input_id, unit, step)
MS_RANGE_FIELDS: list[tuple[str, str, str, str, str, str, float | int]] = [
    ("# CS", "clone_set_count", "stats-ms-cs-count-slider", "stats-ms-cs-count-min", "stats-ms-cs-count-max", "", 1),
    ("# Inter CS", "inter_clone_set_count", "stats-ms-inter-cs-slider", "stats-ms-inter-cs-min", "stats-ms-inter-cs-max", "", 1),
    ("Clone LOC", "total_clone_line_count", "stats-ms-loc-slider", "stats-ms-loc-min", "stats-ms-loc-max", "", 1),
    ("ROC", "roc_pct", "stats-ms-roc-slider", "stats-ms-roc-min", "stats-ms-roc-max", "%", 0.1),
    ("Avg LOC", "clone_avg_line_count", "stats-ms-avg-loc-slider", "stats-ms-avg-loc-min", "stats-ms-avg-loc-max", "", 0.1),
    ("Files", "clone_file_count", "stats-ms-file-count-slider", "stats-ms-file-count-min", "stats-ms-file-count-max", "", 1),
    ("Comod", "comod_count", "stats-ms-comod-slider", "stats-ms-comod-min", "stats-ms-comod-max", "", 1),
    ("Related Services", "comod_other_service_count", "stats-ms-related-slider", "stats-ms-related-min", "stats-ms-related-max", "", 1),
]

CS_RANGE_FIELDS: list[tuple[str, str, str, str, str, str, float | int]] = [
    ("Service Span", "service_count", "stats-cs-svc-count-slider", "stats-cs-svc-count-min", "stats-cs-svc-count-max", "", 1),
    ("Inter LOC", "cross_service_line_count", "stats-cs-inter-loc-slider", "stats-cs-inter-loc-min", "stats-cs-inter-loc-max", "", 1),
    ("Inter %", "inter_frag_ratio_pct", "stats-cs-inter-ratio-slider", "stats-cs-inter-ratio-min", "stats-cs-inter-ratio-max", "%", 0.1),
    ("Comod", "comod_count", "stats-cs-comod-slider", "stats-cs-comod-min", "stats-cs-comod-max", "", 1),
    ("Comod Frag %", "comod_frag_ratio_pct", "stats-cs-comod-ratio-slider", "stats-cs-comod-ratio-min", "stats-cs-comod-ratio-max", "%", 0.1),
    ("Frags", "n_total_fragments", "stats-cs-frag-count-slider", "stats-cs-frag-count-min", "stats-cs-frag-count-max", "", 1),
    ("Inter Frags", "cross_service_fragment_count", "stats-cs-inter-frag-slider", "stats-cs-inter-frag-min", "stats-cs-inter-frag-max", "", 1),
    ("Inter Scale", "cross_service_scale", "stats-cs-inter-scale-slider", "stats-cs-inter-scale-min", "stats-cs-inter-scale-max", "", 0.1),
]

FILE_RANGE_FIELDS: list[tuple[str, str, str, str, str, str, float | int]] = [
    ("Shared Services", "sharing_service_count", "stats-file-share-ms-slider", "stats-file-share-ms-min", "stats-file-share-ms-max", "", 1),
    ("Shared %", "sharing_service_ratio_pct", "stats-file-share-ratio-slider", "stats-file-share-ratio-min", "stats-file-share-ratio-max", "%", 0.1),
    ("# Inter CS", "cross_service_clone_set_count", "stats-file-inter-cs-slider", "stats-file-inter-cs-min", "stats-file-inter-cs-max", "", 1),
    ("Inter CS %", "cross_cs_ratio_pct", "stats-file-inter-cs-ratio-slider", "stats-file-inter-cs-ratio-min", "stats-file-inter-cs-ratio-max", "%", 0.1),
    ("Inter LOC", "cross_service_line_count", "stats-file-inter-loc-slider", "stats-file-inter-loc-min", "stats-file-inter-loc-max", "", 1),
    ("Inter Comod", "cross_service_comod_count", "stats-file-inter-comod-slider", "stats-file-inter-comod-min", "stats-file-inter-comod-max", "", 1),
]

# ---------------------------------------------------------------------------
# テーブルカラム定義
# ---------------------------------------------------------------------------

MS_TABLE_COLUMNS = [
    {"id": "service", "name": "Service", "type": "text"},
    {"id": "clone_set_count", "name": "# CS", "type": "numeric"},
    {"id": "inter_clone_set_count", "name": "# Inter CS", "type": "numeric"},
    {"id": "total_clone_line_count", "name": "Clone LOC", "type": "numeric"},
    {"id": "roc_pct", "name": "ROC (%)", "type": "numeric"},
    {"id": "clone_avg_line_count", "name": "Avg LOC", "type": "numeric"},
    {"id": "clone_file_count", "name": "Files", "type": "numeric"},
    {"id": "comod_count", "name": "Comod", "type": "numeric"},
    {"id": "comod_other_service_count", "name": "Related Services", "type": "numeric"},
]

CS_TABLE_COLUMNS = [
    {"id": "clone_id", "name": "Clone ID", "type": "text"},
    {"id": "service_count", "name": "Service Span", "type": "numeric"},
    {"id": "file_types", "name": "Category", "type": "text"},
    {
        "id": "involved_services",
        "name": "Services",
        "type": "text",
        "presentation": "markdown",
    },
    {"id": "comod_count", "name": "Comod", "type": "numeric"},
    {"id": "cross_service_line_count", "name": "Inter LOC", "type": "numeric"},
    {"id": "inter_frag_ratio_pct", "name": "Inter %", "type": "numeric"},
    {"id": "comod_frag_ratio_pct", "name": "Comod Frag %", "type": "numeric"},
    {"id": "n_total_fragments", "name": "Frags", "type": "numeric"},
    {"id": "cross_service_fragment_count", "name": "Inter Frags", "type": "numeric"},
    {"id": "cross_service_scale", "name": "Inter Scale", "type": "numeric"},
]

FILE_TABLE_COLUMNS = [
    {"id": "file_name", "name": "File", "type": "text"},
    {"id": "service", "name": "Service", "type": "text"},
    {"id": "file_type", "name": "Category", "type": "text"},
    {"id": "sharing_service_count", "name": "Shared Services", "type": "numeric"},
    {"id": "sharing_service_ratio_pct", "name": "Shared %", "type": "numeric"},
    {"id": "total_service_count", "name": "Total Services", "type": "numeric"},
    {"id": "cross_service_clone_set_count", "name": "# Inter CS", "type": "numeric"},
    {"id": "cross_cs_ratio_pct", "name": "Inter CS %", "type": "numeric"},
    {"id": "cross_service_line_count", "name": "Inter LOC", "type": "numeric"},
    {"id": "cross_service_comod_count", "name": "Inter Comod", "type": "numeric"},
    {"id": "comod_shared_service_count", "name": "Comod Services", "type": "numeric"},
]


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------


def _empty_detail() -> html.Div:
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


def _page_size_control(prefix: str) -> html.Div:
    """ページサイズドロップダウン + ページ情報の表示エリア."""
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Rows per page:", className="stats-page-size-label"),
                    dcc.Dropdown(
                        id=f"{prefix}-page-size",
                        options=[{"label": str(n), "value": n} for n in PAGE_SIZE_OPTIONS],
                        value=DEFAULT_PAGE_SIZE,
                        clearable=False,
                        searchable=False,
                        className="stats-page-size-dropdown",
                    ),
                ],
                className="stats-page-size-wrap",
            ),
            html.Div(
                id=f"{prefix}-page-info",
                className="stats-page-info",
            ),
        ],
        className="stats-page-controls",
    )


def _make_table(table_id: str, columns: list[dict]) -> dash_table.DataTable:
    return dash_table.DataTable(
        id=table_id,
        columns=columns,
        data=[],
        page_size=DEFAULT_PAGE_SIZE,
        page_action="native",
        sort_action="native",
        sort_mode="multi",
        row_selectable=False,
        style_table={"overflowX": "auto"},
        style_header=_TABLE_STYLE_HEADER,
        style_cell=_TABLE_STYLE_CELL,
        style_data_conditional=_TABLE_STYLE_DATA_CONDITIONAL,
        style_cell_conditional=[
            {"if": {"column_type": "numeric"}, "textAlign": "right"},
            {"if": {"column_id": "clone_id"}, "fontWeight": "700", "cursor": "pointer"},
            {"if": {"column_id": "service"}, "fontWeight": "600"},
            {"if": {"column_id": "file_types"}, "maxWidth": "140px", "whiteSpace": "normal", "lineHeight": "1.35"},
            {"if": {"column_id": "involved_services"}, "maxWidth": "200px", "whiteSpace": "normal", "lineHeight": "1.35"},
        ],
        tooltip_header={
            col["id"]: {"value": TABLE_COLUMN_HELP[col["id"]], "type": "text"}
            for col in columns
            if col["id"] in TABLE_COLUMN_HELP
        },
        tooltip_delay=0,
        tooltip_duration=None,
        markdown_options={"html": True},
    )


def _filter_sidebar(
    *,
    sidebar_id: str,
    range_fields: list[tuple],
    extra_children: list,
) -> html.Aside:
    return html.Aside(
        [
            html.Div("Filters", className="stats-panel-heading"),
            *[
                _range_filter(label, sid, mi, ma, unit, step, help_text=FILTER_HELP.get(col))
                for (label, col, sid, mi, ma, unit, step) in range_fields
            ],
            *extra_children,
        ],
        id=sidebar_id,
        className="stats-filter-panel",
    )


def _labeled_field(label: str, control, help_key: str | None = None) -> html.Div:
    """Generic label + (optional ? icon) + form control wrapper."""
    label_children: list = [html.Span(label)]
    icon = _help_icon(FILTER_HELP.get(help_key)) if help_key else None
    if icon is not None:
        label_children.append(icon)
    return html.Div(
        [
            html.Label(label_children, className="stats-filter-label"),
            control,
        ],
        className="stats-filter-field",
    )


def _ms_filter_sidebar() -> html.Aside:
    return _filter_sidebar(
        sidebar_id="stats-ms-filter-panel",
        range_fields=MS_RANGE_FIELDS,
        extra_children=[
            _labeled_field(
                "Service name",
                dcc.Input(
                    id="stats-ms-name-search",
                    type="text",
                    debounce=True,
                    placeholder="Search service",
                    className="stats-text-input",
                ),
                help_key="stats-ms-name-search",
            ),
        ],
    )


def _cs_filter_sidebar() -> html.Aside:
    return _filter_sidebar(
        sidebar_id="stats-cs-filter-panel",
        range_fields=CS_RANGE_FIELDS,
        extra_children=[
            _labeled_field(
                "Preset",
                dcc.Dropdown(
                    id="stats-preset-filter",
                    options=[
                        {"label": "All clone sets", "value": "all"},
                        {"label": "Cross-service 2+", "value": "cross2"},
                        {"label": "Co-modified 1+", "value": "comod1"},
                        {"label": "Top 25% Inter LOC", "value": "top_inter_loc"},
                    ],
                    value="all",
                    clearable=False,
                    searchable=False,
                    className="stats-dropdown",
                ),
                help_key="stats-preset-filter",
            ),
            _labeled_field(
                "File Category",
                dcc.Dropdown(
                    id="stats-file-type-filter",
                    options=[],
                    value=[],
                    multi=True,
                    placeholder="Any category",
                    className="stats-dropdown",
                ),
                help_key="stats-file-type-filter",
            ),
            _labeled_field(
                "Involved service",
                dcc.Dropdown(
                    id="stats-service-filter",
                    options=[],
                    value=[],
                    multi=True,
                    placeholder="Any service",
                    className="stats-dropdown",
                ),
                help_key="stats-service-filter",
            ),
            _labeled_field(
                "Clone ID",
                dcc.Input(
                    id="stats-clone-id-search",
                    type="text",
                    debounce=True,
                    placeholder="Search ID",
                    className="stats-text-input",
                ),
                help_key="stats-clone-id-search",
            ),
        ],
    )


def _file_filter_sidebar() -> html.Aside:
    return _filter_sidebar(
        sidebar_id="stats-file-filter-panel",
        range_fields=FILE_RANGE_FIELDS,
        extra_children=[
            _labeled_field(
                "File Category",
                dcc.Dropdown(
                    id="stats-file-type-filter-file",
                    options=[
                        {"label": "All", "value": "all"},
                        {"label": "Logic", "value": "logic"},
                        {"label": "Test", "value": "test"},
                        {"label": "Data", "value": "data"},
                        {"label": "Config", "value": "config"},
                    ],
                    value="all",
                    clearable=False,
                    className="stats-dropdown",
                ),
                help_key="stats-file-type-filter-file",
            ),
            _labeled_field(
                "Service",
                dcc.Dropdown(
                    id="stats-file-service-filter",
                    options=[],
                    value=[],
                    multi=True,
                    placeholder="Any service",
                    className="stats-dropdown",
                ),
                help_key="stats-file-service-filter",
            ),
            _labeled_field(
                "File name",
                dcc.Input(
                    id="stats-file-name-search",
                    type="text",
                    debounce=True,
                    placeholder="Search file",
                    className="stats-text-input",
                ),
                help_key="stats-file-name-search",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Tabs & breadcrumb
# ---------------------------------------------------------------------------


def _view_selector() -> html.Div:
    return html.Div(
        [
            html.Button(
                [
                    html.Span("Service Base", className="stats-home-card-title"),
                    html.Span(
                        "Start from a microservice, then inspect the clone sets and code fragments connected to it.",
                        className="stats-home-card-copy",
                    ),
                ],
                id="stats-tab-ms",
                className="stats-home-card",
                n_clicks=0,
            ),
            html.Button(
                [
                    html.Span("Clone Set Base", className="stats-home-card-title"),
                    html.Span(
                        "Browse clone sets directly, then drill down into their fragments and source snippets.",
                        className="stats-home-card-copy",
                    ),
                ],
                id="stats-tab-cs",
                className="stats-home-card",
                n_clicks=0,
            ),
            html.Button(
                [
                    html.Span("File Base", className="stats-home-card-title"),
                    html.Span(
                        "Start from a file, then inspect the clone sets where that file appears.",
                        className="stats-home-card-copy",
                    ),
                ],
                id="stats-tab-file",
                className="stats-home-card",
                n_clicks=0,
            ),
        ],
        className="stats-home-card-grid",
    )


def _home_step() -> html.Div:
    return html.Div(
        id="stats-home-step",
        className="stats-home-step",
        children=[
            html.Div(
                id="stats-home-selection-guide",
                className="stats-home-selection-guide",
                children=[
                    html.Div("Select a project and dataset to begin.", className="stats-home-guide-title"),
                    html.Div(
                        "Use the Project and Dataset selectors in the top bar before choosing a metric base.",
                        className="stats-home-guide-copy",
                    ),
                ],
            ),
            html.Div(id="stats-summary-bar", className="stats-summary-bar"),
            _view_selector(),
        ],
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


def _breadcrumb() -> html.Div:
    return html.Nav(
        id="stats-breadcrumb",
        className="stats-breadcrumb",
        children=[
            html.Button(
                "Clone Sets",
                id="stats-breadcrumb-back-to-list",
                className="stats-breadcrumb-link",
                n_clicks=0,
                style={"display": "none"},
            ),
            html.Ol(
                id="stats-breadcrumb-list",
                className="stats-breadcrumb-list",
                children=[
                    _hidden_breadcrumb_home_link(),
                    _hidden_breadcrumb_base_link(),
                    html.Li(
                        html.Button(
                            "Clone Sets",
                            id="stats-breadcrumb-clone-sets-link",
                            className="stats-breadcrumb-link",
                            n_clicks=0,
                        ),
                        className="stats-breadcrumb-item",
                        style={"display": "none"},
                    ),
                    html.Li(
                        html.Span("Clone Sets", className="stats-breadcrumb-current"),
                        className="stats-breadcrumb-item active",
                    ),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Step 1: 各タブの内容
# ---------------------------------------------------------------------------


def _step1_ms() -> html.Div:
    return html.Div(
        id="stats-step-ms",
        className="stats-step stats-step-table",
        style={"display": "none"},
        children=[
            _ms_filter_sidebar(),
            html.Main(
                [
                    html.Div(
                        [
                            html.Div("Services", className="stats-panel-heading"),
                            html.Div(id="stats-ms-result-count", className="stats-result-count"),
                        ],
                        className="stats-results-heading",
                    ),
                    html.Div(
                        dcc.Loading(
                            type="dot",
                            color="#2563eb",
                            children=_make_table("stats-ms-table", MS_TABLE_COLUMNS),
                        ),
                        className="stats-table-scroll",
                    ),
                    _page_size_control("stats-ms"),
                ],
                className="stats-results-panel",
            ),
        ],
    )


def _step1_cs() -> html.Div:
    return html.Div(
        id="stats-step-cs",
        className="stats-step stats-step-table",
        style={"display": "none"},
        children=[
            _cs_filter_sidebar(),
            html.Main(
                [
                    html.Div(
                        [
                            html.Div("Clone Sets", className="stats-panel-heading"),
                            html.Div(id="stats-result-count", className="stats-result-count"),
                        ],
                        className="stats-results-heading",
                    ),
                    html.Div(
                        dcc.Loading(
                            type="dot",
                            color="#2563eb",
                            children=_make_table("stats-clone-table", CS_TABLE_COLUMNS),
                        ),
                        className="stats-table-scroll",
                    ),
                    _page_size_control("stats-cs"),
                ],
                className="stats-results-panel",
            ),
        ],
    )


def _step1_file() -> html.Div:
    return html.Div(
        id="stats-step-file",
        className="stats-step stats-step-table",
        style={"display": "none"},
        children=[
            _file_filter_sidebar(),
            html.Main(
                [
                    html.Div(
                        [
                            html.Div("Files", className="stats-panel-heading"),
                            html.Div(id="stats-file-result-count", className="stats-result-count"),
                        ],
                        className="stats-results-heading",
                    ),
                    html.Div(
                        dcc.Loading(
                            type="dot",
                            color="#2563eb",
                            children=_make_table("stats-file-table", FILE_TABLE_COLUMNS),
                        ),
                        className="stats-table-scroll",
                    ),
                    _page_size_control("stats-file"),
                ],
                className="stats-results-panel",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Step 2: フラグメント + コード (CS のみ)
# ---------------------------------------------------------------------------


def _step2_fragments() -> html.Div:
    return html.Div(
        id="stats-step-fragments",
        className="stats-step stats-step-fragments",
        style={"display": "none"},
        children=[
            html.Div(id="stats-detail-summary", children=_empty_detail()),
            html.Div(
                [
                    html.Div(id="stats-frag-header", className="stats-frag-header"),
                    dash_table.DataTable(
                        id="stats-frag-table",
                        columns=_FRAG_COLUMNS,
                        data=[],
                        page_action="none",
                        sort_action="native",
                        style_table={"overflowX": "auto"},
                        style_header=_TABLE_STYLE_HEADER,
                        style_cell={**_TABLE_STYLE_CELL, "fontSize": "12px", "padding": "8px 12px"},
                        style_data_conditional=_TABLE_STYLE_DATA_CONDITIONAL,
                        style_cell_conditional=[
                            {"if": {"column_id": "fragment_index"}, "textAlign": "right", "maxWidth": "42px"},
                            {"if": {"column_id": "line_count"}, "textAlign": "right"},
                            {"if": {"column_id": "mod_count"}, "textAlign": "right", "maxWidth": "48px"},
                            {"if": {"column_id": "mod_commits"}, "fontFamily": "monospace", "fontSize": "11px", "maxWidth": "220px", "whiteSpace": "normal"},
                            {"if": {"column_id": "file_short"}, "cursor": "pointer", "fontWeight": "600"},
                        ],
                        tooltip_header={
                            col["id"]: {"value": TABLE_COLUMN_HELP[col["id"]], "type": "text"}
                            for col in _FRAG_COLUMNS
                            if col["id"] in TABLE_COLUMN_HELP
                        },
                        tooltip_delay=0,
                        tooltip_duration=None,
                    ),
                ],
                className="stats-frag-panel",
            ),
            html.Div(
                html.Div(
                    "Select one or two fragments to view code.",
                    className="stats-code-placeholder",
                ),
                id="stats-code-area",
                className="stats-code-area",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Public layout builder
# ---------------------------------------------------------------------------


def create_stats_metrics_explorer() -> html.Div:
    """Build the interactive clone metrics explorer for the Statistics view."""
    return html.Div(
        id="stats-metrics-explorer",
        className="stats-explorer",
        children=[
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Select a Metric Base", className="stats-title"),
                            html.Div(
                                "Choose where to start your drilldown through clone metrics.",
                                className="stats-subtitle",
                            ),
                        ],
                        className="stats-title-block",
                    ),
                ],
                id="stats-explorer-header",
                className="stats-explorer-header",
            ),
            _home_step(),
            _breadcrumb(),
            html.Div(
                [
                    _step1_ms(),
                    _step1_cs(),
                    _step1_file(),
                    _step2_fragments(),
                ],
                className="stats-explorer-body",
            ),
            dcc.Store(id="stats-active-tab", data="home"),
            dcc.Store(id="stats-selected-clone-store"),
            dcc.Store(id="stats-frag-selected-store", data=[]),
            dcc.Store(id="stats-filter-store", data={}),
            dcc.Store(
                id="stats-drilldown-context-store",
                data={"scope_type": "all", "scope_value": None, "scope_label": ""},
            ),
            dcc.Store(id="stats-drilldown-step", data="clone_sets"),
        ],
    )


# ---------------------------------------------------------------------------
# Helpers re-exported for callbacks
# ---------------------------------------------------------------------------


def stats_fragment_columns() -> list[dict]:
    return list(_FRAG_COLUMNS)


def stats_table_data_conditional() -> list[dict]:
    return list(_TABLE_STYLE_DATA_CONDITIONAL)
