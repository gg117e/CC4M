import logging

from dash import html, dcc
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from sidebar_nav import build_dash_sidebar_nav
from ..constants import DetectionMethod
from .summary import (
    create_help_section,
    build_dashboard_view,
    build_project_summary,
)
from .list_view import create_list_view_layout
from .stats_metrics_explorer import create_stats_metrics_explorer
from .statistics_dashboard import create_statistics_dashboard

logger = logging.getLogger(__name__)


def create_layout(
    available_projects, available_languages, default_value, initial_fig, initial_summary
):
    """Dashアプリの全体レイアウトを生成する"""

    # ダッシュボードデータの読み込み
    from ..data_loader import load_dashboard_data

    dashboard_data = load_dashboard_data()
    dashboard_view = build_dashboard_view(dashboard_data)

    # 言語フィルターのオプションを作成
    language_options = [{"label": "All Languages", "value": "all"}]
    language_options.extend(
        [{"label": lang, "value": lang} for lang in available_languages]
    )

    # 既存の散布図ビューのコンテンツ
    # プロジェクト選択はタブの外に出すため、ここではフィルタから開始
    scatter_view_content = html.Div(
        className="container",
        children=[
            # 上部カード：コントロールパネルとプロジェクト概要
            html.Div(
                className="card",
                children=[
                    html.Div(
                        className="control-row",
                        children=[
                            html.Label(
                                "Clone ID Filter:",
                                className="control-label",
                                style={"width": "120px"},
                            ),
                            dcc.Dropdown(
                                id="clone-id-filter",
                                options=[{"label": "Show all clones", "value": "all"}],
                                value="all",
                                placeholder="Filter by Clone ID...",
                                style={
                                    "width": "400px",
                                    "fontFamily": "monospace",
                                    "fontSize": "13px",
                                },
                                optionHeight=35,
                                maxHeight=300,
                            ),
                        ],
                    ),
                    html.Div(
                        className="control-row",
                        children=[
                            html.Div(
                                id="filter-status",
                                style={
                                    "fontSize": "13px",
                                    "color": "#333",
                                    "fontWeight": "bold",
                                },
                            )
                        ],
                    ),
                    html.Hr(),  # 区切り線
                    html.Div(id="project-summary", children=initial_summary),
                ],
            ),
            # 中央カード：散布図
            html.Div(
                className="card",
                children=[
                    create_help_section(),  # ヘルプセクションを追加
                    dcc.Graph(id="scatter-plot", figure=initial_fig),
                ],
            ),
            # 下部カード：クローン詳細
            html.Div(
                className="card",
                children=[
                    html.Div(
                        id="scatter-click-scroll-dummy",
                        style={"display": "none"},
                    ),
                    html.Div(
                        id="clone-selector-container"
                    ),  # クローン選択UI用のコンテナ
                    html.Div(
                        id="clone-details-table",
                        children=[
                            html.P("Click a point on the graph to view clone details.")
                        ],
                    ),
                ],
            ),
        ],
    )

    # ネットワークグラフビューのコンテンツ
    network_view_content = html.Div(
        className="container",
        children=[
            html.Div(
                className="card",
                children=[
                    html.H4("Service Dependency Network", className="card-title"),
                    html.P(
                        "Visualizes clone sharing relationships between microservices. Edges represent clone sharing, and node sizes represent file counts.",
                        className="text-muted",
                    ),
                    dcc.Graph(id="network-graph", style={"height": "800px"}),
                ],
            )
        ],
    )

    # 共通のプロジェクト選択行とフィルタ
    project_selector = html.Div(
        className="container mb-3",
        children=[
            html.Div(
                className="card",
                children=[
                    html.Div(
                        className="control-row",
                        children=[
                            html.Label(
                                "Select project:",
                                className="control-label",
                                style={"width": "120px"},
                            ),
                            dcc.Dropdown(
                                id="project-dropdown",
                                options=available_projects,
                                value=default_value,
                                style={
                                    "flex": 1,
                                    "minWidth": "500px",
                                    "maxWidth": "800px",
                                },
                                optionHeight=70,
                                maxHeight=400,
                            ),
                        ],
                    ),
                    # フィルタ群をRow/Colで整理 (共通化)
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Label(
                                        "Detection Method:", className="fw-bold"
                                    ),
                                    dbc.RadioItems(
                                        id="detection-method-filter",
                                        options=DetectionMethod.get_options(),
                                        value=DetectionMethod.NO_IMPORT,
                                        inline=True,
                                        className="mb-2",
                                    ),
                                ],
                                width=3,
                            ),
                            dbc.Col(
                                [
                                    html.Label("Co-modification:", className="fw-bold"),
                                    dbc.RadioItems(
                                        id="comodified-filter",
                                        options=[
                                            {"label": "All", "value": "all"},
                                            {"label": "Yes", "value": "true"},
                                            {"label": "No", "value": "false"},
                                        ],
                                        value="all",
                                        inline=True,
                                        className="mb-2",
                                    ),
                                ],
                                width=3,
                            ),
                            dbc.Col(
                                [
                                    html.Label("File Category:", className="fw-bold"),
                                    dbc.RadioItems(
                                        id="code-type-filter",
                                        options=[
                                            {"label": "All", "value": "all"},
                                            {"label": "Data", "value": "data"},
                                            {"label": "Logic", "value": "logic"},
                                            {"label": "Test", "value": "test"},
                                            {"label": "Config", "value": "config"},
                                            {"label": "Mixed", "value": "mixed"},
                                        ],
                                        value="all",
                                        inline=True,
                                        className="mb-2",
                                    ),
                                ],
                                width=3,
                            ),
                            dbc.Col(
                                [
                                    html.Label("Scope:", className="fw-bold"),
                                    dbc.RadioItems(
                                        id="scope-filter",
                                        options=[
                                            {"label": "Resolved", "value": "resolved"},
                                            {"label": "All", "value": "all"},
                                            {"label": "Unknown", "value": "unknown"},
                                        ],
                                        value="resolved",
                                        inline=True,
                                        className="mb-2",
                                    ),
                                ],
                                width=3,
                            ),
                        ],
                        className="mb-3 p-2 border rounded bg-light",
                    ),
                ],
            )
        ],
    )

    # タブ構成
    return dbc.Container(
        [
            html.H1("Microservice Code Clone Analysis", className="my-4 text-center"),
            project_selector,
            dcc.Tabs(
                id="main-tabs",
                value="tab-dashboard",
                children=[
                    dcc.Tab(
                        label="Dashboard",
                        value="tab-dashboard",
                        children=[dashboard_view],
                    ),
                    dcc.Tab(
                        label="Scatter Plot",
                        value="tab-scatter",
                        children=[scatter_view_content],
                    ),
                    dcc.Tab(
                        label="Dependency Network",
                        value="tab-network",
                        children=[network_view_content],
                    ),
                ],
            ),
        ],
        fluid=True,
    )


