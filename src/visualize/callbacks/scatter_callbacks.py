"""散布図関連のコールバック."""
import logging
import re

import dash
import pandas as pd
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, no_update, html

from ..data_loader import (
    load_and_process_data,
    get_csv_options_for_project,
    clear_data_cache,
)
from ..plotting import create_scatter_plot
from ..components import (
    build_project_summary,
    build_clone_details_view,
    find_overlapping_clones,
    build_clone_selector,
    build_clone_selector_options,
    calculate_cross_service_metrics,
)
from modules.util import get_file_type
from .filter_callbacks import (
    _apply_code_type_clone_set_filter,
    _apply_comodification_filter,
    _apply_focus_related_service_filter,
    _apply_known_service_filter,
    _apply_service_spread_filter,
)

logger = logging.getLogger(__name__)

CLONE_SET_LINK_META = "clone_set_link"
CLONE_SET_LINK_COLOR = "rgba(0, 255, 255, 0.6)"
CLICKED_POINT_COLOR = "rgba(0, 255, 255, 0.95)"

SCATTER_GRAPH_SIZE_LEVELS = {
    -3: ("420px", "48vh", "620px"),
    -2: ("500px", "58vh", "760px"),
    -1: ("600px", "68vh", "900px"),
    0: ("720px", "78vh", "1000px"),
    1: ("860px", "92vh", "1200px"),
    2: ("1000px", "108vh", "1400px"),
    3: ("1120px", "124vh", "1600px"),
}

# クローンセット紐づけ線機能のON/OFFフラグ
# True: クリック時に同一clone_set_idの点を点線で接続する
# False: 機能を無効化（パフォーマンス向上・再描画防止）
ENABLE_CLONE_SET_LINK_OVERLAY = False


def _resolve_clone_set_column(df: pd.DataFrame) -> str | None:
    """クローンセット識別子として利用可能な列名を返す."""
    for column in ("clone_set_id", "clone_id", "clone_set"):
        if column in df.columns:
            return column
    return None


def _clear_clone_set_link_traces(fig: go.Figure) -> go.Figure:
    """クリック時に追加したクローンセット紐付けトレースを削除する."""
    fig.data = tuple(
        trace for trace in fig.data if getattr(trace, "meta", None) != CLONE_SET_LINK_META
    )
    return fig


def _add_clicked_point_marker(fig: go.Figure, click_x: float, click_y: float) -> None:
    """クリックされた座標に強調マーカーを追加する."""
    fig.add_trace(
        go.Scattergl(
            x=[click_x],
            y=[click_y],
            mode="markers",
            marker={
                "symbol": "star-open",
                "size": 18,
                "color": CLICKED_POINT_COLOR,
                "line": {"width": 2, "color": "rgba(255, 255, 255, 0.95)"},
            },
            hoverinfo="skip",
            showlegend=False,
            meta=CLONE_SET_LINK_META,
            name="clone_set_link_clicked",
        )
    )


def _resolve_clicked_row(click_data: dict, df: pd.DataFrame) -> pd.Series | None:
    """clickData からクリック対象の行を DataFrame から特定する."""
    points = click_data.get("points") if isinstance(click_data, dict) else None
    if not points:
        return None

    point = points[0]
    custom_data = point.get("customdata")
    if isinstance(custom_data, (list, tuple)) and custom_data:
        try:
            row_index = int(custom_data[0])
            if row_index in df.index:
                return df.loc[row_index]
        except (TypeError, ValueError):
            pass

    click_x = point.get("x")
    click_y = point.get("y")
    if click_x is None or click_y is None:
        return None

    if {"display_file_id_x", "display_file_id_y"} <= set(df.columns):
        display_match = df[
            (df["display_file_id_y"] == click_x) & (df["display_file_id_x"] == click_y)
        ]
        if not display_match.empty:
            return display_match.iloc[0]

    overlapping = find_overlapping_clones(df, click_x, click_y)
    if not overlapping:
        return None
    return df.loc[overlapping[0]]


def _find_overlapping_rows_from_click(click_data: dict, df: pd.DataFrame):
    """圧縮表示座標のclickDataから元file_id座標の重なり行を返す."""
    clicked_row = _resolve_clicked_row(click_data, df)
    if clicked_row is None:
        return [], None, None

    original_x = clicked_row.get("file_id_y")
    original_y = clicked_row.get("file_id_x")
    if pd.isna(original_x) or pd.isna(original_y):
        return [], None, None

    overlapping = find_overlapping_clones(df, original_x, original_y)
    if not overlapping and clicked_row.name in df.index:
        overlapping = [clicked_row.name]
    return overlapping, original_x, original_y


def _resolve_selected_row(selected_clone_idx, df: pd.DataFrame) -> pd.Series | None:
    """ドロップダウン選択値から行を特定する."""
    if selected_clone_idx is None:
        return None
    try:
        row_index = int(selected_clone_idx)
    except (TypeError, ValueError):
        return None
    if row_index not in df.index:
        return None
    return df.loc[row_index]


