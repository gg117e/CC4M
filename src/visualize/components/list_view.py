"""ドリルダウン方式クローンメトリクスリストビュー — レイアウトコンポーネント.

3 つの起点タブ (MSベース / ファイルベース / CSベース) から
階層的に詳細を掘り下げる DataTable ベースのビューを提供する.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

FILE_TYPE_OPTIONS = [
    {"label": "All", "value": "all"},
    {"label": "Logic", "value": "logic"},
    {"label": "Test", "value": "test"},
    {"label": "Data", "value": "data"},
    {"label": "Config", "value": "config"},
]

# DataTable 共通スタイル
_TABLE_STYLE_HEADER = {
    "backgroundColor": "#1f2937",
    "color": "#f9fafb",
    "fontWeight": "600",
    "fontSize": "12px",
    "borderBottom": "1px solid #e5e7eb",
    "borderTop": "none",
    "borderLeft": "none",
    "borderRight": "none",
    "textAlign": "left",
    "whiteSpace": "nowrap",
    "padding": "10px 14px",
}
_TABLE_STYLE_CELL = {
    "fontSize": "13px",
    "padding": "10px 14px",
    "borderBottom": "1px solid #f3f4f6",
    "borderTop": "none",
    "borderLeft": "none",
    "borderRight": "none",
    "textAlign": "left",
    "whiteSpace": "nowrap",
    "overflow": "hidden",
    "textOverflow": "ellipsis",
    "minWidth": "70px",
    "color": "#374151"
}
_TABLE_STYLE_DATA_CONDITIONAL = [
    {
        "if": {"row_index": "odd"},
        "backgroundColor": "#f9fafb",
    },
    {
        "if": {"state": "selected"},
        "backgroundColor": "#eff6ff",
        "border": "1px solid #bfdbfe",
    },
    {
        "if": {"state": "active"},
        "backgroundColor": "#eff6ff",
        "border": "1px solid #bfdbfe",
    },
]

# フラグメント一覧テーブル用（コンパクト）
_FRAG_COLUMNS_DEF = [
    {"id": "fragment_index", "name": "#", "type": "numeric"},
    {"id": "service", "name": "Service", "type": "text"},
    {"id": "file_short", "name": "File", "type": "text"},
    {"id": "lines", "name": "Lines", "type": "text"},
    {"id": "line_count", "name": "LOC", "type": "numeric"},
    {"id": "file_type", "name": "Type", "type": "text"},
]
_FRAG_STYLE_CELL = {
    "fontSize": "12px",
    "padding": "8px 12px",
    "borderBottom": "1px solid #f3f4f6",
    "borderTop": "none",
    "borderLeft": "none",
    "borderRight": "none",
    "textAlign": "left",
    "whiteSpace": "nowrap",
    "overflow": "hidden",
    "textOverflow": "ellipsis",
    "minWidth": "50px",
    "color": "#374151",
}

# ---------------------------------------------------------------------------
# カラムツールチップ定義
# ---------------------------------------------------------------------------

_COLUMN_TOOLTIPS: dict[str, str] = {
    # Service columns
    "service": "Microservice name",
    "clone_set_count": "Total clone sets that include fragments in this service",
    "inter_clone_set_count": "Clone sets shared with other services (inter-service)",
    "total_clone_line_count": "Total clone LOC (deduplicated)",
    "roc_pct": "Ratio of Clones: clone LOC / total LOC (%)",
    "comod_count": "Commits where two or more fragments were co-modified",
    "comod_other_service_count": "Number of other services sharing co-modifications",
    # File columns
    "file_name": "File name",
    "file_type": "File type (logic / test / config / data)",
    "sharing_service_count": "Number of services sharing clones with this file",
    "cross_service_clone_set_count": "Inter-service clone set count",
    "cross_cs_ratio_pct": "Inter-service clone set ratio (%)",
    "cross_service_comod_count": "Co-modification count for inter-service clones",
    # CS columns
    "clone_id": "Clone set identifier (click a row to view details)",
    "service_count": "Number of services involved in this clone set",
    "inter_frag_ratio_pct": "Inter-service fragment ratio (%)",
    "cross_service_line_count": "Total LOC of inter-service fragments",
    "file_types": "Included file types (logic, test, etc.)",
    # Fragment columns
    "fragment_index": "Index within the clone set",
    "file_short": "File name (click a row to show code)",
    "lines": "Start line - end line",
    "line_count": "Fragment LOC",
    # File-clones columns
    "n_total_fragments": "Total fragments in the clone set",
    "involved_services": "Services involved in this clone set",
}

# ---------------------------------------------------------------------------
# 初期ナビゲーション状態
# ---------------------------------------------------------------------------


def _initial_nav() -> dict:
    return {
        "origin": "ms",  # "ms" | "file" | "cs"
        "ms_name": None,  # str — 選択された MS 名 (MS Level 2 以降)
        "l2_tab": "file",  # 互換維持用. MS Baseでは常に file 扱い.
        "level": 1,  # 1 | 2 | 3 | 4
        "detail_id": None,  # str — ファイル or CS の識別子
        "compare_clone_id": None,  # str — フラグメント比較レベルのクローンID
    }


# ---------------------------------------------------------------------------
# DataTable スタブ（常に DOM に存在させる）
# ---------------------------------------------------------------------------


def _make_stub_table() -> dash_table.DataTable:
    """初期表示用の空 DataTable."""
    return dash_table.DataTable(
        id="list-main-table",
        columns=[],
        data=[],
        page_size=40,
        page_action="native",
        sort_action="native",
        sort_mode="single",
        row_selectable=False,
        style_table={"overflowX": "auto", "width": "100%"},
        style_header=_TABLE_STYLE_HEADER,
        style_cell=_TABLE_STYLE_CELL,
        style_data_conditional=_TABLE_STYLE_DATA_CONDITIONAL,
        style_cell_conditional=[
            {"if": {"column_type": "numeric"}, "textAlign": "right"},
        ],
        tooltip_header={
            col: {"value": desc, "type": "text"}
            for col, desc in _COLUMN_TOOLTIPS.items()
        },
        tooltip_delay=0,
        tooltip_duration=None,
        css=[
            {
                "selector": ".dash-table-tooltip",
                "rule": (
                    "background-color: #2b3035 !important;"
                    "color: #fff !important;"
                    "font-size: 12px;"
                    "max-width: 320px;"
                    "padding: 6px 10px;"
                    "border-radius: 4px;"
                    "white-space: normal;"
                ),
            },
        ],
    )


# ---------------------------------------------------------------------------
# メインレイアウト
# ---------------------------------------------------------------------------


def _make_file_clones_table() -> dash_table.DataTable:
    """ファイル選択時に表示するクローン一覧テーブル."""
    return dash_table.DataTable(
        id="list-file-clones-table",
        columns=[],
        data=[],
        page_size=20,
        page_action="native",
        sort_action="native",
        sort_mode="single",
        row_selectable=False,
        style_table={"overflowX": "auto", "width": "100%"},
        style_header=_TABLE_STYLE_HEADER,
        style_cell={**_TABLE_STYLE_CELL, "fontSize": "12px", "padding": "6px 10px"},
        style_data_conditional=_TABLE_STYLE_DATA_CONDITIONAL,
        style_cell_conditional=[
            {"if": {"column_type": "numeric"}, "textAlign": "right"},
        ],
        tooltip_header={
            col: {"value": desc, "type": "text"}
            for col, desc in _COLUMN_TOOLTIPS.items()
        },
        tooltip_delay=0,
        tooltip_duration=None,
        markdown_options={"html": True},
    )


def _right_panel_section_header(text: str, html_id: str | None = None) -> html.Div:
    """右パネル内のセクションヘッダー."""
    props: dict = {
        "style": {
            "padding": "8px 16px",
            "fontSize": "13px",
            "fontWeight": "700",
            "color": "#1f2937",
            "backgroundColor": "#f3f4f6",
            "borderBottom": "1px solid #e5e7eb",
        },
        "children": text,
    }
    if html_id:
        props["id"] = html_id
    return html.Div(**props)


def create_list_view_layout() -> html.Div:
    """ドリルダウンリストビューの全体レイアウトを返す.

    シングルカラム遷移方式:
      各レベルのビューが全幅で切り替わる.
      テーブルレベルでは全幅テーブル,
      詳細レベルではサマリバー + クローン一覧 + フラグメント/コード横並びを表示.
    """
    return html.Div(
        id="list-view-container",
        className="list-view-container",
        style={
            "height": "100%",
            "display": "flex",
            "flexDirection": "column",
            "overflow": "hidden",
            "backgroundColor": "#fff",
        },
        children=[
            # ── 起点タブ (MS / File / CS) ──────────────────────────────────
            dbc.Tabs(
                id="list-origin-tabs",
                active_tab="ms",
                children=[
                    dbc.Tab(label="MS Base", tab_id="ms", className="list-origin-tab"),
                    dbc.Tab(
                        label="File Base", tab_id="file", className="list-origin-tab"
                    ),
                    dbc.Tab(label="CS Base", tab_id="cs", className="list-origin-tab"),
                ],
                style={
                    "borderBottom": "2px solid #dee2e6",
                    "paddingLeft": "8px",
                    "backgroundColor": "#f8f9fa",
                    "flexShrink": "0",
                },
            ),
            # ── ツールバー（パンくず + フィルタ）──────────────────────────
            html.Div(
                id="list-toolbar",
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "16px",
                    "padding": "6px 12px",
                    "borderBottom": "1px solid #e9ecef",
                    "backgroundColor": "#fafbfc",
                    "flexShrink": "0",
                    "flexWrap": "wrap",
                },
                children=[
                    html.Div(
                        id="list-breadcrumb",
                        style={"flex": "1", "minWidth": "200px"},
                        children=[_breadcrumb_root("ms")],
                    ),
                    html.Div(
                        [
                            html.Span(
                                "File Category:",
                                style={
                                    "fontSize": "12px",
                                    "fontWeight": "600",
                                    "marginRight": "6px",
                                    "whiteSpace": "nowrap",
                                },
                            ),
                            dcc.Dropdown(
                                id="list-filetype-filter",
                                options=FILE_TYPE_OPTIONS,
                                value="all",
                                clearable=False,
                                searchable=False,
                                style={"width": "130px", "fontSize": "12px"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    html.Div(
                        [
                            html.Span(
                                "Columns:",
                                style={
                                    "fontSize": "12px",
                                    "fontWeight": "600",
                                    "marginRight": "6px",
                                    "whiteSpace": "nowrap",
                                },
                            ),
                            dcc.Dropdown(
                                id="list-columns-toggle",
                                options=[],
                                value=[],
                                multi=True,
                                clearable=False,
                                placeholder="Select columns",
                                className="list-columns-toggle",
                                style={
                                    "minWidth": "280px",
                                    "maxWidth": "520px",
                                    "fontSize": "12px",
                                },
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center", "flex": "1"},
                    ),
                ],
            ),
            # ── 旧Level 2サブタブのプレースホルダ. タブUIは廃止. ──────────
            html.Div(
                id="list-l2-subtabs-container",
                style={"flexShrink": "0", "display": "none"},
                children=[],
            ),
            # ── データが無い時のメッセージ ─────────────────────────────────
            html.Div(
                id="list-no-data-msg",
                style={
                    "display": "none",
                    "padding": "60px 20px",
                    "color": "#6b7280",
                    "textAlign": "center",
                    "flexDirection": "column",
                    "alignItems": "center",
                    "justifyContent": "center",
                },
                children=[
                    html.Div("📊", style={"fontSize": "48px", "marginBottom": "16px", "opacity": "0.5"}),
                    html.H4("No Project Selected", style={"color": "#374151", "fontWeight": "600", "marginBottom": "8px", "fontSize": "18px"}),
                    html.P("Please select a project from the top menu to view clone metrics.", style={"fontSize": "14px", "margin": "0"})
                ],
            ),
            # ══ メインコンテンツ: シングルカラム遷移 ═══════════════════════
            html.Div(
                id="list-content-area",
                style={
                    "display": "flex",
                    "flexDirection": "column",
                    "flex": "1",
                    "minHeight": "0",
                    "overflow": "hidden",
                },
                children=[
                    # ── テーブルセクション（Level 1–2: 全幅テーブル）──────
                    html.Div(
                        id="list-table-section",
                        style={
                            "flex": "1",
                            "minHeight": "0",
                            "overflowY": "auto",
                        },
                        children=[
                            dcc.Loading(
                                id="loading-list",
                                type="dot",
                                color="#4a90d9",
                                children=[
                                    html.Div(
                                        id="list-table-wrapper",
                                        style={"padding": "8px 12px"},
                                        children=[_make_stub_table()],
                                    ),
                                ],
                            ),
                        ],
                    ),
                    # ── 詳細セクション（Level 3 / 詳細レベル: 全幅）──────
                    html.Div(
                        id="list-detail-section",
                        className="list-detail-section",
                        style={"display": "none"},
                        children=[
                            # サマリバー (コンパクト要約 + 展開式詳細)
                            html.Div(
                                id="list-detail-panel",
                                style={"padding": "0"},
                            ),
                            # ファイル選択時: 関連クローン一覧 (全幅)
                            html.Div(
                                id="list-file-clones-container",
                                style={"display": "none"},
                                children=[
                                    _right_panel_section_header("Related Clone Sets"),
                                    html.Div(
                                        style={
                                            "flex": "1",
                                            "minHeight": "0",
                                            "overflowY": "auto",
                                            "padding": "4px 8px 8px",
                                        },
                                        children=[_make_file_clones_table()],
                                    ),
                                ],
                            ),
                        ],
                    ),
                    # ── フラグメント比較セクション（全幅）──────────────────
                    html.Div(
                        id="list-frag-compare-section",
                        style={"display": "none"},
                        children=[
                            # CS サマリバー
                            html.Div(id="list-compare-summary-panel"),
                            # 横並び: フラグメント一覧(左) + コード比較(右)
                            html.Div(
                                className="list-compare-split",
                                children=[
                                    # 左: フラグメント一覧
                                    html.Div(
                                        className="list-compare-frag-pane",
                                        children=[
                                            html.Div(
                                                id="list-compare-frag-header",
                                                style={
                                                    "padding": "6px 14px",
                                                    "fontSize": "12px",
                                                    "fontWeight": "700",
                                                    "color": "#2c3e50",
                                                    "backgroundColor": "#f0f3f7",
                                                    "borderBottom": "1px solid #dee2e6",
                                                },
                                                children="Fragments",
                                            ),
                                            html.Div(
                                                style={
                                                    "overflowY": "auto",
                                                    "flex": "1",
                                                    "minHeight": "0",
                                                },
                                                children=[
                                                    dash_table.DataTable(
                                                        id="list-compare-frag-table",
                                                        columns=_FRAG_COLUMNS_DEF,
                                                        data=[],
                                                        page_action="none",
                                                        sort_action="native",
                                                        style_table={
                                                            "overflowX": "auto",
                                                            "width": "100%",
                                                        },
                                                        style_header=_TABLE_STYLE_HEADER,
                                                        style_cell=_FRAG_STYLE_CELL,
                                                        style_data_conditional=_TABLE_STYLE_DATA_CONDITIONAL,
                                                        style_cell_conditional=[
                                                            {
                                                                "if": {
                                                                    "column_id": "fragment_index"
                                                                },
                                                                "textAlign": "right",
                                                                "maxWidth": "40px",
                                                            },
                                                            {
                                                                "if": {
                                                                    "column_id": "line_count"
                                                                },
                                                                "textAlign": "right",
                                                            },
                                                        ],
                                                        tooltip_header={
                                                            col: {
                                                                "value": desc,
                                                                "type": "text",
                                                            }
                                                            for col, desc in _COLUMN_TOOLTIPS.items()
                                                        },
                                                        tooltip_delay=0,
                                                        tooltip_duration=None,
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                    # 右: コード比較エリア (動的にコールバックで構築)
                                    html.Div(
                                        id="list-compare-code-area",
                                        className="list-compare-code-area",
                                        children=[
                                            html.Div(
                                                "Click a fragment to show code",
                                                style={
                                                    "display": "flex",
                                                    "alignItems": "center",
                                                    "justifyContent": "center",
                                                    "height": "100%",
                                                    "color": "#888",
                                                    "fontSize": "14px",
                                                },
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            # ── ストア ────────────────────────────────────────────────────
            dcc.Store(id="list-nav-store", data=_initial_nav()),
            dcc.Store(id="list-frag-selected-store", data=[]),
        ],
    )


# ---------------------------------------------------------------------------
# パンくずリスト生成
# ---------------------------------------------------------------------------


def _breadcrumb_root(origin: str) -> html.Span:
    labels = {"ms": "MS Base", "file": "File Base", "cs": "CS Base"}
    return html.Span(
        labels.get(origin, origin),
        id={"type": "list-bc-btn", "index": "root"},
        n_clicks=0,
        style={
            "cursor": "pointer",
            "color": "#0366d6",
            "fontSize": "12px",
            "fontWeight": "600",
        },
    )


def build_breadcrumb(
    origin: str,
    ms_name: str | None,
    level: int,
    l2_tab: str,
    detail_id: str | None,
    compare_clone_id: str | None = None,
) -> list:
    """ナビゲーション状態からパンくずリスト要素を生成する."""
    sep = html.Span(
        " / ", style={"color": "#d1d5db", "margin": "0 8px", "fontSize": "14px", "fontWeight": "400"}
    )
    bc: list = []

    # Root
    labels = {"ms": "MS Base", "file": "File Base", "cs": "CS Base"}
    root_label = labels.get(origin, origin)
    has_deeper = level > 1
    bc.append(
        html.Span(
            root_label,
            id={"type": "list-bc-btn", "index": "root"},
            n_clicks=0,
            style={
                "cursor": "pointer" if has_deeper else "default",
                "color": "#3b82f6" if has_deeper else "#374151",
                "fontSize": "13px",
                "fontWeight": "600",
                "padding": "4px 8px",
                "borderRadius": "4px",
                "backgroundColor": "#eff6ff" if has_deeper else "transparent",
            },
        )
    )

    if origin == "ms" and level >= 2 and ms_name:
        bc.append(sep)
        has_deeper_ms = level > 2
        bc.append(
            html.Span(
                ms_name,
                id={"type": "list-bc-btn", "index": "ms"},
                n_clicks=0,
                style={
                    "cursor": "pointer" if has_deeper_ms else "default",
                    "color": "#3b82f6" if has_deeper_ms else "#374151",
                    "fontSize": "13px",
                    "padding": "4px 8px",
                    "borderRadius": "4px",
                    "backgroundColor": "#eff6ff" if has_deeper_ms else "transparent",
                },
            )
        )

    if detail_id:
        # detail_id 表示 (ファイルパス or クローンID)
        is_clickable = compare_clone_id is not None
        bc.append(sep)
        normalized = str(detail_id).replace("\\", "/")
        if "/" in normalized:
            short = normalized.rsplit("/", 1)[-1]
        else:
            short = detail_id if len(detail_id) <= 40 else f"…{detail_id[-38:]}"
        bc.append(
            html.Span(
                short,
                id={"type": "list-bc-btn", "index": "detail"},
                n_clicks=0,
                style={
                    "cursor": "pointer" if is_clickable else "default",
                    "color": "#3b82f6" if is_clickable else "#374151",
                    "fontSize": "13px",
                    "fontStyle": "italic",
                    "padding": "4px 8px",
                    "borderRadius": "4px",
                    "backgroundColor": "#eff6ff" if is_clickable else "transparent",
                },
            )
        )

    if compare_clone_id is not None:
        bc.append(sep)
        bc.append(
            html.Span(
                f"Clone {compare_clone_id}",
                style={
                    "fontSize": "13px",
                    "color": "#374151",
                    "fontWeight": "600",
                    "padding": "4px 8px",
                },
            )
        )

    return bc


# ---------------------------------------------------------------------------
# Level 3 詳細パネル — サマリバー + 展開式詳細
# ---------------------------------------------------------------------------


def build_detail_panel(
    origin: str,
    l2_tab: str,
    detail_id: str,
    metrics: dict,
) -> list:
    """詳細レベルのサマリバーと展開式詳細テーブルを生成する.

    コンパクトな1-2行の要約バーを上部に表示し,
    [▼] をクリックすると全メトリクスを展開表示する.
    """
    if origin in ("file",) or (origin == "ms" and l2_tab == "file"):
        return _file_summary_bar(detail_id, metrics)
    else:
        return _cs_summary_bar(detail_id, metrics)


def _summary_metric_badge(label: str, value: object) -> html.Span:
    """サマリバー内のメトリクスバッジ."""
    return html.Span(
        [
            html.Span(
                f"{label}: ",
                style={"fontWeight": "600", "color": "#4b5563"},
            ),
            html.Span(
                str(value),
                style={"fontWeight": "700", "color": "#111827"},
            ),
        ],
        className="list-summary-badge",
        style={
            "backgroundColor": "#f3f4f6",
            "padding": "4px 10px",
            "borderRadius": "16px",
            "fontSize": "12px",
            "display": "inline-flex",
            "alignItems": "center",
            "border": "1px solid #e5e7eb"
        }
    )


def _build_summary_bar(
    icon: str,
    title: str,
    badges: list,
    full_items: list[tuple[str, object]],
) -> list:
    """サマリバー + 展開式詳細テーブルのレイアウトを構築する."""
    detail_rows = [
        html.Tr(
            [
                html.Td(
                    label,
                    style={
                        "fontWeight": "600",
                        "padding": "3px 12px",
                        "fontSize": "12px",
                        "whiteSpace": "nowrap",
                        "color": "#555",
                    },
                ),
                html.Td(str(value), style={"padding": "3px 12px", "fontSize": "12px"}),
            ]
        )
        for label, value in full_items
    ]

    return [
        # コンパクトサマリバー
        html.Div(
            className="list-summary-bar",
            style={
                "padding": "10px 16px",
                "backgroundColor": "#ffffff",
                "borderBottom": "1px solid #e5e7eb",
                "display": "flex",
                "justifyContent": "space-between",
                "alignItems": "center",
            },
            children=[
                html.Div(
                    className="list-summary-inline",
                    style={"display": "flex", "alignItems": "center", "gap": "10px", "flexWrap": "wrap"},
                    children=[
                        html.Span(
                            f"{icon} {title}",
                            style={
                                "fontWeight": "700",
                                "fontSize": "14px",
                                "color": "#1f2937",
                                "marginRight": "8px",
                            },
                        ),
                        *[
                            html.Span(
                                children=[b],
                                style={
                                    "display": "inline-flex",
                                    "alignItems": "center",
                                },
                            )
                            for b in badges
                        ],
                    ],
                ),
                html.Button(
                    "▼",
                    id="list-summary-toggle",
                    n_clicks=0,
                    className="list-summary-toggle-btn",
                    style={
                        "background": "none",
                        "border": "none",
                        "cursor": "pointer",
                        "color": "#6b7280",
                        "fontSize": "12px",
                        "padding": "4px",
                    }
                ),
            ],
        ),
        # 展開式 全メトリクス詳細
        dbc.Collapse(
            id="list-summary-collapse",
            is_open=False,
            children=html.Div(
                style={"padding": "0 14px 8px"},
                children=[
                    dbc.Table(
                        html.Tbody(detail_rows),
                        bordered=False,
                        striped=True,
                        size="sm",
                        style={"marginBottom": "0"},
                    ),
                ],
            ),
        ),
    ]


def _file_summary_bar(file_path: str, metrics: dict) -> list:
    """ファイル詳細のサマリバーを生成する."""
    from pathlib import Path as _Path

    file_df = metrics.get("file")
    if file_df is None or file_df.empty:
        return [html.P(f"No detail for: {file_path}", style={"color": "#888"})]

    row = file_df[file_df["file_path"] == file_path]
    if row.empty:
        return [html.P(f"File not found: {file_path}", style={"color": "#888"})]
    row = row.iloc[0]

    short_name = _Path(file_path).name
    badges = [
        _summary_metric_badge("Service", row.get("service", "—")),
        _summary_metric_badge("Type", row.get("file_type", "—")),
        _summary_metric_badge("Shared MS", row.get("sharing_service_count", "—")),
        _summary_metric_badge(
            "Inter CS",
            f"{row.get('cross_service_clone_set_count', '—')}"
            f" ({row.get('cross_cs_ratio_pct', 0):.0f}%)",
        ),
        _summary_metric_badge("Comod", row.get("cross_service_comod_count", "—")),
    ]

    full_items = [
        ("File", file_path),
        ("Service", row.get("service", "—")),
        ("File Category", row.get("file_type", "—")),
        ("Shared MS Count", row.get("sharing_service_count", "—")),
        ("Total MS Count", row.get("total_service_count", "—")),
        ("Sharing MS Ratio", f"{row.get('sharing_service_ratio', 0) * 100:.1f}%"),
        ("Inter-Service CS Count", row.get("cross_service_clone_set_count", "—")),
        (
            "Inter-Service CS Ratio",
            f"{row.get('cross_service_clone_set_ratio', 0) * 100:.1f}%",
        ),
        ("Inter-Service Clone LOC", row.get("cross_service_line_count", "—")),
        ("Inter-Service Comod Count", row.get("cross_service_comod_count", "—")),
        ("Comod Shared MS Count", row.get("comod_shared_service_count", "—")),
    ]

    return _build_summary_bar("📄", short_name, badges, full_items)


def _cs_summary_bar(clone_id: str, metrics: dict) -> list:
    """クローンセット詳細のサマリバーを生成する."""
    cs_df = metrics.get("clone_set")
    if cs_df is None or cs_df.empty:
        return [html.P(f"No detail for clone set: {clone_id}", style={"color": "#888"})]

    row = cs_df[cs_df["clone_id"].astype(str) == str(clone_id)]
    if row.empty:
        return [html.P(f"Clone set not found: {clone_id}", style={"color": "#888"})]
    row = row.iloc[0]

    badges = [
        _summary_metric_badge("Service Span", row.get("service_count", "—")),
        _summary_metric_badge("Comod", row.get("comod_count", "—")),
        _summary_metric_badge(
            "Comod Frag%",
            f"{row.get('comod_fragment_ratio', 0) * 100:.0f}%",
        ),
        _summary_metric_badge(
            "Inter%",
            f"{row.get('cross_service_fragment_ratio', 0) * 100:.0f}%",
        ),
        _summary_metric_badge("Inter LOC", row.get("cross_service_line_count", "—")),
    ]

    full_items = [
        ("Clone ID", clone_id),
        ("Involved Services", row.get("involved_services", "—")),
        ("# Involved MS", row.get("service_count", "—")),
        ("File Categories", row.get("file_types", "—")),
        ("Inter-Service Frag Count", row.get("cross_service_fragment_count", "—")),
        (
            "Inter-Service Frag Ratio",
            f"{row.get('cross_service_fragment_ratio', 0) * 100:.1f}%",
        ),
        ("Inter-Service Clone LOC", row.get("cross_service_line_count", "—")),
        ("Inter-Service Scale", row.get("cross_service_scale", "—")),
        ("Simultaneous Mod Count", row.get("comod_count", "—")),
        ("Comod Fragment Count", row.get("comod_fragment_count", "—")),
        ("Comod Fragment Ratio", f"{row.get('comod_fragment_ratio', 0) * 100:.1f}%"),
    ]

    return _build_summary_bar("🔗", f"Clone Set #{clone_id}", badges, full_items)
