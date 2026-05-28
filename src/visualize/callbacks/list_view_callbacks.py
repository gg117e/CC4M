"""ドリルダウンリストビューのコールバック.

ナビゲーション状態管理 + テーブルレンダリング + フラグメント比較.
"""

from __future__ import annotations

import difflib
import html as html_lib
import logging
import os
import re

import dash
import pandas as pd
from dash import dcc, html, Input, Output, State, ALL, no_update

from pathlib import Path

from ..components.list_view import (
    _FRAG_COLUMNS_DEF,
    _TABLE_STYLE_DATA_CONDITIONAL,
    build_breadcrumb,
    build_detail_panel,
)
from ..utils import get_local_snippet, get_file_content
from modules.util import get_file_type
from ..data_loader.metrics_loader import (
    clear_metrics_cache,
    get_cs_table_df,
    get_file_table_df,
    get_service_table_df,
    load_metrics_dataframes,
)

logger = logging.getLogger(__name__)


def _text_series(series, fill_value=""):
    return series.astype("string").fillna(fill_value).astype(str)


# ---------------------------------------------------------------------------
# カラム定義
# ---------------------------------------------------------------------------


_SERVICE_ALL_COLUMNS: list[dict] = [
    {"id": "service", "name": "Service", "type": "text"},
    {"id": "clone_set_count", "name": "# Clone Sets", "type": "numeric"},
    {"id": "inter_clone_set_count", "name": "# Inter CS", "type": "numeric"},
    {"id": "total_clone_line_count", "name": "Clone LOC", "type": "numeric"},
    {"id": "roc_pct", "name": "ROC (%)", "type": "numeric"},
    {"id": "clone_avg_line_count", "name": "Avg LOC", "type": "numeric"},
    {"id": "clone_file_count", "name": "Clone Files", "type": "numeric"},
    {"id": "comod_count", "name": "Comod Count", "type": "numeric"},
    {"id": "comod_other_service_count", "name": "Related MS", "type": "numeric"},
]

_SERVICE_DEFAULT_VISIBLE = [
    "service", "clone_set_count", "inter_clone_set_count",
    "total_clone_line_count", "roc_pct",
    "comod_count", "comod_other_service_count",
]

_FILE_ALL_COLUMNS: list[dict] = [
    {"id": "file_name", "name": "File", "type": "text"},
    {"id": "service", "name": "Service", "type": "text"},
    {"id": "file_type", "name": "Type", "type": "text"},
    {"id": "sharing_service_count", "name": "Shared MS", "type": "numeric"},
    {"id": "sharing_service_ratio_pct", "name": "Shared MS%", "type": "numeric"},
    {"id": "total_service_count", "name": "Total MS", "type": "numeric"},
    {"id": "cross_service_clone_set_count", "name": "# Shared CS", "type": "numeric"},
    {"id": "cross_cs_ratio_pct", "name": "Shared CS%", "type": "numeric"},
    {"id": "cross_service_line_count", "name": "Inter LOC", "type": "numeric"},
    {"id": "cross_service_comod_count", "name": "Comod", "type": "numeric"},
    {"id": "comod_shared_service_count", "name": "Comod MS", "type": "numeric"},
]

_FILE_DEFAULT_VISIBLE = [
    "file_name", "service", "file_type",
    "sharing_service_count",
    "cross_service_clone_set_count", "cross_cs_ratio_pct",
    "cross_service_comod_count",
]

_CS_ALL_COLUMNS: list[dict] = [
    {"id": "clone_id", "name": "Clone ID", "type": "text"},
    {"id": "service_count", "name": "Service Span", "type": "numeric"},
    {"id": "comod_count", "name": "Comod", "type": "numeric"},
    {"id": "inter_frag_ratio_pct", "name": "Inter%", "type": "numeric"},
    {"id": "cross_service_line_count", "name": "Inter LOC", "type": "numeric"},
    {"id": "comod_frag_ratio_pct", "name": "Comod Frag%", "type": "numeric"},
    {"id": "comod_fragment_count", "name": "Comod Frags", "type": "numeric"},
    {"id": "cross_service_fragment_count", "name": "Inter Frags", "type": "numeric"},
    {"id": "cross_service_fragment_ratio", "name": "Inter Frag Ratio", "type": "numeric"},
    {"id": "cross_service_element_count", "name": "Inter Elements", "type": "numeric"},
    {"id": "cross_service_scale", "name": "Inter Scale", "type": "numeric"},
]

_CS_DEFAULT_VISIBLE = [
    "clone_id", "service_count", "comod_count",
    "inter_frag_ratio_pct", "cross_service_line_count",
]


def _filter_columns(all_cols: list[dict], visible_ids: list[str] | None) -> list[dict]:
    if not visible_ids:
        return list(all_cols)
    visible_set = set(visible_ids)
    # 順序は all_cols のものを維持
    return [c for c in all_cols if c["id"] in visible_set]


def _service_columns(visible_ids: list[str] | None = None) -> list[dict]:
    return _filter_columns(_SERVICE_ALL_COLUMNS, visible_ids or _SERVICE_DEFAULT_VISIBLE)


def _file_columns(
    include_service: bool = True,
    visible_ids: list[str] | None = None,
) -> list[dict]:
    visible = visible_ids or _FILE_DEFAULT_VISIBLE
    if not include_service:
        visible = [v for v in visible if v != "service"]
    return _filter_columns(_FILE_ALL_COLUMNS, visible)


def _cs_columns(visible_ids: list[str] | None = None) -> list[dict]:
    return _filter_columns(_CS_ALL_COLUMNS, visible_ids or _CS_DEFAULT_VISIBLE)