def _build_service_legend(service_legend, selected_service_a=None, selected_service_b=None):
    """番号→サービス名の凡例テーブルを生成する.

    Args:
        service_legend: add_service_number_labels が返すマッピングリスト.

    Returns:
        Dash HTML コンポーネント.
    """
    if not service_legend:
        return html.Div(
            "No services",
            style={"color": "#999", "fontSize": "0.85rem", "padding": "8px"},
        )

    header = html.Div(
        [
            html.I(className="bi bi-list-ol", style={"marginRight": "6px"}),
            html.Span("Services"),
        ],
        className="service-legend-header",
    )

    def _short_service_name(service):
        if not service:
            return ""
        return str(service).split("/")[-1]

    selected_summary = None
    if selected_service_a and selected_service_b:
        selected_summary = html.Div(
            [
                html.I(className="bi bi-funnel-fill", style={"marginRight": "6px"}),
                html.Span(
                    f"Selected: {_short_service_name(selected_service_a)} ↔ "
                    f"{_short_service_name(selected_service_b)}"
                ),
            ],
            className="service-legend-selection",
            title=f"{selected_service_a} ↔ {selected_service_b}",
        )
    elif selected_service_a:
        selected_summary = html.Div(
            [
                html.I(className="bi bi-funnel-fill", style={"marginRight": "6px"}),
                html.Span(f"Selected: {_short_service_name(selected_service_a)}"),
            ],
            className="service-legend-selection",
            title=str(selected_service_a),
        )

    rows = []
    seen_numbers = set()
    selected_services = {s for s in (selected_service_a, selected_service_b) if s}
    for item in service_legend:
        num = item["number"]
        if num in seen_numbers:
            # 同一サービスが複数範囲を持つ場合は最初の1行だけ表示
            continue
        seen_numbers.add(num)
        service_value = item["full_name"]
        row_class = "service-legend-row"
        if service_value in selected_services:
            row_class += " selected"
        rows.append(
            html.Button(
                [
                    html.Span(
                        str(num),
                        className="service-legend-number",
                    ),
                    html.Span(
                        item["service_name"],
                        className="service-legend-name",
                        title=item["full_name"],
                    ),
                ],
                id={"type": "service-legend-row", "service": service_value},
                n_clicks=0,
                type="button",
                className=row_class,
                title=f"Filter by {service_value}",
            )
        )

    content = [header]
    if selected_summary is not None:
        content.append(selected_summary)
    content.extend(rows)
    return html.Div(content, className="service-legend-content")