def _build_nav_sidebar():
    """左側ナビゲーションサイドバーを構築する.

    Returns:
        html.Nav コンポーネント.
    """
    return html.Nav(
        id="app-sidebar",
        className="app-sidebar",
        children=[
            # Brand area (with collapse toggle)
            html.Div(
                className="sidebar-brand",
                children=[
                    html.Div(
                        [
                            html.Span(
                                "CC4M",
                                className="sidebar-brand-text",
                            ),
                        ],
                        className="sidebar-brand-inner",
                    ),
                    html.Button(
                        html.I(
                            className="bi bi-chevron-left",
                            id="sidebar-toggle-icon",
                        ),
                        id="sidebar-toggle",
                        className="sidebar-collapse-btn",
                        n_clicks=0,
                        title="Toggle sidebar",
                    ),
                ],
            ),
            # Navigation items
            html.Ul(
                className="sidebar-nav-list",
                children=build_dash_sidebar_nav(active_key="scatter"),
            ),
            # Footer: help button
            html.Div(
                className="sidebar-footer",
                children=[
                    html.Button(
                        html.I(className="bi bi-question-circle"),
                        id="help-btn",
                        className="sidebar-help-btn",
                        n_clicks=0,
                        title="About this tool",
                    ),
                ],
            ),
        ],
    )