def all_columns_for_origin(origin: str) -> list[dict]:
    """Return the full column catalog for a given origin tab (for UI)."""
    if origin == "ms":
        return list(_SERVICE_ALL_COLUMNS)
    if origin == "file":
        return list(_FILE_ALL_COLUMNS)
    return list(_CS_ALL_COLUMNS)


def default_visible_for_origin(origin: str) -> list[str]:
    if origin == "ms":
        return list(_SERVICE_DEFAULT_VISIBLE)
    if origin == "file":
        return list(_FILE_DEFAULT_VISIBLE)
    return list(_CS_DEFAULT_VISIBLE)


def _file_clone_columns() -> list[dict]:
    """ファイル選択時に表示する関連クローンセット用カラム."""
    return [
        {"id": "clone_id", "name": "Clone ID", "type": "text"},
        {"id": "n_total_fragments", "name": "Frags", "type": "numeric"},
        {"id": "service_count", "name": "Service Span", "type": "numeric"},
        {"id": "comod_count", "name": "Comod", "type": "numeric"},
        {"id": "cross_service_line_count", "name": "Inter LOC", "type": "numeric"},
        {
            "id": "involved_services",
            "name": "Services",
            "type": "text",
            "presentation": "markdown",
        },
    ]


# デフォルトソート定義 (column_id, direction)
_DEFAULT_SORT: dict[str, list[dict]] = {
    "service": [{"column_id": "clone_set_count", "direction": "desc"}],
    "file": [{"column_id": "sharing_service_count", "direction": "desc"}],
    "cs": [{"column_id": "comod_count", "direction": "desc"}],
}


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _parse_project(
    project_value: str | None,
) -> tuple[str | None, str | None, str | None]:
    """project_selector value から (project, commit, language) を取り出す."""
    if not project_value:
        return None, None, None
    try:
        project, commit, language = project_value.split("|||", 2)
        return project, commit, language
    except (ValueError, AttributeError):
        return None, None, None


def _initial_nav() -> dict:
    return {
        "origin": "ms",
        "ms_name": None,
        # 互換維持用. MS Baseでは常に file 扱い.
        "l2_tab": "file",
        "level": 1,
        "detail_id": None,
        "compare_clone_id": None,
        "_last_cell": None,  # 最後に処理した active_cell（二重処理防止）
    }


def _empty_table_outputs() -> tuple:
    """テーブルを空にする出力タプル."""
    detail_hidden = {"display": "none"}
    fc_hidden = {"display": "none"}
    compare_hidden = {"display": "none"}
    table_visible = {
        "flex": "1",
        "minHeight": "0",
        "overflowY": "auto",
    }
    return (
        [],  # columns
        [],  # data
        [],  # sort_by
        0,  # page_current
        [],  # breadcrumb children
        {"flexShrink": "0", "display": "none"},  # l2-subtabs-container style
        [],  # detail-panel children
        detail_hidden,  # detail-section style
        fc_hidden,  # file-clones-container style
        [],  # file-clones-table data
        [],  # file-clones-table columns
        {
            "display": "block",
            "padding": "20px",
            "color": "#888",
            "textAlign": "center",
        },  # no-data-msg
        table_visible,  # table-section style
        compare_hidden,  # frag-compare-section style
    )


def _df_to_records(df: pd.DataFrame, cols: list[dict]) -> list[dict]:
    """列定義に基づいて DataFrame を records リストに変換する."""
    if df is None or df.empty:
        return []
    col_ids = [c["id"] for c in cols]
    existing = [c for c in col_ids if c in df.columns]
    sub = df[existing].copy()
    # 不足列を None で補完
    for c in col_ids:
        if c not in sub.columns:
            sub[c] = None
    # NaN を None に変換（JSON シリアライズ対応）
    records = sub[col_ids].where(pd.notna(sub[col_ids]), None).to_dict("records")
    return records


def _compact_services_markdown(value: object, limit: int = 3) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    services = [token.strip() for token in text.split(",") if token.strip()]
    if len(services) <= limit:
        return ", ".join(html_lib.escape(service) for service in services)

    shown = ", ".join(html_lib.escape(service) for service in services[:limit])
    hidden = "<br>".join(html_lib.escape(service) for service in services[limit:])
    total = len(services)
    remaining = total - limit
    return (
        f"{shown}"
        f"<details class=\"list-services-details\">"
        f"<summary>Show all {total} services (+{remaining})</summary>"
        f"<div class=\"list-services-details-body\">{hidden}</div>"
        f"</details>"
    )


def _compact_involved_services(records: list[dict]) -> list[dict]:
    compacted = []
    for record in records:
        next_record = dict(record)
        if "involved_services" in next_record:
            next_record["involved_services"] = _compact_services_markdown(
                record.get("involved_services")
            )
        compacted.append(next_record)
    return compacted


def _df_to_frag_records(df: pd.DataFrame) -> list[dict]:
    """フラグメント DataFrame を records に変換する.

    表示列 (_FRAG_COLUMNS_DEF) に加えて, コード読み取りに必要な
    ``file_path``, ``start_line``, ``end_line`` を隠しフィールドとして含める.
    """
    if df is None or df.empty:
        return []
    visible_ids = [c["id"] for c in _FRAG_COLUMNS_DEF]
    hidden_ids = ["file_path", "start_line", "end_line"]
    all_ids = visible_ids + [h for h in hidden_ids if h not in visible_ids]
    result = []
    for _, row in df.iterrows():
        rec = {
            col: (None if pd.isna(row[col]) else row[col])
            for col in all_ids
            if col in row
        }
        result.append(rec)
    return result


def _apply_sort(df: pd.DataFrame, sort_by: list[dict]) -> pd.DataFrame:
    """sort_by リストに従って DataFrame をソートする."""
    if df.empty or not sort_by:
        return df
    by = []
    ascending = []
    for s in sort_by:
        col = s.get("column_id")
        if col and col in df.columns:
            by.append(col)
            ascending.append(s.get("direction", "asc") == "asc")
    if by:
        df = df.sort_values(by=by, ascending=ascending, na_position="last")
    return df