def register_scatter_callbacks(app, app_data):
    """散布図・クリック・ドロップダウン関連のコールバックを登録する."""

    # --- カラーバーを散布図の実描画領域に同期するクライアントサイドコールバック ---
    # scaleanchor + constrain="domain" によって y 軸 domain が縮むケースで
    # colorbar が散布図より長くなる/横に離れる問題を解消する.
    app.clientside_callback(
        """
        function(figure) {
            function getRoot() { return document.getElementById('scatter-plot'); }
            function getGd() {
                var root = getRoot();
                if (!root) return null;
                if (root._fullLayout) return root;
                return root.querySelector('.js-plotly-plot');
            }

            function syncOnce() {
                var gd = getGd();
                if (!gd || !gd._fullLayout || !gd._fullLayout.yaxis) return;
                if (gd.__cbSyncing) return;
                var fl = gd._fullLayout;
                if (!fl._size || !fl.xaxis || !fl.yaxis) return;
                if (!fl.xaxis._length || !fl.yaxis._length || !fl._size.w || !fl._size.h) return;

                var plotLeftPx = fl._size.l != null ? fl._size.l : (fl.margin && fl.margin.l != null ? fl.margin.l : 0);
                var plotTopPx = fl._size.t != null ? fl._size.t : (fl.margin && fl.margin.t != null ? fl.margin.t : 0);

                // Use pixel length so the colorbar matches the constrained axis exactly.
                var len = Math.max(20, fl.yaxis._length);

                // Use the actual axis centers/edges after scaleanchor constraints.
                var yCenterPx = fl.yaxis._offset + fl.yaxis._length / 2;
                var y = 1 - (yCenterPx - plotTopPx) / fl._size.h;
                if (!isFinite(y)) y = 0.5;
                y = Math.max(0, Math.min(1, y));

                var xRightPx = fl.xaxis._offset + fl.xaxis._length;
                var gapPx = 10;
                var x = (xRightPx - plotLeftPx + gapPx) / fl._size.w;
                if (!isFinite(x)) x = 1.02;
                x = Math.max(0, Math.min(1.2, x));

                var data = gd.data || [];
                var idx = -1;
                for (var i = 0; i < data.length; i++) {
                    if (data[i] && data[i].marker && data[i].marker.showscale) {
                        idx = i; break;
                    }
                }
                if (idx < 0) return;
                var cur = (data[idx].marker.colorbar) || {};
                var curLen = (cur.len == null) ? 1 : cur.len;
                var curY = (cur.y == null) ? 0.5 : cur.y;
                var curX = (cur.x == null) ? 1.02 : cur.x;
                // Hysteresis: only restyle on meaningful changes to avoid feedback loops
                // with Plotly's auto-margin algorithm.
                if (Math.abs(curLen - len) < 2 && Math.abs(curY - y) < 0.01 && Math.abs(curX - x) < 0.01) return;

                gd.__cbSyncing = true;
                Plotly.restyle(gd, {
                    'marker.colorbar.len': len,
                    'marker.colorbar.lenmode': 'pixels',
                    'marker.colorbar.x': x,
                    'marker.colorbar.xanchor': 'left',
                    'marker.colorbar.xref': 'paper',
                    'marker.colorbar.y': y,
                    'marker.colorbar.yanchor': 'middle',
                    'marker.colorbar.yref': 'paper'
                }, [idx]).then(function() {
                    // Release the guard after a short delay so any Plotly
                    // auto-margin reflow settles before the next sync.
                    setTimeout(function() { gd.__cbSyncing = false; }, 150);
                }).catch(function() {
                    setTimeout(function() { gd.__cbSyncing = false; }, 150);
                });
            }
            window.__syncScatterColorbar = syncOnce;

            // Run after figure update — Plotly needs a moment to compute _fullLayout.
            setTimeout(syncOnce, 120);
            setTimeout(syncOnce, 450);

            // One-time setup of external resize triggers. We deliberately do NOT
            // listen to plotly_afterplot/plotly_redraw because those fire after
            // our own restyle and can cause auto-margin redraw oscillation.
            if (!window.__colorbarSyncSetup) {
                window.__colorbarSyncSetup = true;
                var debounce;
                var lastObservedSize = null;
                function getObservedSize(root) {
                    if (!root) return null;
                    var rect = root.getBoundingClientRect();
                    return {
                        width: Math.round(rect.width || 0),
                        height: Math.round(rect.height || 0)
                    };
                }
                function sizeChanged(size) {
                    if (!size || !size.width || !size.height) return false;
                    if (!lastObservedSize) {
                        lastObservedSize = size;
                        return true;
                    }
                    var changed = (
                        Math.abs(lastObservedSize.width - size.width) > 2 ||
                        Math.abs(lastObservedSize.height - size.height) > 2
                    );
                    if (changed) lastObservedSize = size;
                    return changed;
                }
                function trigger(force) {
                    clearTimeout(debounce);
                    debounce = setTimeout(function() {
                        var root = getRoot();
                        if (!force && !sizeChanged(getObservedSize(root))) return;
                        var gd = getGd();
                        if (gd && gd.__cbResizing) return;
                        if (gd && window.Plotly && Plotly.Plots && Plotly.Plots.resize) {
                            try {
                                gd.__cbResizing = true;
                                var p = Plotly.Plots.resize(gd);
                                if (p && typeof p.then === 'function') {
                                    p.then(function() {
                                        gd.__cbResizing = false;
                                        syncOnce();
                                    }).catch(function(){
                                        gd.__cbResizing = false;
                                    });
                                } else {
                                    setTimeout(function() {
                                        gd.__cbResizing = false;
                                        syncOnce();
                                    }, 80);
                                }
                            } catch (e) {
                                gd.__cbResizing = false;
                                setTimeout(syncOnce, 80);
                            }
                        } else {
                            setTimeout(syncOnce, 80);
                        }
                    }, 120);
                }
                window.addEventListener('resize', function() { trigger(true); });
                if (typeof ResizeObserver !== 'undefined') {
                    var attach = function() {
                        var root = getRoot();
                        if (!root) { setTimeout(attach, 500); return; }
                        lastObservedSize = getObservedSize(root);
                        var ro = new ResizeObserver(function() { trigger(false); });
                        ro.observe(root);
                    };
                    attach();
                }
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("colorbar-sync-dummy", "children"),
        Input("scatter-plot", "figure"),
        prevent_initial_call=False,
    )

    # --- 2段階プロジェクト選択: プロジェクト名 → CSVファイル一覧更新 ---
    @app.callback(
        [
            Output("scatter-size-store", "data"),
            Output("scatter-plot", "style"),
            Output("scatter-size-decrease", "className"),
            Output("scatter-size-reset", "className"),
            Output("scatter-size-increase", "className"),
        ],
        [
            Input("scatter-size-decrease", "n_clicks"),
            Input("scatter-size-reset", "n_clicks"),
            Input("scatter-size-increase", "n_clicks"),
        ],
        State("scatter-size-store", "data"),
    )
    def update_scatter_plot_size(_decrease, _reset, _increase, current_level):
        triggered_id = dash.ctx.triggered_id
        try:
            level = int(current_level or 0)
        except (TypeError, ValueError):
            level = 0

        if triggered_id == "scatter-size-decrease":
            level -= 1
        elif triggered_id == "scatter-size-increase":
            level += 1
        elif triggered_id == "scatter-size-reset":
            level = 0

        min_level = min(SCATTER_GRAPH_SIZE_LEVELS)
        max_level = max(SCATTER_GRAPH_SIZE_LEVELS)
        level = max(min_level, min(max_level, level))
        min_height, preferred_height, max_height = SCATTER_GRAPH_SIZE_LEVELS[level]
        height = f"clamp({min_height}, {preferred_height}, {max_height})"
        style = {
            "height": height,
            "--scatter-graph-height": height,
            "--scatter-graph-min-height": min_height,
            "minHeight": min_height,
            "width": "100%",
        }

        def button_class(is_active=False):
            class_name = "filter-preset-btn scatter-size-btn"
            if is_active:
                class_name += " active"
            return class_name

        return (
            level,
            style,
            button_class(level == min_level),
            button_class(level == 0),
            button_class(level == max_level),
        )

    @app.callback(
        [
            Output("project-selector", "options"),
            Output("project-selector", "value"),
            Output("project-selector", "disabled"),
        ],
        Input("project-name-selector", "value"),
        prevent_initial_call=True,
    )
    def update_csv_options_for_project(project_name):
        """プロジェクト名選択時にCSVファイルドロップダウンを更新する."""
        if not project_name:
            return [], None, True

        from ..data_loader import get_csv_options_for_project

        csv_options = get_csv_options_for_project(project_name)
        if not csv_options:
            return [], None, True

        # 最初のオプションをデフォルト選択
        default_value = csv_options[0]["value"]
        return csv_options, default_value, False

    # --- データをロード中であることを示すためのクライアントサイドコールバック ---
    app.clientside_callback(
        """
        function(projectValue) {
            if (!projectValue || projectValue.startsWith('HEADER_')) {
                return window.dash_clientside.no_update;
            }
            return {
                "layout": {
                    "title": "Loading Dataset...",
                    "xaxis": {"visible": false},
                    "yaxis": {"visible": false},
                    "annotations": [{
                        "text": "Loading scattered data... Please wait.",
                        "showarrow": false,
                        "xref": "paper",
                        "yref": "paper",
                        "x": 0.5,
                        "y": 0.5,
                        "font": {"size": 20}
                    }]
                },
                "data": []
            };
        }
        """,
        Output("scatter-plot", "figure", allow_duplicate=True),
        Input("project-selector", "value"),
        prevent_initial_call=True
    )

    @app.callback(
        [
            Output("scatter-plot", "figure", allow_duplicate=True),
            Output("project-summary-container", "children", allow_duplicate=True),
            Output("scatter-stats-header", "children"),
            Output("service-legend-container", "children"),
        ],  # Added Header Output + Legend Output
        # Output('filter-status', 'children') # Removed from Layout
        [
            Input("project-selector", "value"),  # Renamed
            Input("clone-id-filter", "value"),  # Restored as Dropdown
            Input("comodification-filter", "value"),  # Renamed
            Input("comodification-min-filter", "value"),
            Input("code-type-store", "data"),  # Changed from Dropdown to Store
            Input("service-scope-filter", "value"),  # Added service scope filter
            Input("service-spread-filter", "value"),
            Input("service-spread-min-filter", "value"),
            Input("cross-service-filter", "value"),
            Input("service-a-filter", "value"),
            Input("service-b-filter", "value"),
        ],  # Added cross-service filter (Multi-service)
        # Input('scope-filter', 'value')], # Removed
        prevent_initial_call=True,
    )
    def update_graph_and_summary(
        selected_value,
        clone_id_filter,
        comodified_filter_val,
        comodification_min,
        code_type_filter,
        service_scope_filter,
        service_spread_filter,
        service_spread_min,
        cross_service_filter,
        service_a_filter,
        service_b_filter,
    ):
        """選択されたプロジェクトとフィルターに基づいて散布図とサマリーを更新."""
        if not selected_value or selected_value.startswith("HEADER_"):
            return no_update, no_update, no_update, no_update

        scope_filter = "all"
        comodified_filter = comodified_filter_val or "all"

        try:
            project, commit, language = selected_value.split("|||", 2)
        except (ValueError, AttributeError):
            # Handle simple project name case if needed
            return no_update, no_update, no_update, no_update

        # プロジェクト変更時にキャッシュをクリア
        current_project_key = f"{project}_{commit}_{language}"
        cached_project_key = f"{app_data.get('project', '')}_{app_data.get('commit', '')}_{app_data.get('language', '')}"
        graph_signature = (
            selected_value,
            clone_id_filter or "all",
            comodified_filter_val or "all",
            comodification_min,
            code_type_filter or "all",
            service_scope_filter or "all",
            service_spread_filter or "all",
            service_spread_min,
            cross_service_filter or "all",
            service_a_filter or "",
            service_b_filter or "",
        )

        # if (
        #     app_data.get("last_graph_signature") == graph_signature
        #     and current_project_key == cached_project_key
        #     and not app_data.get("df", pd.DataFrame()).empty
        # ):
        #     return no_update, no_update, no_update, no_update

        if current_project_key != cached_project_key:
            logger.info(
                "Project changed from %s to %s, clearing cache...",
                cached_project_key,
                current_project_key,
            )
            from ..data_loader import clear_data_cache

            clear_data_cache()

        df_raw, file_ranges, error = load_and_process_data(project, commit, language)

        if df_raw is None:
            fig = go.Figure().update_layout(title=f"Error: {error}")
            return (
                fig,
                build_project_summary(None, {}, project, commit, language),
                html.Div("Error loading data"),
                html.Div(),
            )

        # フィルタリング処理：no_importsデータ（import文除去済み）をそのまま使用
        df_filtered = _apply_known_service_filter(df_raw)
        df_display = df_filtered.copy()
        filter_status = ""

        # Scope Filter (Unknown)
        if scope_filter == "resolved":
            df_display = df_display[
                (df_display["service_x"] != "unknown")
                & (df_display["service_y"] != "unknown")
            ]
        elif scope_filter == "unknown":
            df_display = df_display[
                (df_display["service_x"] == "unknown")
                | (df_display["service_y"] == "unknown")
            ]
        # 'all' の場合は何もしない

        # Service Scope Filter (Within / Cross) - Implementation
        if service_scope_filter and service_scope_filter != "all":
            # Use 'relation' column if available for better performance (intra/inter)
            if "relation" in df_display.columns:
                if service_scope_filter == "within":
                    df_display = df_display[df_display["relation"] == "intra"]
                    filter_status += " | 🏠 Within Service"
                elif service_scope_filter == "cross":
                    df_display = df_display[df_display["relation"] == "inter"]
                    filter_status += " | 🌐 Cross Services"
            else:
                # Fallback to string comparison
                if service_scope_filter == "within":
                    df_display = df_display[
                        df_display["service_x"] == df_display["service_y"]
                    ]
                    filter_status += " | 🏠 Within Service"
                elif service_scope_filter == "cross":
                    df_display = df_display[
                        df_display["service_x"] != df_display["service_y"]
                    ]
                    filter_status += " | 🌐 Cross Services"

        if service_scope_filter != "within":
            df_display = _apply_service_spread_filter(
                df_display, service_spread_filter, service_spread_min
            )
            if service_spread_filter and service_spread_filter != "all":
                threshold = (
                    service_spread_min
                    if service_spread_filter == "custom"
                    else service_spread_filter
                )
                filter_status += f" | Service spread {threshold}+"

        # Cross Service Filter (Many Services / Specific ID)
        if cross_service_filter and cross_service_filter != "all":
            try:
                # Value matches Clone ID directly (int)
                selected_clone_id = int(str(cross_service_filter))

                if "clone_id" in df_display.columns:
                    df_display = df_display[df_display["clone_id"] == selected_clone_id]
                    filter_status += f" | 🌐 ID: {selected_clone_id}"
            except Exception as e:
                # Fallback or silent fail
                logger.warning("Cross service filtering error: %s", e)

        # Focus/Related サービス選択時はハイライト対象を更新（表示自体は維持）
        if service_a_filter and service_b_filter:
            df_display = _apply_focus_related_service_filter(
                df_display, service_a_filter, service_b_filter
            )
            if service_a_filter == service_b_filter:
                filter_status += f" | 🎯 {service_a_filter}"
            else:
                filter_status += f" | 🎯 {service_a_filter}↔{service_b_filter}"
        elif service_a_filter:
            df_display = _apply_focus_related_service_filter(
                df_display, service_a_filter
            )
            filter_status += f" | 🎯 {service_a_filter}"

        # クローンIDフィルタを適用（TKSフィルタが適用されている場合はその結果を使用）
        if clone_id_filter and clone_id_filter != "all":
            # clone_id_filter e.g. "ID001" or numeric
            try:
                # 文字列から数値を抽出 (Legacy format: clone_123, New: 123)
                digit_str = re.sub(r"\D", "", str(clone_id_filter))
                if digit_str:
                    selected_clone_id = int(digit_str)

                    source_df = df_display
                    df_display = source_df[source_df["clone_id"] == selected_clone_id]

                    # フィルタリングされたデータフレームを使ってメトリクスを計算
                    clone_metrics, _, _ = calculate_cross_service_metrics(df_display)
                    if selected_clone_id in clone_metrics:
                        metrics = clone_metrics[selected_clone_id]

                        filter_status_parts = []
                        filter_status_parts.append(
                            f"🎯 ID {selected_clone_id:03d}: {metrics['pair_count']} pairs"
                        )
                        filter_status = " | ".join(filter_status_parts)
            except Exception as e:
                logger.warning("Clone ID filtering error: %s", e)
                pass

        # 同時修正フィルタ
        if comodified_filter in {
            "none",
            "any",
            "once",
            "repeated",
            "custom",
            "yes",
            "no",
        }:
            df_display = _apply_comodification_filter(
                df_display, comodified_filter, comodification_min
            )
            labels = {
                "none": "Co-modification 0",
                "any": "Co-modification >= 1",
                "once": "Co-modification = 1",
                "repeated": "Co-modification >= 2",
                "custom": f"Co-modification >= {comodification_min}",
            }
            filter_status += f" | {labels.get(comodified_filter, comodified_filter)}"
            comodified_filter = "all"

        if comodified_filter and comodified_filter != "all":
            # 既にフィルタリングされたdf_displayを使用
            source_df = df_display
            if comodified_filter == "true":
                # True, 1, 'True', 'true' などを許容
                df_display = source_df[
                    source_df["comodified"].isin([True, 1, "True", "true"])
                ]
                filter_status += " | 🔄 Co-modified Only"
            elif comodified_filter == "false":
                # False, 0, 'False', 'false' などを許容
                df_display = source_df[
                    source_df["comodified"].isin([False, 0, "False", "false"])
                ]
                filter_status += " | 🔄 Not Co-modified"

        # コードタイプフィルタ
        code_type_source_df = df_display.copy()
        if code_type_filter and code_type_filter != "all":
            # フィルタ適用順序を考慮してソースを選択
            source_df = df_display
            # ... (filtering logic kept same) ...
            if "file_type_x" in source_df.columns:
                if code_type_filter == "data":
                    df_display = source_df[
                        (source_df["file_type_x"] == "data")
                        & (source_df["file_type_y"] == "data")
                    ]

                    filter_status += " | 💾 Data Code"
                elif code_type_filter == "logic":
                    # Logic = (Logic or Config or Data) vs (Logic or Config or Data) MINUS (Data-Data) MINUS (Config-Config)
                    # つまり、Productコード同士のペアで、純粋なDataペアとConfigペアを除いたもの（Logic-Config等を含む）
                    product_types = ["logic", "data", "config"]
                    is_product_x = source_df["file_type_x"].isin(product_types)
                    is_product_y = source_df["file_type_y"].isin(product_types)
                    is_data_pair = (source_df["file_type_x"] == "data") & (
                        source_df["file_type_y"] == "data"
                    )
                    is_config_pair = (source_df["file_type_x"] == "config") & (
                        source_df["file_type_y"] == "config"
                    )

                    df_display = source_df[
                        is_product_x & is_product_y & ~is_data_pair & ~is_config_pair
                    ]
                    filter_status += " | 🧠 Logic Code"
                elif code_type_filter == "test":
                    df_display = source_df[
                        (source_df["file_type_x"] == "test")
                        & (source_df["file_type_y"] == "test")
                    ]
                    filter_status += " | 🧪 Test Code"
                elif code_type_filter == "config":
                    df_display = source_df[
                        (source_df["file_type_x"] == "config")
                        & (source_df["file_type_y"] == "config")
                    ]
                    filter_status += " | ⚙️ Config Code"
                elif code_type_filter == "mixed":
                    # Mixed = Test vs Product (Test vs Non-Test)
                    is_test_x = source_df["file_type_x"] == "test"
                    is_test_y = source_df["file_type_y"] == "test"
                    df_display = source_df[is_test_x != is_test_y]
                    filter_status += " | 🔀 Mixed Code"
            else:
                # 古いデータ形式、または file_type カラムがない場合
                # ファイルパスから判定する (get_file_type を使用)
                df_display = source_df.copy()

                # apply を使う (少し遅いが確実)
                df_display["temp_type_x"] = df_display["file_path_x"].apply(
                    lambda x: get_file_type(str(x))
                )
                df_display["temp_type_y"] = df_display["file_path_y"].apply(
                    lambda x: get_file_type(str(x))
                )

                if code_type_filter == "data":
                    df_display = df_display[
                        (df_display["temp_type_x"] == "data")
                        & (df_display["temp_type_y"] == "data")
                    ]
                    filter_status += " | 💾 Data Code"
                elif code_type_filter == "logic":
                    # Logic = Product-Product (excluding pure Data/Config)
                    product_types = ["logic", "data", "config"]
                    is_product_x = df_display["temp_type_x"].isin(product_types)
                    is_product_y = df_display["temp_type_y"].isin(product_types)
                    is_data_pair = (df_display["temp_type_x"] == "data") & (
                        df_display["temp_type_y"] == "data"
                    )
                    is_config_pair = (df_display["temp_type_x"] == "config") & (
                        df_display["temp_type_y"] == "config"
                    )

                    df_display = df_display[
                        is_product_x & is_product_y & ~is_data_pair & ~is_config_pair
                    ]
                    filter_status += " | 🧠 Logic Code"
                elif code_type_filter == "test":
                    df_display = df_display[
                        (df_display["temp_type_x"] == "test")
                        & (df_display["temp_type_y"] == "test")
                    ]
                    filter_status += " | 🧪 Test Code"
                elif code_type_filter == "config":
                    df_display = df_display[
                        (df_display["temp_type_x"] == "config")
                        & (df_display["temp_type_y"] == "config")
                    ]
                    filter_status += " | ⚙️ Config Code"
                elif code_type_filter == "mixed":
                    # Mixed = Test vs Product
                    is_test_x = df_display["temp_type_x"] == "test"
                    is_test_y = df_display["temp_type_y"] == "test"
                    df_display = df_display[is_test_x != is_test_y]
                    filter_status += " | 🔀 Mixed Code"

                # 一時カラムを削除
                df_display = df_display.drop(columns=["temp_type_x", "temp_type_y"])

        # フィルター状態を表示（軽量な通常ペア数で高速表示）
        if not filter_status:  # フィルタ状態がまだ設定されていない場合
            original_pairs = len(df_raw)
            filtered_pairs = len(df_display)
            filter_parts = []

            # サービススコープフィルタの表示
            if service_scope_filter and service_scope_filter != "all":
                scope_icon = "🏠" if service_scope_filter == "within" else "🌐"
                scope_label = "Within" if service_scope_filter == "within" else "Cross"
                filter_parts.append(f"{scope_icon} {scope_label}")

            # 検出方法フィルタの表示
            if (
                clone_id_filter
                and clone_id_filter != "all"
                and clone_id_filter.startswith("clone_")
            ):
                # クローンIDフィルタの場合
                selected_clone_id = clone_id_filter.replace("clone_", "")
                filter_parts.append(f"🎯 ID {selected_clone_id}")

            # 同時修正フィルタの表示
            if comodified_filter and comodified_filter != "all":
                if comodified_filter == "true":
                    filter_parts.append("🔄 Co-modified")
                elif comodified_filter == "false":
                    filter_parts.append("🔄 Not co-modified")

            # コードタイプフィルタの表示
            if code_type_filter and code_type_filter != "all":
                if code_type_filter == "data":
                    filter_parts.append("💾 Product data")
                elif code_type_filter == "logic":
                    filter_parts.append("🧠 Logic")
                elif code_type_filter == "test":
                    filter_parts.append("🧪 Test code")
                elif code_type_filter == "config":
                    filter_parts.append("⚙️ Config")
                elif code_type_filter == "mixed":
                    filter_parts.append("🔀 Mixed")

            # フィルタ状態のメッセージを組み立て
            if filter_parts:
                filter_status = (
                    " | ".join(filter_parts)
                    + f": {filtered_pairs:,} / {original_pairs:,} pairs"
                )
                if filtered_pairs != original_pairs:
                    reduction_percent = (
                        (original_pairs - filtered_pairs) / original_pairs * 100
                    )
                    filter_status += f" ({reduction_percent:.1f}% reduced)"
            else:
                # フィルタなしの場合
                filter_status = (
                    f"Showing: {filtered_pairs:,} / {original_pairs:,} clone pairs"
                )

        # データをキャッシュ
        if code_type_filter and code_type_filter != "all":
            df_display = _apply_code_type_clone_set_filter(
                code_type_source_df, code_type_filter
            )

        app_data.update(
            {
                "df": df_display,
                "file_ranges": file_ranges,
                "project": project,
                "commit": commit,
                "language": language,
                "last_graph_signature": graph_signature,
            }
        )

        # データ点数が多い場合は静的モード（WebGL + ホバーなし）を有効化
        # 閾値は20,000点とする（ブラウザのパフォーマンスに応じて調整）
        static_mode = len(df_display) > 20000
        if static_mode:
            filter_status += " | ⚠️ Static mode enabled due to large dataset (hover disabled)"

        fig, _ = create_scatter_plot(
            df_display,
            file_ranges,
            project,
            language,
            static_mode=static_mode,
            highlight_service_a=service_a_filter,
            highlight_service_b=service_b_filter,
        )
        summary = build_project_summary(
            df_filtered, file_ranges, project, commit, language
        )

        # Filter details and pair counts are shown in the third row (active-filter-tags).
        stats_header = html.Div()
        # The service list is intentionally hidden; service names now live in hover.
        legend_component = html.Div()

        return fig, summary, stats_header, legend_component

    @app.callback(
        [
            Output("service-a-filter", "value", allow_duplicate=True),
            Output("service-b-filter", "value", allow_duplicate=True),
        ],
        Input({"type": "service-legend-row", "service": ALL}, "n_clicks"),
        [
            State({"type": "service-legend-row", "service": ALL}, "id"),
            State("service-a-filter", "value"),
            State("service-b-filter", "value"),
        ],
        prevent_initial_call=True,
    )
    def update_service_filters_from_legend(n_clicks, row_ids, service_a, service_b):
        """Service legend clicks update the hidden service filter dropdowns."""
        if not any((count or 0) > 0 for count in (n_clicks or [])):
            return no_update, no_update

        triggered_id = dash.ctx.triggered_id
        if not isinstance(triggered_id, dict):
            return no_update, no_update

        clicked_service = triggered_id.get("service")
        if not clicked_service:
            return no_update, no_update

        if clicked_service == service_a:
            return service_b, None
        if clicked_service == service_b:
            return service_a, None
        if not service_a:
            return clicked_service, service_b
        if not service_b:
            return service_a, clicked_service
        return service_a, clicked_service

    @app.callback(
        Output("clone-selector-container", "children"),
        Input("scatter-plot", "clickData"),
        prevent_initial_call=True,
    )
    def update_clone_selector(clickData):
        """散布図のクリックに基づいてクローン選択用DropDownを更新"""
        if not clickData or app_data["df"].empty:
            return no_update

        overlapping_clones, _, _ = _find_overlapping_rows_from_click(
            clickData, app_data["df"]
        )

        if len(overlapping_clones) <= 1:
            # 1個以下の場合はDropDownを表示しない
            return html.Div()

        return build_clone_selector(
            overlapping_clones,
            app_data["df"],
        )

    @app.callback(
        Output("clone-dropdown", "options"),
        Output("clone-dropdown", "value"),
        Input("clone-selector-sort", "value"),
        State("scatter-plot", "clickData"),
        prevent_initial_call=True,
    )
    def update_clone_dropdown_sort(sort_mode, clickData):
        """重なったクローン候補の並び順を変更する."""
        if not clickData or app_data["df"].empty:
            return no_update, no_update

        overlapping_clones, _, _ = _find_overlapping_rows_from_click(
            clickData, app_data["df"]
        )
        if len(overlapping_clones) <= 1:
            return [], None

        options, value = build_clone_selector_options(
            overlapping_clones,
            app_data["df"],
            sort_mode or "line_count",
        )
        return options, value

    @app.callback(
        Output("scatter-plot", "figure", allow_duplicate=True),
        Input("scatter-plot", "clickData"),
        Input("clone-dropdown", "value"),
        State("scatter-plot", "figure"),
        prevent_initial_call=True,
    )
    def update_clone_set_link_overlay(clickData, selected_clone_idx, figure_state):
        """クリックされた点へ選択マーカーを表示し, 必要時にリンク線を重ねる.

        Note:
            この機能は ENABLE_CLONE_SET_LINK_OVERLAY フラグで無効化できる.
            False の場合はサーバー側の figure 更新を行わない.
        """
        # 既定ではクライアント側の selected スタイルで印を付けるため,
        # サーバー側で figure 全体を再送せずに高速化する.
        if not ENABLE_CLONE_SET_LINK_OVERLAY:
            return no_update

        if not figure_state:
            return no_update

        fig = _clear_clone_set_link_traces(go.Figure(figure_state))

        if app_data["df"].empty:
            return fig

        triggered_id = dash.ctx.triggered_id
        if triggered_id == "clone-dropdown":
            clicked_row = _resolve_selected_row(selected_clone_idx, app_data["df"])
            if clicked_row is None:
                clicked_row = _resolve_clicked_row(clickData, app_data["df"])
        else:
            clicked_row = _resolve_clicked_row(clickData, app_data["df"])

        if clicked_row is None:
            return fig

        clone_set_column = _resolve_clone_set_column(app_data["df"])
        if clone_set_column is None:
            return fig

        clone_id = clicked_row.get(clone_set_column)
        click_x = clicked_row.get("display_file_id_y", clicked_row.get("file_id_y"))
        click_y = clicked_row.get("display_file_id_x", clicked_row.get("file_id_x"))
        if pd.isna(clone_id) or pd.isna(click_x) or pd.isna(click_y):
            return fig

        _add_clicked_point_marker(fig, click_x, click_y)

        same_clone_rows = app_data["df"][app_data["df"][clone_set_column] == clone_id]
        if same_clone_rows.empty:
            return fig

        line_x: list[float | int | None] = []
        line_y: list[float | int | None] = []
        for _, row in same_clone_rows.iterrows():
            target_x = row.get("display_file_id_y", row.get("file_id_y"))
            target_y = row.get("display_file_id_x", row.get("file_id_x"))
            if pd.isna(target_x) or pd.isna(target_y):
                continue
            if target_x == click_x and target_y == click_y:
                continue
            line_x.extend([click_x, target_x, None])
            line_y.extend([click_y, target_y, None])

        if line_x:
            fig.add_trace(
                go.Scattergl(
                    x=line_x,
                    y=line_y,
                    mode="lines",
                    line={"color": CLONE_SET_LINK_COLOR, "width": 2, "dash": "dot"},
                    hoverinfo="skip",
                    showlegend=False,
                    meta=CLONE_SET_LINK_META,
                    name="clone_set_link_lines",
                )
            )

        return fig

    @app.callback(
        Output("clone-details-table", "children"),
        Input("scatter-plot", "clickData"),
        prevent_initial_call=True,
    )
    def update_details_from_plot(clickData):
        """散布図のクリックに基づいてクローン詳細テーブルを更新"""
        if not clickData or app_data["df"].empty:
            return no_update

        overlapping_clones, click_x, click_y = _find_overlapping_rows_from_click(
            clickData, app_data["df"]
        )

        if overlapping_clones:
            # 最初のクローンを表示
            row = app_data["df"].loc[overlapping_clones[0]]

            # 現在選択されているクローン情報をapp_dataに保存
            app_data["current_clone"] = {
                "index": overlapping_clones[0],
                "clone_id": row.get("clone_id", ""),
                "file_id_x": row.get("file_id_x", ""),
                "file_id_y": row.get("file_id_y", ""),
                "file_path_x": row.get("file_path_x", ""),
                "file_path_y": row.get("file_path_y", ""),
                "start_line_x": row.get("start_line_x", ""),
                "end_line_x": row.get("end_line_x", ""),
                "start_line_y": row.get("start_line_y", ""),
                "end_line_y": row.get("end_line_y", ""),
                "click_x": click_x,
                "click_y": click_y,
            }

            return build_clone_details_view(
                row, app_data["project"], app_data["df"], app_data["file_ranges"]
            )

        if click_x is None or click_y is None:
            return html.P("No clone found at the clicked location.")
        return html.P(f"No clone found at coordinates ({click_x}, {click_y}).")

    app.clientside_callback(
        """
        function(clickData) {
            if (!clickData || !clickData.points || !clickData.points.length) {
                return window.dash_clientside.no_update;
            }

            function scrollToCloneDetails() {
                var selector = document.getElementById('clone-selector-container');
                var details = document.getElementById('clone-details-table');
                var target = (
                    selector && selector.children && selector.children.length
                ) ? selector : details;
                if (!target) return;
                target.scrollIntoView({behavior: 'smooth', block: 'start'});
            }

            // Wait for the server-side details callback to replace the content.
            setTimeout(scrollToCloneDetails, 180);
            setTimeout(scrollToCloneDetails, 420);
            return '';
        }
        """,
        Output("scatter-click-scroll-dummy", "children"),
        Input("scatter-plot", "clickData"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("clone-details-table", "children", allow_duplicate=True),
        Input("clone-dropdown", "value"),
        prevent_initial_call=True,
    )
    def update_details_from_dropdown(selected_clone_idx):
        """ドロップダウン選択に基づいてクローン詳細テーブルを更新"""
        if selected_clone_idx is None or app_data["df"].empty:
            return no_update

        try:
            if selected_clone_idx in app_data["df"].index:
                row = app_data["df"].loc[selected_clone_idx]

                # 現在選択されているクローン情報をapp_dataに保存
                app_data["current_clone"] = {
                    "index": selected_clone_idx,
                    "clone_id": row.get("clone_id", ""),
                    "file_id_x": row.get("file_id_x", ""),
                    "file_id_y": row.get("file_id_y", ""),
                    "file_path_x": row.get("file_path_x", ""),
                    "file_path_y": row.get("file_path_y", ""),
                    "start_line_x": row.get("start_line_x", ""),
                    "end_line_x": row.get("end_line_x", ""),
                    "start_line_y": row.get("start_line_y", ""),
                    "end_line_y": row.get("end_line_y", ""),
                    "click_x": row.get("file_id_y", ""),  # 座標系注意
                    "click_y": row.get("file_id_x", ""),
                }

                return build_clone_details_view(
                    row, app_data["project"], app_data["df"], app_data["file_ranges"]
                )
        except Exception:
            # ドロップダウンが存在しない場合やエラーの場合
            pass

        return no_update