def _build_help_modal():
    """ヘルプモーダルダイアログを構築する.

    Returns:
        dbc.Modal コンポーネント.
    """
    return dbc.Modal(
        id="help-modal",
        is_open=False,
        size="lg",
        centered=True,
        children=[
            dbc.ModalHeader(
                dbc.ModalTitle("CC4M"),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    html.H5("About", className="mb-3"),
                    html.P(
                        "MSCCVis (Microservice Code Clone Visualizer) is a toolset "
                        "for detecting and visualizing code clones across microservice "
                        "repositories. It integrates CCFinderSW for clone detection "
                        "and CLAIM for microservice boundary identification.",
                    ),
                    html.Hr(),
                    html.H6("Views"),
                    html.Ul(
                        [
                            html.Li(
                                [
                                    html.Strong("Scatter Plot"),
                                    html.Span(
                                        " — Visualizes clone pairs as points. "
                                        "Filter by co-modification, scope, and file category."
                                    ),
                                ]
                            ),
                            html.Li(
                                [
                                    html.Strong("List View"),
                                    html.Span(
                                        " — Browse repository files and "
                                        "inspect clone fragments side-by-side."
                                    ),
                                ]
                            ),
                            html.Li(
                                [
                                    html.Strong("Metric View"),
                                    html.Span(
                                        " — Filter microservices, clone sets, "
                                        "and files by metric ranges, then drill "
                                        "down into fragments and source code."
                                    ),
                                ]
                            ),
                            html.Li(
                                [
                                    html.Strong("Statistics View"),
                                    html.Span(
                                        " — Project-wide dashboard with KPIs, "
                                        "language mix, and per-service clone "
                                        "summaries across all languages."
                                    ),
                                ]
                            ),
                        ]
                    ),
                    html.Hr(),
                    html.H6("Tips"),
                    html.Ul(
                        [
                            html.Li(
                                "Click a point on the scatter plot to see clone details."
                            ),
                            html.Li("Use the sidebar to switch between views."),
                            html.Li(
                                "Collapse the sidebar with the toggle button "
                                "for more screen space."
                            ),
                        ]
                    ),
                ]
            ),
        ],
    )