# ---------------------------------------------------------------------------
# ドリルダウン / ナビゲーション
# ---------------------------------------------------------------------------


def _drill_down(nav: dict, row: dict) -> dict:
    """行クリックに基づいてナビゲーション状態を更新する."""
    origin = nav.get("origin", "ms")
    level = nav.get("level", 1)

    if origin == "ms":
        if level == 1:
            ms_name = row.get("service", "")
            return {
                **nav,
                "ms_name": ms_name,
                "l2_tab": "file",
                "level": 2,
                "compare_clone_id": None,
                "_last_cell": None,
            }
        elif level == 2:
            detail_id = row.get("file_path") or row.get("clone_id") or ""
            return {
                **nav,
                "detail_id": str(detail_id),
                "level": 3,
                "compare_clone_id": None,
                "_last_cell": None,
            }
        else:  # level >= 3: 別の行を選択 → detail_id だけ更新
            detail_id = row.get("file_path") or row.get("clone_id") or ""
            return {
                **nav,
                "detail_id": str(detail_id),
                "compare_clone_id": None,
                "_last_cell": None,
            }
    else:
        # file / cs origin: level 1 → detail (level 2)、または level 2 で再選択
        detail_id = row.get("file_path") or row.get("clone_id") or ""
        return {
            **nav,
            "detail_id": str(detail_id),
            "level": 2,
            "compare_clone_id": None,
            "_last_cell": None,
        }

    return nav


def _drill_down_to_compare(nav: dict, clone_id: str) -> dict:
    """ファイル詳細のクローン一覧クリック → フラグメント比較レベルへ遷移."""
    return {
        **nav,
        "compare_clone_id": str(clone_id),
        "level": nav.get("level", 1) + 1,
        "_last_cell": None,
    }


def _navigate_back(nav: dict, target: str) -> dict:
    """パンくずクリックに基づいてナビゲーション状態を巻き戻す."""
    if target == "root":
        return {**_initial_nav(), "origin": nav.get("origin", "ms")}
    if target == "ms":
        return {
            **nav,
            "level": 2,
            "detail_id": None,
            "compare_clone_id": None,
            "_last_cell": None,
        }
    if target == "detail":
        # フラグメント比較 → ファイル詳細に戻る
        return {
            **nav,
            "compare_clone_id": None,
            "level": nav.get("level", 2) - 1,
            "_last_cell": None,
        }
    return nav


# ---------------------------------------------------------------------------
# コールバック登録
# ---------------------------------------------------------------------------


def register_list_view_callbacks(app: dash.Dash, app_data: dict) -> None:
    """リストビュー関連のコールバックをすべて登録する."""

    # ── A: ナビゲーション状態更新 ──────────────────────────────────────────

    @app.callback(
        Output("list-nav-store", "data"),
        [
            Input("list-origin-tabs", "active_tab"),
            Input("list-main-table", "active_cell"),
            Input({"type": "list-bc-btn", "index": ALL}, "n_clicks"),
            Input("list-file-clones-table", "active_cell"),
        ],
        [
            State("list-nav-store", "data"),
            State("list-main-table", "data"),
            State("list-main-table", "derived_virtual_data"),
            State("list-file-clones-table", "data"),
            State("list-file-clones-table", "derived_virtual_data"),
        ],
        prevent_initial_call=True,
    )
    def update_nav_store(
        origin_tab: str,
        active_cell: dict | None,
        bc_clicks: list,
        fc_active_cell: dict | None,
        nav: dict,
        table_data: list[dict],
        derived_virtual_data: list[dict] | None,
        fc_data: list[dict] | None,
        fc_virtual_data: list[dict] | None,
    ) -> dict:
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update

        triggered_id = ctx.triggered_id

        # 起点タブ切り替え → Level 1 にリセット
        if triggered_id == "list-origin-tabs":
            return {**_initial_nav(), "origin": origin_tab or "ms"}

        # パンくずクリック
        if isinstance(triggered_id, dict) and triggered_id.get("type") == "list-bc-btn":
            # どのボタンが実際にクリックされたか確認
            triggered_prop = ctx.triggered[0]["prop_id"]
            import json as _json

            try:
                btn_id = _json.loads(triggered_prop.split(".")[0])
            except Exception:
                return no_update
            # n_clicks が 0 なら初期化トリガー → 無視
            if not ctx.triggered[0]["value"]:
                return no_update
            return _navigate_back(nav, btn_id.get("index", "root"))

        # ファイル詳細のクローン一覧クリック → 比較レベルへ遷移
        if triggered_id == "list-file-clones-table":
            if fc_active_cell is None:
                return no_update
            if fc_active_cell.get("column_id") == "involved_services":
                return no_update
            current = fc_virtual_data if fc_virtual_data else fc_data
            if not current:
                return no_update
            row_idx = fc_active_cell.get("row", 0)
            if row_idx >= len(current):
                return no_update
            clone_id = str(current[row_idx].get("clone_id", ""))
            if not clone_id:
                return no_update
            return _drill_down_to_compare(nav, clone_id)

        # 行クリック (DataTable active_cell)
        if triggered_id == "list-main-table":
            if active_cell is None or not table_data:
                return no_update
            # 同じセルの二重処理防止
            last_cell = nav.get("_last_cell")
            if last_cell is not None and last_cell == active_cell:
                return no_update
            row_idx = active_cell.get("row", 0)
            current_data = (
                derived_virtual_data if derived_virtual_data is not None else table_data
            )
            if row_idx >= len(current_data):
                return no_update
            row = current_data[row_idx]
            new_nav = _drill_down(nav, row)
            new_nav["_last_cell"] = active_cell
            return new_nav

        return no_update

    # ── B: テーブル・パンくず・右パネルのレンダリング ────────────────────

    @app.callback(
        [
            Output("list-main-table", "columns"),
            Output("list-main-table", "data"),
            Output("list-main-table", "sort_by"),
            Output("list-main-table", "page_current"),
            Output("list-breadcrumb", "children"),
            Output("list-l2-subtabs-container", "style"),
            Output("list-detail-panel", "children"),
            Output("list-detail-section", "style"),
            Output("list-file-clones-container", "style"),
            Output("list-file-clones-table", "data"),
            Output("list-file-clones-table", "columns"),
            Output("list-no-data-msg", "style"),
            Output("list-table-section", "style"),
            Output("list-frag-compare-section", "style"),
        ],
        [
            Input("list-nav-store", "data"),
            Input("project-selector", "value"),
            Input("list-filetype-filter", "value"),
            Input("list-columns-toggle", "value"),
        ],
        prevent_initial_call=False,
    )
    def render_list_view(
        nav: dict,
        project_value: str | None,
        file_type: str | None,
        visible_columns: list[str] | None,
    ) -> tuple:
        data_hidden = {"display": "none"}
        l2_hidden = {"flexShrink": "0", "display": "none"}
        l2_visible = {
            "flexShrink": "0",
            "display": "block",
            "borderBottom": "1px solid #dee2e6",
        }
        table_visible = {
            "flex": "1",
            "minHeight": "0",
            "overflowY": "auto",
        }
        table_hidden = {"display": "none"}
        detail_hidden = {"display": "none"}
        detail_visible = {
            "display": "flex",
            "flexDirection": "column",
            "flex": "1",
            "minHeight": "0",
            "overflow": "hidden",
        }
        fc_hidden = {"display": "none"}
        fc_visible = {
            "display": "flex",
            "flexDirection": "column",
            "flex": "1",
            "minHeight": "0",
            "overflow": "hidden",
        }
        compare_hidden = {"display": "none"}
        compare_visible = {
            "display": "flex",
            "flexDirection": "column",
            "flex": "1",
            "minHeight": "0",
            "overflow": "hidden",
        }

        if not project_value or not nav:
            return _empty_table_outputs()

        project, commit, language = _parse_project(project_value)
        if not project or not language:
            return _empty_table_outputs()

        # メトリクス読み込み
        try:
            metrics = load_metrics_dataframes(project, language)
        except Exception as exc:
            logger.error("Error loading metrics for %s/%s: %s", project, language, exc)
            return _empty_table_outputs()

        if all(v.empty for k, v in metrics.items() if k != "fragments"):
            return _empty_table_outputs()

        origin = nav.get("origin", "ms")
        level = nav.get("level", 1)
        ms_name = nav.get("ms_name")
        l2_tab = nav.get("l2_tab", "file")
        detail_id = nav.get("detail_id")
        compare_clone_id = nav.get("compare_clone_id")
        ft = file_type or "all"

        bc_children = build_breadcrumb(
            origin, ms_name, level, l2_tab, detail_id, compare_clone_id
        )

        # ── フラグメント比較モード判定 ──────────────────────────────────
        # CS コンテキスト: detail レベルで直接比較
        is_cs_ctx = origin == "cs" and level >= 2 and detail_id
        # compare_clone_id がある or CSコンテキスト → 比較モード
        show_compare = bool(compare_clone_id) or is_cs_ctx

        if show_compare:
            return (
                [],
                [],
                [],
                0,
                bc_children,
                l2_hidden,
                [],
                detail_hidden,
                fc_hidden,
                [],
                [],
                data_hidden,
                table_hidden,
                compare_visible,
            )

        # ── 詳細パネル内容を構築 ────────────────────────────────────────
        detail_content: list = []
        fc_data_out: list = []
        fc_cols: list = []
        show_detail = False
        show_fc = False

        # ファイルコンテキスト判定
        is_file_ctx = (origin == "file" and level >= 2 and detail_id) or (
            origin == "ms" and level >= 3 and detail_id
        )

        if is_file_ctx:
            show_detail = True
            show_fc = True
            detail_content = build_detail_panel(origin, l2_tab, detail_id, metrics)
            fc_data_out, fc_cols = _build_file_clones(metrics, detail_id)

        # ── ファイル詳細: テーブル非表示, 詳細全幅 (MS Level 3) ────────
        if origin == "ms" and level == 3 and detail_id and not show_compare:
            return (
                [],
                [],
                [],
                0,
                bc_children,
                l2_hidden,
                detail_content,
                detail_visible,
                fc_visible if show_fc else fc_hidden,
                fc_data_out,
                fc_cols,
                data_hidden,
                table_hidden,
                compare_hidden,
            )

        # ── ファイル詳細: テーブル非表示 (file/cs origin) ──────────────
        if origin != "ms" and level >= 2 and detail_id and not show_compare:
            return (
                [],
                [],
                [],
                0,
                bc_children,
                l2_hidden,
                detail_content,
                detail_visible,
                fc_visible if show_fc else fc_hidden,
                fc_data_out,
                fc_cols,
                data_hidden,
                table_hidden,
                compare_hidden,
            )

        # 列トグル: 現在の起点に対応するカラム ID のみを残す.
        # 起点切替直後はチェック済み列が他起点のものなので, この起点に属する
        # ID だけ採用. 空ならデフォルト表示.
        all_ids_for_origin = {c["id"] for c in all_columns_for_origin(origin)}
        if visible_columns:
            cur_visible = [c for c in visible_columns if c in all_ids_for_origin]
        else:
            cur_visible = []
        if not cur_visible:
            cur_visible = default_visible_for_origin(origin)

        # ── Level 2: MS → file / cs テーブル (全幅) ────────────────────
        if origin == "ms" and level == 2:
            cols, data, sort_by = _build_level2_ms_table(metrics, ms_name, ft, cur_visible)
            return (
                cols,
                data,
                sort_by,
                0,
                bc_children,
                l2_hidden,
                [],
                detail_hidden,
                fc_hidden,
                [],
                [],
                data_hidden,
                table_visible,
                compare_hidden,
            )

        # ── Level 1: テーブル全幅 ───────────────────────────────────────
        if origin == "ms":
            cols, data, sort_by = _build_service_table(metrics, cur_visible)
        elif origin == "file":
            cols, data, sort_by = _build_file_table(metrics, ms_name=None, file_type=ft, visible_ids=cur_visible)
        else:
            cols, data, sort_by = _build_cs_table(metrics, ms_name=None, file_type=ft, visible_ids=cur_visible)

        return (
            cols,
            data,
            sort_by,
            0,
            bc_children,
            l2_hidden,
            [],
            detail_hidden,
            fc_hidden,
            [],
            [],
            data_hidden,
            table_visible,
            compare_hidden,
        )

    # ── C: project 変更時にメトリクスキャッシュをパージ ────────────────────

    @app.callback(
        Output("list-nav-store", "data", allow_duplicate=True),
        Input("project-selector", "value"),
        State("list-nav-store", "data"),
        prevent_initial_call=True,
    )
    def reset_nav_on_project_change(project_value: str | None, nav: dict) -> dict:
        """プロジェクトが変わったらキャッシュをクリアして Level 1 に戻す."""
        clear_metrics_cache()
        return {**_initial_nav(), "origin": nav.get("origin", "ms")}

    # ── C2: 起点タブ変更時に列トグル選択肢を入れ替え ────────────────────────

    @app.callback(
        [
            Output("list-columns-toggle", "options"),
            Output("list-columns-toggle", "value"),
        ],
        Input("list-origin-tabs", "active_tab"),
        prevent_initial_call=False,
    )
    def update_columns_toggle(origin_tab: str | None):
        origin = origin_tab or "ms"
        all_cols = all_columns_for_origin(origin)
        options = [{"label": c["name"], "value": c["id"]} for c in all_cols]
        return options, default_visible_for_origin(origin)

    # ── D: サマリバー展開/折り畳みトグル ─────────────────────────────────
    app.clientside_callback(
        """
        function(n_clicks, is_open) {
            if (!n_clicks) return [window.dash_clientside.no_update,
                                   window.dash_clientside.no_update];
            var newOpen = !is_open;
            var label = newOpen ? "▲" : "▼";
            return [newOpen, label];
        }
        """,
        [
            Output("list-summary-collapse", "is_open"),
            Output("list-summary-toggle", "children"),
        ],
        Input("list-summary-toggle", "n_clicks"),
        State("list-summary-collapse", "is_open"),
        prevent_initial_call=True,
    )

    # ── E: フラグメント比較セクション更新 ────────────────────────────────
    #   トリガー: nav変更 (比較モードに入った時)

    @app.callback(
        [
            Output("list-compare-summary-panel", "children"),
            Output("list-compare-frag-table", "data"),
            Output("list-compare-frag-table", "columns"),
            Output("list-compare-frag-header", "children"),
            Output("list-frag-selected-store", "data", allow_duplicate=True),
        ],
        [
            Input("list-nav-store", "data"),
            Input("project-selector", "value"),
        ],
        prevent_initial_call=True,
    )
    def populate_comparison(
        nav: dict,
        project_value: str | None,
    ) -> tuple:
        empty = ([], [], _FRAG_COLUMNS_DEF, "Fragments", [])

        if not project_value or not nav:
            return empty

        # 比較モード判定
        compare_clone_id = nav.get("compare_clone_id")
        detail_id = nav.get("detail_id")
        origin = nav.get("origin", "ms")
        l2_tab = "file"
        level = nav.get("level", 1)

        is_cs_ctx = origin == "cs" and level >= 2
        clone_id = compare_clone_id or (
            str(detail_id) if is_cs_ctx and detail_id else None
        )
        if not clone_id:
            return empty

        project, _commit, language = _parse_project(project_value)
        if not project or not language:
            return empty

        try:
            metrics = load_metrics_dataframes(project, language)
        except Exception as exc:
            logger.error("Error loading metrics for comparison: %s", exc)
            return empty

        # CS サマリバー
        summary_content = build_detail_panel(origin, "cs", clone_id, metrics)

        # フラグメント一覧
        frags = metrics.get("fragments", pd.DataFrame())
        if frags.empty or "clone_id" not in frags.columns:
            return (
                summary_content,
                [],
                _FRAG_COLUMNS_DEF,
                f"Clone ID {clone_id} — fragments not available",
                [],
            )

        cs_frags = frags[frags["clone_id"].astype(str) == str(clone_id)].copy()
        if cs_frags.empty:
            return (
                summary_content,
                [],
                _FRAG_COLUMNS_DEF,
                f"Clone ID {clone_id} — no fragments found",
                [],
            )

        cs_frags["file_short"] = cs_frags["file_path"].apply(lambda p: Path(p).name)
        cs_frags["lines"] = (
            cs_frags["start_line"].astype(str) + "–" + cs_frags["end_line"].astype(str)
        )
        cs_frags["service"] = _text_series(cs_frags["service"])

        frag_data = _df_to_frag_records(cs_frags)
        n_svcs = cs_frags["service"].nunique()
        n_frags = len(cs_frags)
        header = f"Clone ID {clone_id} — {n_frags} fragments / {n_svcs} services"

        return (summary_content, frag_data, _FRAG_COLUMNS_DEF, header, [])

    # ── F: フラグメント選択 → FIFO (最大 2) ──────────────────────────────

    @app.callback(
        Output("list-frag-selected-store", "data"),
        Input("list-compare-frag-table", "active_cell"),
        State("list-frag-selected-store", "data"),
        prevent_initial_call=True,
    )
    def handle_frag_selection(
        active_cell: dict | None,
        selected: list | None,
    ) -> list:
        if active_cell is None:
            return no_update

        row_idx = active_cell.get("row", 0)
        current = list(selected) if selected else []

        if row_idx in current:
            # 選択解除
            current.remove(row_idx)
        else:
            current.append(row_idx)
            if len(current) > 2:
                current.pop(0)

        return current

    # ── G: コード比較ビュー描画 ──────────────────────────────────────────

    @app.callback(
        [
            Output("list-compare-code-area", "children"),
            Output("list-compare-frag-table", "style_data_conditional"),
        ],
        Input("list-frag-selected-store", "data"),
        [
            State("list-compare-frag-table", "data"),
            State("project-selector", "value"),
        ],
        prevent_initial_call=True,
    )
    def render_code_comparison(
        selected: list | None,
        frag_data: list[dict] | None,
        project_value: str | None,
    ) -> tuple:
        base_cond = list(_TABLE_STYLE_DATA_CONDITIONAL)
        placeholder = html.Div(
            "フラグメントをクリックしてコードを表示",
            style={
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "height": "100%",
                "color": "#888",
                "fontSize": "14px",
            },
        )

        if not selected or not frag_data or not project_value:
            return [placeholder], base_cond

        project, _commit, _lang = _parse_project(project_value)
        if not project:
            return [placeholder], base_cond

        # 選択行ハイライト用スタイル
        sel_cond = base_cond + [
            {
                "if": {"row_index": idx},
                "backgroundColor": "#dbeafe",
                "border": "1px solid #3b82f6",
            }
            for idx in selected
        ]

        # 有効な行のみ
        valid = [i for i in selected if 0 <= i < len(frag_data)]
        if not valid:
            return [placeholder], sel_cond

        if len(valid) == 1:
            # 単一フラグメント表示
            pane = _build_single_code_pane(frag_data[valid[0]], project)
            return [pane], sel_cond

        # 2 フラグメント比較
        row_a, row_b = frag_data[valid[0]], frag_data[valid[1]]
        view = _build_dual_code_panes(row_a, row_b, project)
        return [view], sel_cond