def create_ide_layout(
    available_projects,
    available_languages,
    default_project,
    initial_fig,
    initial_summary,
    *,
    project_names=None,
):
    """サイドバーナビゲーション + メインコンテンツのレイアウトを作成する."""

    # Project Name Selector (Step 1)
    project_name_selector = dcc.Dropdown(
        id="project-name-selector",
        options=project_names or [],
        value=None,
        placeholder="Select Project",
        style={"width": "clamp(180px, 24vw, 260px)"},
        clearable=False,
        maxHeight=500,
        optionHeight=45,
    )

    # CSV File Selector (Step 2) — ID は既存コールバック互換のため維持
    project_selector = dcc.Dropdown(
        id="project-selector",
        options=available_projects,
        value=default_project,
        placeholder="Select Dataset",
        style={"width": "clamp(240px, 34vw, 420px)", "fontSize": "0.82rem"},
        clearable=False,
        disabled=True,
        optionHeight=76,
        maxHeight=500,
    )

    # ── Navigation Sidebar ──
    nav_sidebar = _build_nav_sidebar()

    # ── Content Header (project selectors) ──
    content_header = html.Div(
        className="content-header",
        children=[
            html.H2(
                "Scatter Plot",
                id="page-title",
                className="content-title",
                **{"data-i18n": "navScatter"},
            ),
            html.Div(
                className="header-selectors",
                children=[
                    html.Div(
                        className="selector-group",
                        children=[
                            html.Span(
                                "Project:",
                                className="selector-label",
                                **{"data-i18n": "labelProject"},
                            ),
                            project_name_selector,
                        ],
                    ),
                    html.Span("▸", className="selector-separator"),
                    html.Div(
                        className="selector-group dataset-selector-group",
                        children=[
                            html.Span(
                                "Dataset:",
                                className="selector-label",
                                **{"data-i18n": "labelDataset"},
                            ),
                            project_selector,
                        ],
                    ),
                ],
            ),
        ],
    )

    # ── Explorer (List View) ──
    explorer_sidebar = html.Div(
        [
            html.Div(
                [
                    html.Div(
                        "EXPLORER",
                        className="sidebar-header",
                        **{"data-i18n": "sidebarExplorer"},
                    ),
                    html.Div(id="file-tree-container", className="sidebar-tree"),
                ],
                className="sidebar-section",
                style={"flex": "2", "borderBottom": "1px solid #e0e0e0"},
            ),
            html.Div(
                [
                    html.Div(id="drag-handle", className="sidebar-resizer"),
                    html.Div(
                        "CLONE OUTLINE",
                        className="sidebar-header",
                        **{"data-i18n": "sidebarCloneOutline"},
                    ),
                    html.Div(
                        id="clone-list-container",
                        className="sidebar-tree",
                        style={"flex": "1"},
                    ),
                ],
                className="sidebar-section",
                style={"flex": "1", "display": "flex", "flexDirection": "column"},
            ),
        ],
        className="ide-sidebar",
    )

    editor_content = html.Div(
        [
            html.Div(
                id="editor-header",
                className="editor-header",
                children=html.Span(
                    "Select a file to view", **{"data-i18n": "editorPlaceholder"}
                ),
            ),
            html.Div(
                id="editor-content",
                className="editor-content",
                children=[
                    html.Div(
                        html.Span(
                            "Select a file from the explorer to view its content.",
                            **{"data-i18n": "emptyState"},
                        ),
                        id="empty-state-message",
                        style={
                            "padding": "20px",
                            "color": "#777",
                            "textAlign": "center",
                            "marginTop": "50px",
                        },
                    )
                ],
                style={"padding": "0", "height": "100%", "overflow": "hidden"},
            ),
        ],
        className="ide-content",
    )

    # ── Scatter View (Redesigned: Minimal Header + Filter Drawer) ──
    # Filter Drawer (Slide-in panel)
    # Hidden inputs for backward compatibility
    filter_drawer = html.Div(
        [
            dcc.Dropdown(
                id="clone-sort-order",
                options=[{"label": "Service count", "value": "service_count"}],
                value="service_count",
            ),
            dcc.Dropdown(
                id="min-services-filter", options=[{"label": "-", "value": 0}], value=2
            ),
            dcc.Dropdown(
                id="min-comod-filter", options=[{"label": "-", "value": 0}], value=0
            ),
            dcc.Input(id="clone-id-filter", type="hidden", value="all"),
            dcc.Dropdown(id="service-a-filter", options=[], value=None),
            dcc.Dropdown(id="service-b-filter", options=[], value=None),
            html.Div(id="service-b-group"),
            html.Button(id="clear-filters-btn"),
            # Placeholder for drawer properties to avoid callback errors if they still update filter-drawer-overlay
            html.Div(id="filter-drawer-overlay", n_clicks=0),
            html.Button(id="filter-drawer-close", n_clicks=0),
            html.Button(id="filter-drawer-close-footer", n_clicks=0),
        ],
        id="filter-drawer",
        style={"display": "none"},
    )

    scatter_view = html.Div(
        [
            filter_drawer,
            # Compact filter panel
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label(
                                        "SERVICE SCOPE", className="toolbar-label"
                                    ),
                                    dbc.RadioItems(
                                        id="service-scope-filter",
                                        options=[
                                            {"label": "All", "value": "all"},
                                            {"label": "Within", "value": "within"},
                                            {"label": "Cross", "value": "cross"},
                                        ],
                                        value="all",
                                        inline=True,
                                        className="filter-radio",
                                    ),
                                ],
                                className="filter-field service-scope",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "CO-MODIFICATION COUNT",
                                        className="toolbar-label",
                                    ),
                                    html.Div(
                                        [
                                            html.Button(
                                                "All",
                                                id="btn-comod-all",
                                                className="filter-preset-btn active",
                                            ),
                                            html.Button(
                                                "0",
                                                id="btn-comod-0",
                                                className="filter-preset-btn",
                                            ),
                                            html.Button(
                                                "1+",
                                                id="btn-comod-1",
                                                className="filter-preset-btn",
                                            ),
                                            html.Div(
                                                [
                                                    dcc.Input(
                                                        id="comod-draft-input",
                                                        type="number",
                                                        min=0,
                                                        step=1,
                                                        placeholder="n",
                                                        className="custom-draft-input",
                                                    ),
                                                    html.Span(
                                                        "+",
                                                        className="input-plus-label",
                                                    ),
                                                ],
                                                id="comod-input-wrapper",
                                                className="custom-input-wrapper",
                                                title="Show clone groups with at least n co-modifications",
                                            ),
                                        ],
                                        className="filter-button-group",
                                    ),
                                    # Invisible inputs for backward compatibility
                                    dcc.Input(
                                        id="comodification-filter",
                                        type="hidden",
                                        value="all",
                                    ),
                                    dcc.Input(
                                        id="comodification-min-filter",
                                        type="hidden",
                                        value=0,
                                    ),
                                ],
                                className="filter-field co-modification",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "SERVICE SPAN", className="toolbar-label"
                                    ),
                                    html.Div(
                                        [
                                            html.Button(
                                                "All",
                                                id="btn-spread-all",
                                                className="filter-preset-btn active",
                                            ),
                                            html.Button(
                                                "2+",
                                                id="btn-spread-2",
                                                className="filter-preset-btn",
                                            ),
                                            html.Div(
                                                [
                                                    dcc.Input(
                                                        id="spread-draft-input",
                                                        type="number",
                                                        min=1,
                                                        step=1,
                                                        placeholder="n",
                                                        className="custom-draft-input",
                                                    ),
                                                    html.Span(
                                                        "+",
                                                        className="input-plus-label",
                                                    ),
                                                ],
                                                id="spread-input-wrapper",
                                                className="custom-input-wrapper",
                                                title="Show clone groups spanning at least n services",
                                            ),
                                        ],
                                        id="service-spread-btn-group",
                                        className="filter-button-group",
                                    ),
                                    html.Div(
                                        "Unavailable for Within scope",
                                        id="service-spread-disabled-note",
                                        className="filter-disabled-note",
                                        style={"display": "none"},
                                    ),
                                    # Invisible inputs for backward compatibility
                                    dcc.Input(
                                        id="service-spread-filter",
                                        type="hidden",
                                        value="all",
                                    ),
                                    dcc.Input(
                                        id="service-spread-min-filter",
                                        type="hidden",
                                        value=1,
                                    ),
                                ],
                                className="filter-field service-spread",
                                id="service-spread-field-container",
                            ),
                        ],
                        className="filter-row filter-row-primary",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label(
                                        "FILE CATEGORY",
                                        className="toolbar-label",
                                    ),
                                    html.Div(
                                        id="code-type-buttons-container",
                                        className="code-type-buttons toolbar-code-type",
                                    ),
                                    dcc.Store(id="code-type-store", data="all"),
                                ],
                                className="filter-field code-type",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "PLOT SIZE", className="toolbar-label"
                                    ),
                                    html.Div(
                                        [
                                            html.Button(
                                                html.I(className="bi bi-dash-lg"),
                                                id="scatter-size-decrease",
                                                n_clicks=0,
                                                className="filter-preset-btn scatter-size-btn",
                                                title="Shrink plot",
                                            ),
                                            html.Button(
                                                html.I(
                                                    className="bi bi-arrow-clockwise"
                                                ),
                                                id="scatter-size-reset",
                                                n_clicks=0,
                                                className="filter-preset-btn scatter-size-btn active",
                                                title="Reset plot size",
                                            ),
                                            html.Button(
                                                html.I(className="bi bi-plus-lg"),
                                                id="scatter-size-increase",
                                                n_clicks=0,
                                                className="filter-preset-btn scatter-size-btn",
                                                title="Enlarge plot",
                                            ),
                                        ],
                                        className="filter-button-group scatter-size-group",
                                    ),
                                    dcc.Store(id="scatter-size-store", data=0),
                                ],
                                className="filter-field scatter-size",
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label(
                                                "CLONE ID", className="toolbar-label"
                                            ),
                                            html.Span(
                                                id="clone-id-option-count",
                                                className="clone-option-count",
                                            ),
                                        ],
                                        className="clone-id-heading",
                                    ),
                                    dcc.Dropdown(
                                        id="cross-service-filter",
                                        options=[{"label": "All", "value": "all"}],
                                        value="all",
                                        placeholder=("Search clone ID..."),
                                        clearable=True,
                                        searchable=True,
                                        optionHeight=44,
                                        maxHeight=440,
                                        className="toolbar-dropdown clone-id-dropdown",
                                    ),
                                ],
                                className="filter-field clone-id",
                            ),
                        ],
                        className="filter-row filter-row-secondary",
                    ),
                    html.Div(
                        id="scatter-stats-header",
                        className="scatter-pair-count filter-stats-inline",
                    ),
                ],
                className="filter-panel filter-panel-wrap",
            ),
            # Active Filter Tags
            html.Div(
                [
                    html.Div(
                        id="active-filter-tags",
                        className="filter-tags-container",
                        children=[
                            html.Span(
                                [html.B("0"), " / 0 pairs (0.0%)"],
                                className="filter-pair-summary",
                                style={"marginLeft": "16px"},
                            )
                        ],
                    ),
                ],
                className="scatter-minimal-header",
            ),
            # Graph row
            html.Div(
                [
                    html.Div(
                        [
                            dcc.Loading(
                                id="loading-scatter",
                                type="circle",
                                children=[
                                    dcc.Graph(
                                        id="scatter-plot",
                                        figure=initial_fig,
                                        className="scatter-graph",
                                        style={
                                            "height": "clamp(720px, 78vh, 1000px)",
                                            "--scatter-graph-height": (
                                                "clamp(720px, 78vh, 1000px)"
                                            ),
                                            "--scatter-graph-min-height": "720px",
                                            "minHeight": "720px",
                                            "width": "100%",
                                        },
                                        config={"responsive": True},
                                    )
                                ],
                            )
                        ],
                        className="scatter-graph-panel",
                    ),
                ],
                className="scatter-graph-row",
            ),
            # Kept hidden so existing callbacks can update it without reserving UI space.
            html.Div(
                id="service-legend-container",
                className="service-legend-container",
                style={"display": "none"},
            ),
            # Clone Details
            html.Div(
                [
                    html.Div(
                        id="scatter-click-scroll-dummy",
                        style={"display": "none"},
                    ),
                    html.Div(
                        id="clone-selector-container",
                        style={"marginBottom": "10px"},
                    ),
                    html.Div(
                        id="clone-details-table",
                        children=[
                            html.P(
                                "Click a point on the graph to view clone "
                                "details and code comparison here.",
                                **{"data-i18n": "scatterClickHint"},
                                style={
                                    "color": "var(--text-light)",
                                    "textAlign": "center",
                                    "padding": "40px",
                                },
                            )
                        ],
                    ),
                ],
                style={
                    "padding": "16px",
                    "borderTop": "2px solid var(--border, #ddd)",
                    "backgroundColor": "var(--card-bg, #fff)",
                },
            ),
        ],
        id="scatter-container",
        className="view-panel active",
        style={"padding": "0"},
    )

    # ── Metrics View View (旧 Statistics) ──
    stats_view = html.Div(
        [
            create_stats_metrics_explorer(),
            # Compatibility target for existing scatter/explorer callbacks that
            # still update the legacy summary output.
            html.Div(
                initial_summary,
                id="project-summary-container",
                style={"display": "none"},
            ),
        ],
        id="stats-container",
        className="view-panel",
        style={"padding": "0"},
    )

    # ── Statistics Dashboard View (新規) ──
    statistics_view = html.Div(
        create_statistics_dashboard(),
        id="statistics-container",
        className="view-panel",
        style={"padding": "0"},
    )

    # ── Help Modal ──
    help_modal = _build_help_modal()

    # ── Stores ──
    stores = html.Div(
        [
            dcc.Location(id="url-location", refresh=False),
            dcc.Store(id="file-tree-data-store"),
            dcc.Store(id="selected-file-store"),
            dcc.Store(id="clone-data-store"),
            dcc.Store(id="lang-store", data="en"),
            html.Div(id="i18n-dummy", style={"display": "none"}),
            html.Div(id="colorbar-sync-dummy", style={"display": "none"}),
            # Ghost elements removed - explorer_callbacks now target the visible elements
            # in explorer_sidebar (lines 563, 577, 592, 599)
        ]
    )

    return html.Div(
        className="app-container",
        children=[
            nav_sidebar,
            html.Div(
                className="app-main",
                children=[
                    content_header,
                    html.Div(
                        className="content-body",
                        children=[
                            # List View (drill-down, hidden by default)
                            html.Div(
                                create_list_view_layout(),
                                id="ide-main-container",
                                className="ide-main",
                                style={"display": "none"},
                            ),
                            # Scatter overlay
                            scatter_view,
                            # Metrics View overlay
                            stats_view,
                            # Statistics Dashboard overlay
                            statistics_view,
                        ],
                    ),
                    # help_modal と stores を app-main 内に配置
                    # (app-container は2列GridのためGrid列を乱さないように)
                    help_modal,
                    stores,
                ],
            ),
        ],
    )