# ---------------------------------------------------------------------------
# テーブルビルダー
# ---------------------------------------------------------------------------


def _build_service_table(
    metrics: dict[str, pd.DataFrame],
    visible_ids: list[str] | None = None,
) -> tuple[list, list, list]:
    df = get_service_table_df(metrics)
    cols = _service_columns(visible_ids)
    sort_by = _DEFAULT_SORT["service"]
    df = _apply_sort(df, sort_by)
    data = _df_to_records(df, cols)
    return cols, data, sort_by


def _build_file_table(
    metrics: dict[str, pd.DataFrame],
    ms_name: str | None,
    file_type: str,
    visible_ids: list[str] | None = None,
) -> tuple[list, list, list]:
    df = get_file_table_df(metrics, ms_name=ms_name, file_type=file_type)
    include_svc = ms_name is None
    cols = _file_columns(include_service=include_svc, visible_ids=visible_ids)
    sort_by = _DEFAULT_SORT["file"]
    df = _apply_sort(df, sort_by)
    data = _df_to_records(df, cols)
    if "file_path" in df.columns:
        fp_values = df["file_path"].tolist()
        for i, rec in enumerate(data):
            if i < len(fp_values):
                rec["file_path"] = fp_values[i]
    return cols, data, sort_by


def _build_cs_table(
    metrics: dict[str, pd.DataFrame],
    ms_name: str | None,
    file_type: str,
    visible_ids: list[str] | None = None,
) -> tuple[list, list, list]:
    df = get_cs_table_df(metrics, ms_name=ms_name, file_type=file_type)
    cols = _cs_columns(visible_ids)
    sort_by = _DEFAULT_SORT["cs"]
    df = _apply_sort(df, sort_by)
    data = _df_to_records(df, cols)
    return cols, data, sort_by


def _build_level2_ms_table(
    metrics: dict[str, pd.DataFrame],
    ms_name: str | None,
    file_type: str,
    visible_ids: list[str] | None = None,
) -> tuple[list, list, list]:
    return _build_file_table(metrics, ms_name=ms_name, file_type=file_type, visible_ids=visible_ids)


def _build_file_clones(
    metrics: dict[str, pd.DataFrame],
    file_path: str,
) -> tuple[list[dict], list[dict]]:
    """選択されたファイルに属するクローンセットの一覧を構築する."""
    frags = metrics.get("fragments", pd.DataFrame())
    cs_df = metrics.get("clone_set", pd.DataFrame())
    cols = _file_clone_columns()

    if (
        frags.empty
        or "file_path" not in frags.columns
        or "clone_id" not in frags.columns
    ):
        return [], cols

    file_frags = frags[frags["file_path"] == file_path]
    if file_frags.empty:
        return [], cols

    clone_ids = set(file_frags["clone_id"].astype(str).unique())

    if cs_df.empty or "clone_id" not in cs_df.columns:
        # CS メトリクスがない場合, fragments だけで簡易テーブルを構築
        simple_records = []
        for cid in sorted(clone_ids):
            n = len(frags[frags["clone_id"].astype(str) == cid])
            simple_records.append({"clone_id": cid, "n_total_fragments": n})
        return _compact_involved_services(simple_records), cols

    cs_subset = cs_df[cs_df["clone_id"].astype(str).isin(clone_ids)].copy()
    cs_subset["clone_id"] = cs_subset["clone_id"].astype(str)

    # フラグメント総数を追加
    frag_counts = (
        frags.groupby(frags["clone_id"].astype(str))
        .size()
        .reset_index(name="n_total_fragments")
    )
    frag_counts.columns = ["clone_id", "n_total_fragments"]
    cs_subset = cs_subset.merge(frag_counts, on="clone_id", how="left")

    data = _compact_involved_services(_df_to_records(cs_subset, cols))
    return data, cols


# ---------------------------------------------------------------------------
# コード比較ビュー構築ヘルパー
# ---------------------------------------------------------------------------

# ファイル種別スタイル
_TYPE_STYLES = {
    "logic": {"color": "#0366d6", "borderColor": "#0366d6"},
    "test": {"color": "#28a745", "borderColor": "#28a745"},
    "data": {"color": "#d73a49", "borderColor": "#d73a49"},
    "config": {"color": "#6a737d", "borderColor": "#6a737d"},
}


def _frag_file_header(
    file_path: str,
    service: str,
    start_line: int,
    end_line: int,
    compact: bool = False,
    fragment_index: object | None = None,
) -> html.Div:
    """フラグメント用ファイルヘッダー (clone_detail._file_header をベースに簡素化)."""
    ftype = get_file_type(file_path)
    t_style = _TYPE_STYLES.get(ftype, {"color": "#6b7280", "borderColor": "#d1d5db"})
    filename = os.path.basename(file_path) if file_path else "Unknown"
    dir_path = os.path.dirname(file_path) if file_path else ""

    if compact:
        return html.Div(
            [
                html.Div(
                    [
                        html.Span(
                            filename,
                            title=file_path,
                            className="stats-code-file-name",
                        ),
                        (
                            html.Span(
                                f"#{fragment_index}",
                                className="stats-code-frag-index",
                            )
                            if fragment_index not in (None, "")
                            else None
                        ),
                    ],
                    className="stats-code-file-main",
                ),
                html.Div(
                    [
                        html.Span(
                            service,
                            title=f"Service: {service}",
                            className="stats-code-meta-pill",
                        ),
                        html.Span(
                            f"L{start_line}–{end_line}",
                            className="stats-code-line-range",
                        ),
                    ],
                    className="stats-code-file-meta",
                ),
            ],
            className="stats-code-frag-header",
            title=file_path,
        )

    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        ftype.upper(),
                        style={
                            "color": t_style["color"],
                            "fontSize": "10px",
                            "fontWeight": "700",
                            "border": f"1px solid {t_style['borderColor']}",
                            "padding": "2px 6px",
                            "borderRadius": "4px",
                            "marginRight": "12px",
                            "backgroundColor": "#ffffff",
                        },
                    ),
                    html.Span(
                        filename,
                        title=file_path,
                        style={
                            "fontWeight": "600",
                            "fontSize": "13px",
                            "marginRight": "8px",
                            "color": "#111827",
                        },
                    ),
                    html.Span(
                        dir_path,
                        title=file_path,
                        style={
                            "color": "#6b7280",
                            "fontSize": "12px",
                            "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                            "overflow": "hidden",
                            "textOverflow": "ellipsis",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "overflow": "hidden",
                    "whiteSpace": "nowrap",
                    "flex": "1",
                },
            ),
            html.Div(
                [
                    html.Span(
                        [html.B("Svc: ", style={"fontWeight": "600"}), service],
                        style={
                            "fontSize": "12px",
                            "color": "#4b5563",
                            "marginRight": "12px",
                            "backgroundColor": "#e5e7eb",
                            "padding": "2px 8px",
                            "borderRadius": "12px",
                        },
                    ),
                    html.Span(
                        f"L{start_line}–{end_line}",
                        style={"fontSize": "12px", "color": "#4b5563", "fontWeight": "500"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "flexShrink": "0"},
            ),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "padding": "10px 16px",
            "borderBottom": "1px solid #e5e7eb",
            "backgroundColor": "#f9fafb",
            "height": "44px",
            "boxSizing": "border-box",
            "borderTopLeftRadius": "8px",
            "borderTopRightRadius": "8px",
        },
    )


def _diff_line_element(line: str, is_match: bool) -> html.Div:
    """diff 行要素 (clone_detail._diff_pane と同等)."""
    match = re.match(r"([ >])\s*(\d+): (.*)", line)
    if not match:
        match = re.match(r"([ >])\s*(\d+):(.*)", line)
    if not match:
        return html.Div(line, className="diff-line", style={"whiteSpace": "pre"})

    prefix, ln, text = match.groups()
    return html.Div(
        [
            html.Span(
                ln,
                className="line-num",
                **({"data-prefix": prefix} if prefix != " " else {}),
            ),
            html.Span(text),
        ],
        className=f"diff-line {'diff' if is_match else ''}",
    )


def _build_code_pane_content(
    snippet_rows: list,
    code_for_copy: str,
    file_path: str,
    project: str,
    start_line: int,
    end_line: int,
    compact: bool = False,
) -> html.Div:
    """スニペット + 全ソースコード表示 (clone_detail._code_pane と同等)."""
    full_content = get_file_content(project, file_path, start_line, end_line)

    code_snippet = html.Div(
        [
            dcc.Clipboard(
                content=code_for_copy,
                className="copy-button",
                title="Copy snippet",
                style={
                    "position": "absolute",
                    "top": "5px",
                    "right": "5px",
                    "zIndex": "10",
                },
            ),
            html.Div(
                snippet_rows, className="code-pane-content", style={"padding": "15px"}
            ),
        ],
        className="code-pane",
        style={
            "position": "relative",
            "backgroundColor": "#fff",
            "borderBottom": "1px solid #eee",
        },
    )

    full_source = dcc.Markdown(
        full_content,
        className="full-code-markdown",
        # NOTE: dangerously_allow_html はコードスニペット表示用に必要だが,
        # 表示内容はサーバ側で生成したソースコードのみ (ユーザ入力由来ではない)
        # ため XSS リスクは限定的.
        dangerously_allow_html=True,
        style={
            "padding": "15px",
            "fontSize": "12px",
            "lineHeight": "1.5",
            "fontFamily": (
                "'SFMono-Regular', Consolas, 'Liberation Mono',"
                " Menlo, monospace"
            ),
        },
    )

    if compact:
        full_file_section = html.Details(
            [
                html.Summary("Full source"),
                full_source,
            ],
            className="stats-full-source-details",
        )
    else:
        full_file_section = html.Div(
            [
                html.Div(
                    html.Span(
                        "Full Source Code",
                        style={"fontWeight": "600", "color": "#444", "fontSize": "13px"},
                    ),
                    style={
                        "padding": "10px 15px",
                        "background": "#f8f9fa",
                        "borderBottom": "1px solid #e1e4e8",
                    },
                ),
                full_source,
            ],
            style={
                "height": "70vh",
                "overflowY": "auto",
                "display": "block",
            },
        )

    return html.Div(
        [
            html.Div(
                "Snippet" if compact else "Matched Snippet",
                style={
                    "fontSize": "11px",
                    "fontWeight": "bold",
                    "color": "#888",
                    "textTransform": "uppercase",
                    "padding": "10px 15px 5px",
                    "letterSpacing": "0.5px",
                },
            ),
            code_snippet,
            full_file_section,
        ],
        style={
            "backgroundColor": "white",
            "display": "flex",
            "flexDirection": "column",
        },
    )


def _safe_int(val: object, default: int = 0) -> int:
    try:
        if pd.isna(val):
            return default
        return int(val)
    except (ValueError, TypeError):
        return default


def _get_snippet_data(row: dict, project: str) -> tuple[list[str], list[str], str]:
    """フラグメント行データからスニペット行を取得する.

    Returns:
        (raw_lines, pure_code_lines, code_for_copy)
    """
    fp = row.get("file_path", "")
    sl = _safe_int(row.get("start_line"))
    el = _safe_int(row.get("end_line"))
    raw = get_local_snippet(project, fp, sl, el, context=0).splitlines()
    pure = [re.sub(r"^[ >]\s*\d+:\s*", "", line) for line in raw]
    copy_text = "\n".join(pure)
    return raw, pure, copy_text


def _build_single_code_pane(
    row: dict, project: str, compact: bool = False
) -> html.Div:
    """単一フラグメントのコード表示を構築する."""
    fp = row.get("file_path", "")
    sl = _safe_int(row.get("start_line"))
    el = _safe_int(row.get("end_line"))
    svc = row.get("service", "")
    frag_idx = row.get("fragment_index")

    raw_lines, _pure, code_for_copy = _get_snippet_data(row, project)
    snippet_rows = [_diff_line_element(line, False) for line in raw_lines]

    return html.Div(
        [
            _frag_file_header(
                fp,
                svc,
                sl,
                el,
                compact=compact,
                fragment_index=frag_idx,
            ),
            html.Div(
                _build_code_pane_content(
                    snippet_rows,
                    code_for_copy,
                    fp,
                    project,
                    sl,
                    el,
                    compact=compact,
                ),
                style={"flex": "1", "overflow": "auto"},
            ),
        ],
        style={
            "display": "flex",
            "flexDirection": "column",
            "height": "100%",
        },
    )


def _build_dual_code_panes(
    row_a: dict,
    row_b: dict,
    project: str,
    compact: bool = False,
) -> html.Div:
    """2つのフラグメントのdiff比較表示を構築する."""
    raw_a, pure_a, copy_a = _get_snippet_data(row_a, project)
    raw_b, pure_b, copy_b = _get_snippet_data(row_b, project)

    # difflib で一致/差分を判定
    sm = difflib.SequenceMatcher(None, pure_a, pure_b)
    rows_a: list = []
    rows_b: list = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        is_match = tag == "equal"
        for line in raw_a[i1:i2]:
            rows_a.append(_diff_line_element(line, is_match))
        for line in raw_b[j1:j2]:
            rows_b.append(_diff_line_element(line, is_match))

    fp_a = row_a.get("file_path", "")
    sl_a, el_a = _safe_int(row_a.get("start_line")), _safe_int(row_a.get("end_line"))
    svc_a = row_a.get("service", "")
    frag_idx_a = row_a.get("fragment_index")

    fp_b = row_b.get("file_path", "")
    sl_b, el_b = _safe_int(row_b.get("start_line")), _safe_int(row_b.get("end_line"))
    svc_b = row_b.get("service", "")
    frag_idx_b = row_b.get("fragment_index")

    pane_a = html.Div(
        [
            _frag_file_header(
                fp_a,
                svc_a,
                sl_a,
                el_a,
                compact=compact,
                fragment_index=frag_idx_a,
            ),
            html.Div(
                _build_code_pane_content(
                    rows_a,
                    copy_a,
                    fp_a,
                    project,
                    sl_a,
                    el_a,
                    compact=compact,
                ),
                style={"flex": "1", "overflow": "auto" if compact else "hidden"},
            ),
        ],
        className="split-pane",
        style={"flex": "0 0 50%"},
    )

    pane_b = html.Div(
        [
            _frag_file_header(
                fp_b,
                svc_b,
                sl_b,
                el_b,
                compact=compact,
                fragment_index=frag_idx_b,
            ),
            html.Div(
                _build_code_pane_content(
                    rows_b,
                    copy_b,
                    fp_b,
                    project,
                    sl_b,
                    el_b,
                    compact=compact,
                ),
                style={"flex": "1", "overflow": "auto" if compact else "hidden"},
            ),
        ],
        className="split-pane",
        style={"flex": "1"},
    )

    return html.Div(
        [pane_a, html.Div(className="split-gutter", title="Drag to resize"), pane_b],
        className="split-container",
    )
