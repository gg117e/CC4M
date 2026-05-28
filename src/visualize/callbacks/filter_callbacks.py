"""フィルタリング関連のコールバック."""

import logging
import json

import dash
import pandas as pd
from dash import Input, Output, State, ALL, no_update, html

from ..data_loader import load_and_process_data
from ..components import generate_cross_service_filter_options
from modules.util import get_file_type

logger = logging.getLogger(__name__)

UNKNOWN_SERVICE_VALUES = {"", "unknown", "nan", "none", "null", "unresolved"}


def _text_series(series, fill_value=""):
    return series.astype("string").fillna(fill_value).astype(str)


CODE_TYPE_BUTTON_STYLE = {
    "padding": "0 12px",
    "fontSize": "0.78rem",
    "border": "1px solid var(--border)",
    "borderRadius": "6px",
    "background": "var(--bg)",
    "color": "var(--text-light)",
    "cursor": "pointer",
    "minHeight": "34px",
    "lineHeight": "1.15",
    "boxShadow": "none",
    "transition": "all 0.15s ease",
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "center",
    "marginRight": "4px",
}

CODE_TYPE_BUTTON_ACTIVE_STYLE = {
    **CODE_TYPE_BUTTON_STYLE,
    "background": "rgba(245, 166, 35, 0.16)",
    "color": "#8a5600",
    "border": "1px solid var(--primary)",
    "fontWeight": "600",
    "boxShadow": "inset 0 1px 1px rgba(0, 0, 0, 0.05)",
}


def _is_known_service_value(value):
    normalized = "" if value is None else str(value).strip().lower()
    return normalized not in UNKNOWN_SERVICE_VALUES


def _apply_known_service_filter(df):
    """Keep only pair rows whose X and Y services are both resolved."""
    if df is None or df.empty:
        return df
    if "service_x" not in df.columns or "service_y" not in df.columns:
        return df

    service_x = _text_series(df["service_x"]).str.strip().str.lower()
    service_y = _text_series(df["service_y"]).str.strip().str.lower()
    known_mask = (~service_x.isin(UNKNOWN_SERVICE_VALUES)) & (
        ~service_y.isin(UNKNOWN_SERVICE_VALUES)
    )
    return df[known_mask]


def _normalize_comodified_filter(comodified_val):
    if comodified_val in ("yes", "true", "1"):
        return "true"
    if comodified_val in ("no", "false", "0"):
        return "false"
    if comodified_val in ("any", "none", "once", "repeated", "custom"):
        return comodified_val
    return "all"


def _co_modification_count_series(df):
    if df is None or df.empty:
        return pd.Series(dtype="int64")
    for column in ("coModificationCount", "comodification_count", "comodified_count"):
        if column in df.columns:
            return pd.to_numeric(df[column], errors="coerce").fillna(0).astype(int)
    if "comodified" in df.columns:
        return df["comodified"].isin([True, 1, "1", "True", "true"]).astype(int)
    return pd.Series(0, index=df.index, dtype="int64")


def _normalize_custom_number(value, minimum, default=None):
    try:
        if value is None or value == "":
            return default
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < minimum:
        return default
    return number


def _apply_comodification_filter(df, comodified_val="all", custom_min=None):
    if df is None or df.empty:
        return df

    mode = _normalize_comodified_filter(comodified_val)
    if mode == "all":
        return df

    counts = _co_modification_count_series(df)
    if mode in ("true", "any"):
        return df[counts >= 1]
    if mode in ("false", "none"):
        return df[counts == 0]
    if mode == "once":
        return df[counts == 1]
    if mode == "repeated":
        return df[counts >= 2]
    if mode == "custom":
        threshold = _normalize_custom_number(custom_min, 0, None)
        if threshold is None:
            return df
        return df[counts >= threshold]
    return df


def _clone_service_count_series(df):
    if (
        df is None
        or df.empty
        or "clone_id" not in df.columns
        or "service_x" not in df.columns
        or "service_y" not in df.columns
    ):
        return pd.Series(dtype="int64")
    services_df = pd.concat(
        [
            df[["clone_id", "service_x"]].rename(columns={"service_x": "service"}),
            df[["clone_id", "service_y"]].rename(columns={"service_y": "service"}),
        ],
        ignore_index=True,
    )
    services_df["service"] = services_df["service"].astype(str)
    services_df = services_df[services_df["service"].map(_is_known_service_value)]
    return services_df.groupby("clone_id")["service"].nunique()


def _apply_service_spread_filter(df, spread_filter="all", custom_min=None):
    if df is None or df.empty or spread_filter in (None, "all"):
        return df
    service_counts = _clone_service_count_series(df)
    if service_counts.empty:
        return df.iloc[0:0]

    if spread_filter == "custom":
        threshold = _normalize_custom_number(custom_min, 1, None)
    else:
        threshold = _normalize_custom_number(spread_filter, 1, None)
    if threshold is None:
        return df
    target_ids = set(service_counts[service_counts >= threshold].index)
    return df[df["clone_id"].isin(target_ids)]


def _resolve_method_column(df):
    method_column = "detection_method" if "detection_method" in df.columns else None
    if not method_column and "clone_type" in df.columns:
        method_column = "clone_type"
    return method_column


def _apply_common_pair_filters(
    df,
    detection_method=None,
    comodified_val="all",
    service_scope="all",
    code_type_filter="all",
    cross_service=None,
    service_spread="all",
    comodification_min=None,
    service_spread_min=None,
):
    """散布図表示と整合する共通のペア単位フィルタを適用する."""
    if df is None or df.empty:
        return df

    df_filtered = _apply_known_service_filter(df)
    method_column = _resolve_method_column(df_filtered)

    if detection_method and detection_method != "all" and method_column:
        col_str = df_filtered[method_column].astype(str).str.lower()
        if detection_method == "import":
            df_filtered = df_filtered[col_str.isin(["import", "no-import"])]
        else:
            df_filtered = df_filtered[col_str == detection_method.lower()]

    df_filtered = _apply_comodification_filter(
        df_filtered, comodified_val, comodification_min
    )

    if service_scope and service_scope != "all":
        if "relation" in df_filtered.columns:
            if service_scope == "within":
                df_filtered = df_filtered[df_filtered["relation"] == "intra"]
            elif service_scope == "cross":
                df_filtered = df_filtered[df_filtered["relation"] == "inter"]
        else:
            if service_scope == "within":
                df_filtered = df_filtered[
                    df_filtered["service_x"] == df_filtered["service_y"]
                ]
            elif service_scope == "cross":
                df_filtered = df_filtered[
                    df_filtered["service_x"] != df_filtered["service_y"]
                ]

    if cross_service and cross_service != "all" and "clone_id" in df_filtered.columns:
        try:
            selected_clone_id = int(str(cross_service))
            df_filtered = df_filtered[df_filtered["clone_id"] == selected_clone_id]
        except Exception:
            pass

    if service_scope != "within":
        df_filtered = _apply_service_spread_filter(
            df_filtered, service_spread, service_spread_min
        )

    if code_type_filter and code_type_filter != "all":
        df_filtered = _apply_code_type_clone_set_filter(df_filtered, code_type_filter)

    return df_filtered


def _apply_clone_id_filter(df, clone_id_filter):
    """Clone IDドロップダウン値でペアを絞り込む."""
    if (
        df is None
        or df.empty
        or not clone_id_filter
        or clone_id_filter == "all"
        or "clone_id" not in df.columns
    ):
        return df

    try:
        digit_str = "".join(ch for ch in str(clone_id_filter) if ch.isdigit())
        if not digit_str:
            return df
        selected_clone_id = int(digit_str)
    except (TypeError, ValueError):
        return df

    return df[df["clone_id"] == selected_clone_id]


def _apply_focus_related_service_filter(df, focus_service=None, related_service=None):
    """Filter pair rows by selected focus/related services for UI-side aggregations."""
    if df is None or df.empty or not focus_service:
        return df

    if "service_x" not in df.columns or "service_y" not in df.columns:
        return df

    if related_service:
        if focus_service == related_service:
            return df[
                (df["service_x"] == focus_service) & (df["service_y"] == focus_service)
            ]

        forward = (df["service_x"] == focus_service) & (
            df["service_y"] == related_service
        )
        reverse = (df["service_x"] == related_service) & (
            df["service_y"] == focus_service
        )
        return df[forward | reverse]

    return df[(df["service_x"] == focus_service) | (df["service_y"] == focus_service)]


def _resolve_file_type_series(df):
    if "file_type_x" in df.columns:
        return df["file_type_x"].astype(str), df["file_type_y"].astype(str)
    return (
        df["file_path_x"].apply(lambda x: get_file_type(str(x))).astype(str),
        df["file_path_y"].apply(lambda x: get_file_type(str(x))).astype(str),
    )


def _classify_clone_sets(df):
    classifications = {}
    if df is None or df.empty or "clone_id" not in df.columns:
        return classifications

    series_x, series_y = _resolve_file_type_series(df)
    typed_df = df.assign(_type_x=series_x, _type_y=series_y)
    product_types = {"logic", "data", "config"}

    for clone_id, group in typed_df.groupby("clone_id"):
        all_types = set(group["_type_x"]) | set(group["_type_y"])
        all_types = {t for t in all_types if t and t != "nan"}

        has_test = "test" in all_types
        has_non_test = len(all_types - {"test"}) > 0

        if has_test and has_non_test:
            classifications[clone_id] = "mixed"
        elif all_types == {"test"}:
            classifications[clone_id] = "test"
        elif all_types == {"data"}:
            classifications[clone_id] = "data"
        elif all_types == {"config"}:
            classifications[clone_id] = "config"
        elif all_types and all_types.issubset(product_types):
            classifications[clone_id] = "logic"
        else:
            classifications[clone_id] = "mixed"

    return classifications


def _apply_code_type_clone_set_filter(df, code_type_filter):
    if (
        df is None
        or df.empty
        or not code_type_filter
        or code_type_filter == "all"
        or "clone_id" not in df.columns
    ):
        return df

    classifications = _classify_clone_sets(df)
    target_ids = {
        clone_id
        for clone_id, clone_type in classifications.items()
        if clone_type == code_type_filter
    }
    if not target_ids:
        return df.iloc[0:0]
    return df[df["clone_id"].isin(target_ids)]


def _calculate_code_type_counts(df):
    counts = {
        "all": 0,
        "logic": 0,
        "data": 0,
        "test": 0,
        "config": 0,
        "mixed": 0,
    }

    if df is None or df.empty:
        return counts

    classifications = _classify_clone_sets(df)
    counts["all"] = len(classifications)
    for clone_type in classifications.values():
        counts[clone_type] = counts.get(clone_type, 0) + 1

    return counts


def _calculate_code_type_pair_counts(df):
    counts = {
        "all": 0,
        "logic": 0,
        "data": 0,
        "test": 0,
        "config": 0,
        "mixed": 0,
    }

    if df is None or df.empty:
        return counts

    classifications = _classify_clone_sets(df)
    counts["all"] = len(df)
    for clone_id, clone_type in classifications.items():
        counts[clone_type] += int((df["clone_id"] == clone_id).sum())

    return counts


def _normalize_code_type_selection(active_code_type, counts):
    selected = active_code_type or "all"
    if selected == "all":
        return "all"
    if counts.get(selected, 0) > 0:
        return selected
    return "all"


def create_code_type_button(label, count, value, active_value):
    isActive = value == active_value
    pair_count = int(count.get("pairs", 0)) if isinstance(count, dict) else int(count)
    style = (
        CODE_TYPE_BUTTON_ACTIVE_STYLE.copy()
        if isActive
        else {**CODE_TYPE_BUTTON_STYLE, "fontWeight": "500"}
    )
    style["opacity"] = "1.0" if isActive or pair_count > 0 else "0.45"

    btn_label = f"{label} ({pair_count})"

    return html.Button(
        btn_label,
        id={"type": "code-type-btn", "index": value},
        n_clicks=0,
        className=f"filter-preset-btn code-type-btn{' active' if isActive else ''}",
        style=style,
    )


def _build_code_type_buttons(active_code_type="all", counts=None, pair_counts=None):
    """コードタイプボタン群を組み立てる."""
    default_counts = {
        "all": 0,
        "logic": 0,
        "data": 0,
        "test": 0,
        "config": 0,
        "mixed": 0,
    }
    resolved_counts = counts or default_counts
    resolved_pair_counts = pair_counts or default_counts
    normalized_active = _normalize_code_type_selection(
        active_code_type,
        resolved_counts,
    )

    # Order: All, Logic, Data, Mixed, Test, Config
    order = ["all", "logic", "data", "mixed", "test", "config"]
    buttons = []
    for type_key in order:
        buttons.append(
            create_code_type_button(
                type_key.capitalize(),
                {
                    "sets": resolved_counts.get(type_key, 0),
                    "pairs": resolved_pair_counts.get(type_key, 0),
                },
                type_key,
                normalized_active,
            )
        )
    return buttons


def register_filter_callbacks(app, app_data):
    """フィルタリング（コードタイプ・クロスサービス）関連のコールバックを登録する."""

    @app.callback(
        [
            Output("comodification-filter", "value"),
            Output("service-scope-filter", "value"),
            Output("code-type-store", "data", allow_duplicate=True),
            Output("clone-id-filter", "value"),
            Output("cross-service-filter", "value"),
            Output("service-spread-filter", "value"),
            Output("comodification-min-filter", "value"),
            Output("service-spread-min-filter", "value"),
            Output("service-a-filter", "value", allow_duplicate=True),
            Output("service-b-filter", "value", allow_duplicate=True),
            Output("btn-comod-all", "className", allow_duplicate=True),
            Output("btn-comod-0", "className", allow_duplicate=True),
            Output("btn-comod-1", "className", allow_duplicate=True),
            Output("comod-input-wrapper", "className", allow_duplicate=True),
            Output("comod-draft-input", "value", allow_duplicate=True),
            Output("btn-spread-all", "className", allow_duplicate=True),
            Output("btn-spread-2", "className", allow_duplicate=True),
            Output("spread-input-wrapper", "className", allow_duplicate=True),
            Output("spread-draft-input", "value", allow_duplicate=True),
        ],
        Input("clear-filters-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_all_filters(n_clicks):
        """Clear All ボタンが押されたとき、すべてのフィルターを初期値にリセットする"""
        if n_clicks and n_clicks > 0:
            btn_active = "filter-preset-btn active"
            btn_base = "filter-preset-btn"
            wrap_base = "custom-input-wrapper"
            return (
                "all",
                "all",
                "all",
                "all",
                "all",
                "all",
                0,
                1,
                None,
                None,
                btn_active,
                btn_base,
                btn_base,
                wrap_base,
                None,
                btn_active,
                btn_base,
                wrap_base,
                None,
            )
        return dash.no_update

    @app.callback(
        [
            Output("service-a-filter", "options"),
            Output("service-b-filter", "options"),
            Output("service-b-filter", "value"),
        ],
        [
            Input("project-selector", "value"),
            Input("comodification-filter", "value"),
            Input("comodification-min-filter", "value"),
            Input("service-scope-filter", "value"),
            Input("cross-service-filter", "value"),
            Input("service-spread-filter", "value"),
            Input("service-spread-min-filter", "value"),
            Input("code-type-store", "data"),
            Input("service-a-filter", "value"),
        ],
        [State("service-b-filter", "value")],
    )
    def update_service_filter_options(
        project_value,
        comodified_val,
        comodification_min,
        service_scope,
        cross_service,
        service_spread,
        service_spread_min,
        code_type_filter,
        focus_service,
        current_related_service,
    ):
        """サービス候補を更新し、Focus選択後はRelated候補を共有クローン先に限定する."""
        if not project_value or "|||" not in project_value:
            return [], [], None

        try:
            project, commit, language = project_value.split("|||", 2)
            df, _, _ = load_and_process_data(project, commit, language)
        except Exception as e:
            logger.warning("Service filter options load error: %s", e)
            return [], [], None

        if df is None or df.empty:
            return [], [], None

        # 候補サービス集合（プロジェクト内の全サービス）
        services = set()
        if "service_x" in df.columns:
            services.update(
                s
                for s in df["service_x"].dropna().astype(str).unique().tolist()
                if _is_known_service_value(s)
            )
        if "service_y" in df.columns:
            services.update(
                s
                for s in df["service_y"].dropna().astype(str).unique().tolist()
                if _is_known_service_value(s)
            )

        # 件数算出用に、散布図と同じペア単位フィルタを適用する（A/B 自体は未適用）
        df_filtered = _apply_common_pair_filters(
            df,
            detection_method="all",
            comodified_val=comodified_val,
            service_scope=service_scope,
            code_type_filter=code_type_filter,
            cross_service=cross_service,
            service_spread=service_spread,
            comodification_min=comodification_min,
            service_spread_min=service_spread_min,
        )

        service_clone_counts = {}
        service_pair_counts = {}
        if not df_filtered.empty and "clone_id" in df_filtered.columns:
            for svc in services:
                svc_mask = (df_filtered["service_x"] == svc) | (
                    df_filtered["service_y"] == svc
                )
                count = df_filtered.loc[svc_mask, "clone_id"].nunique()
                service_clone_counts[svc] = int(count)
                service_pair_counts[svc] = int(svc_mask.sum())
        else:
            service_clone_counts = {svc: 0 for svc in services}
            service_pair_counts = {svc: 0 for svc in services}

        # clone_id -> services 集合を作り、サービス間の共有クローン件数を計算
        shared_counts = {svc: {other: 0 for other in services} for svc in services}
        shared_pair_counts = {svc: {other: 0 for other in services} for svc in services}
        if not df_filtered.empty and "clone_id" in df_filtered.columns:
            for _, group in df_filtered.groupby("clone_id"):
                svc_set = set(
                    s
                    for s in pd.concat([group["service_x"], group["service_y"]])
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                    if _is_known_service_value(s)
                )
                if not svc_set:
                    continue
                for s1 in svc_set:
                    for s2 in svc_set:
                        shared_counts[s1][s2] += 1

            for s1 in services:
                for s2 in services:
                    if s1 == s2:
                        mask = (df_filtered["service_x"] == s1) & (
                            df_filtered["service_y"] == s1
                        )
                    else:
                        mask = (
                            (df_filtered["service_x"] == s1)
                            & (df_filtered["service_y"] == s2)
                        ) | (
                            (df_filtered["service_x"] == s2)
                            & (df_filtered["service_y"] == s1)
                        )
                    shared_pair_counts[s1][s2] = int(mask.sum())

        def _build_options(count_map, pair_count_map):
            opts = []
            ordered_services = sorted(
                services,
                key=lambda svc: (
                    -int(count_map.get(svc, 0)),
                    -int(pair_count_map.get(svc, 0)),
                    str(svc),
                ),
            )
            for svc in ordered_services:
                cnt = int(count_map.get(svc, 0))
                pair_cnt = int(pair_count_map.get(svc, 0))
                opts.append(
                    {
                        "label": f"{svc} ({cnt} sets / {pair_cnt} pairs)",
                        "value": svc,
                        "disabled": cnt == 0,
                    }
                )
            return opts

        # Focus サービス候補: 各サービスの総クローンセット件数
        options_a = _build_options(service_clone_counts, service_pair_counts)
        # Service B もService A と同じ候補を表示（両方独立して選択可能）
        options_b = _build_options(service_clone_counts, service_pair_counts)

        enabled_b = {opt["value"] for opt in options_b if not opt.get("disabled")}
        next_related = (
            current_related_service if current_related_service in enabled_b else None
        )

        return options_a, options_b, next_related

    @app.callback(
        Output("service-b-group", "style"),
        Input("service-a-filter", "value"),
    )
    def toggle_related_service_visibility(focus_service):
        """新UIではService Bは常に非表示（レイアウトで直接表示）."""
        # 後方互換用: service-b-groupは常に非表示
        return {"display": "none"}

    @app.callback(
        Output("service-a-filter", "value"),
        Input("service-a-filter", "options"),
        State("service-a-filter", "value"),
    )
    def keep_focus_service_if_valid(options, current_value):
        """フィルタ変更で Focus サービスが無効化された場合は選択解除する."""
        if not current_value:
            return current_value
        valid_values = {
            o.get("value") for o in (options or []) if not o.get("disabled")
        }
        if current_value in valid_values:
            return current_value
        return None

    @app.callback(
        [
            Output("service-a-filter", "placeholder"),
            Output("service-b-filter", "placeholder"),
        ],
        Input("lang-store", "data"),
    )
    def update_service_filter_placeholders(lang):
        """Return English placeholders for service selection dropdowns."""
        return "Service A", "Service B"

    @app.callback(
        Output("code-type-store", "data"),
        [Input({"type": "code-type-btn", "index": ALL}, "n_clicks")],
        [State("code-type-store", "data")],
        prevent_initial_call=True,
    )
    def update_selected_code_type(n_clicks, current_value):
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update
        if not any((count or 0) > 0 for count in (n_clicks or [])):
            return no_update

        button_id = ctx.triggered[0]["prop_id"].split(".")[0]
        try:
            val = json.loads(button_id)["index"]
            if val == (current_value or "all"):
                return no_update
            return val
        except (json.JSONDecodeError, KeyError, TypeError):
            return no_update

    @app.callback(
        Output("code-type-store", "data", allow_duplicate=True),
        [
            Input("project-selector", "value"),
            Input("comodification-filter", "value"),
            Input("comodification-min-filter", "value"),
            Input("service-scope-filter", "value"),
            Input("cross-service-filter", "value"),
            Input("service-spread-filter", "value"),
            Input("service-spread-min-filter", "value"),
            Input("service-a-filter", "value"),
            Input("service-b-filter", "value"),
        ],
        State("code-type-store", "data"),
        prevent_initial_call=True,
    )
    def sync_code_type_with_service_filters(
        project_value,
        comodified_val,
        comodification_min,
        service_scope,
        cross_service,
        service_spread,
        service_spread_min,
        focus_service,
        related_service,
        active_code_type,
    ):
        if not project_value or "|||" not in project_value:
            return no_update

        try:
            project, commit, language = project_value.split("|||", 2)
            df, _, _ = load_and_process_data(project, commit, language)
        except Exception as e:
            logger.warning("Code type sync load error: %s", e)
            return no_update

        if df is None or df.empty:
            return "all"

        df_filtered = _apply_common_pair_filters(
            df,
            detection_method="all",
            comodified_val=comodified_val,
            service_scope=service_scope,
            code_type_filter="all",
            cross_service=cross_service,
            service_spread=service_spread,
            comodification_min=comodification_min,
            service_spread_min=service_spread_min,
        )
        df_filtered = _apply_focus_related_service_filter(
            df_filtered, focus_service, related_service
        )

        counts = _calculate_code_type_counts(df_filtered)
        normalized = _normalize_code_type_selection(active_code_type, counts)
        if normalized == (active_code_type or "all"):
            return no_update
        return normalized

    # Dynamic generation of Code Type buttons with counts
    @app.callback(
        Output("code-type-buttons-container", "children"),
        [
            Input("project-selector", "value"),
            Input("comodification-filter", "value"),
            Input("comodification-min-filter", "value"),
            Input("service-scope-filter", "value"),
            Input("cross-service-filter", "value"),
            Input("service-spread-filter", "value"),
            Input("service-spread-min-filter", "value"),
            Input("service-a-filter", "value"),
            Input("service-b-filter", "value"),
            Input("code-type-store", "data"),
        ],
    )
    def update_code_type_counts(
        project_value,
        comodified_val,
        comodification_min,
        service_scope,
        cross_service,
        service_spread,
        service_spread_min,
        focus_service,
        related_service,
        active_code_type,
    ):
        if not project_value:
            return _build_code_type_buttons(active_code_type=active_code_type)

        # Parse project info similar to main callback
        try:
            project, commit, language = project_value.split("|||", 2)
        except (ValueError, AttributeError):
            return _build_code_type_buttons(active_code_type=active_code_type)

        # Load data (should be cached)
        df, _, _ = load_and_process_data(project, commit, language)
        if df is None or df.empty:
            return _build_code_type_buttons(active_code_type=active_code_type)

        df_filtered = _apply_common_pair_filters(
            df,
            detection_method="all",
            comodified_val=comodified_val,
            service_scope=service_scope,
            code_type_filter="all",
            cross_service=cross_service,
            service_spread=service_spread,
            comodification_min=comodification_min,
            service_spread_min=service_spread_min,
        )
        df_filtered = _apply_focus_related_service_filter(
            df_filtered, focus_service, related_service
        )
        counts = _calculate_code_type_counts(df_filtered)
        pair_counts = _calculate_code_type_pair_counts(df_filtered)
        return _build_code_type_buttons(
            active_code_type=active_code_type,
            counts=counts,
            pair_counts=pair_counts,
        )

    # Update cross-service filter options based on project data (Filtered)
    @app.callback(
        [
            Output("cross-service-filter", "options"),
            Output("clone-id-option-count", "children"),
        ],
        [
            Input("project-selector", "value"),
            Input("comodification-filter", "value"),
            Input("comodification-min-filter", "value"),
            Input("service-scope-filter", "value"),
            Input("code-type-store", "data"),
            Input("clone-sort-order", "value"),
            Input("service-spread-filter", "value"),
            Input("service-spread-min-filter", "value"),
        ],
    )
    def update_cross_service_options(
        project_value,
        comodified_val,
        comodification_min,
        service_scope,
        code_type_filter,
        sort_order,
        service_spread,
        service_spread_min,
    ):
        empty_options = [{"label": "All", "value": "all"}]
        if not project_value:
            return empty_options, "0 clone groups"
        try:
            if "|||" in project_value:
                project, commit, language = project_value.split("|||", 2)
            else:
                return empty_options, "0 clone groups"

            # Reuse load_and_process_data (it is cached)
            df, _, _ = load_and_process_data(project, commit, language)

            if df is None or df.empty:
                return empty_options, "0 clone groups"

            # 散布図に実際に表示されるのと同じ基準で候補を作る.
            df_filtered = _apply_common_pair_filters(
                df,
                detection_method="all",
                comodified_val=comodified_val,
                service_scope=service_scope,
                code_type_filter=code_type_filter,
                service_spread=("all" if service_scope == "within" else service_spread),
                comodification_min=comodification_min,
                service_spread_min=service_spread_min,
            )

            if df_filtered.empty:
                return [
                    {
                        "label": "No matching clones",
                        "value": "all",
                    }
                ], "0 clone groups"

            if "clone_id" not in df_filtered.columns:
                return empty_options, "0 clone groups"

            service_counts = _clone_service_count_series(df_filtered)
            pair_counts = df_filtered.groupby("clone_id").size()
            classifications = _classify_clone_sets(df_filtered)
            final_target = service_counts.sort_values(ascending=False)
            top_ids = final_target.index.tolist()

            if not top_ids:
                return [
                    {
                        "label": "No matching clones",
                        "value": "all",
                    }
                ], "0 clone groups"

            # ラベルの補助情報も、現在表示中のペア集合に対して算出する.
            df_stats_source = df_filtered[df_filtered["clone_id"].isin(top_ids)]

            clone_stats = []

            if "file_type_x" in df_stats_source.columns:
                # Group by clone_id and determine type
                for cid in top_ids:
                    subset = df_stats_source[df_stats_source["clone_id"] == cid]
                    if subset.empty:
                        continue

                    types_x = subset["file_type_x"].astype(str)
                    types_y = subset["file_type_y"].astype(str)
                    all_types = set(types_x) | set(types_y)

                    if "test" in all_types and len(all_types - {"test"}) > 0:
                        ctype = "Mixed"
                    elif len(all_types) == 1:
                        ctype = list(all_types)[0].capitalize()
                    elif "logic" in all_types:
                        ctype = "Logic"
                    else:
                        ctype = "Mixed"

                    comod_count = int(_co_modification_count_series(subset).sum())

                    clone_stats.append(
                        {
                            "clone_id": int(cid),
                            "service_count": final_target[cid],
                            "pair_count": int(pair_counts.get(cid, 0)),
                            "code_type": ctype,
                            "comod_count": comod_count,
                            "services": sorted(
                                set(subset["service_x"].dropna().astype(str))
                                | set(subset["service_y"].dropna().astype(str))
                            ),
                        }
                    )
            else:
                # Fallback for old data without file types
                for cid in top_ids:
                    subset = df_stats_source[df_stats_source["clone_id"] == cid]
                    comod_count = int(_co_modification_count_series(subset).sum())

                    clone_stats.append(
                        {
                            "clone_id": int(cid),
                            "service_count": final_target[cid],
                            "pair_count": int(pair_counts.get(cid, 0)),
                            "code_type": "Unknown",
                            "comod_count": comod_count,
                            "services": sorted(
                                set(subset["service_x"].dropna().astype(str))
                                | set(subset["service_y"].dropna().astype(str))
                            ),
                        }
                    )

            # Co-modification threshold is already applied by the main filter.
            min_comod_threshold = 0
            if min_comod_threshold > 0:
                clone_stats = [
                    s
                    for s in clone_stats
                    if s.get("comod_count", 0) >= min_comod_threshold
                ]

            if not clone_stats:
                return [
                    {"label": "No matching clones", "value": "all"}
                ], "0 clone groups"

            options = generate_cross_service_filter_options(
                clone_stats, sort_by=sort_order or "service_count"
            )
            return options, f"{len(clone_stats)} clone groups"
        except Exception as e:
            logger.error("Error updating cross service options: %s", e)
            return empty_options, "0 clone groups"

    # ── Help Modal ──

    # ── Filter Drawer Open/Close ──
    @app.callback(
        [
            Output("service-spread-filter", "disabled"),
            Output("service-spread-filter", "value", allow_duplicate=True),
            Output("service-spread-disabled-note", "style"),
            Output("service-spread-btn-group", "style"),
            Output("btn-spread-all", "className", allow_duplicate=True),
            Output("btn-spread-2", "className", allow_duplicate=True),
            Output("spread-input-wrapper", "className", allow_duplicate=True),
            Output("spread-draft-input", "value", allow_duplicate=True),
        ],
        Input("service-scope-filter", "value"),
        prevent_initial_call=True,
    )
    def sync_service_spread_with_scope(service_scope):
        if service_scope == "within":
            # Disabled UI, reset spread filter to all
            return (
                True,
                "all",
                {"display": "block"},
                {"display": "none"},
                "filter-preset-btn active",
                "filter-preset-btn",
                "custom-input-wrapper",
                None,
            )
        return (
            False,
            no_update,
            {"display": "none"},
            {"display": "flex"},
            no_update,
            no_update,
            no_update,
            no_update,
        )

    @app.callback(
        [
            Output("btn-comod-all", "className"),
            Output("btn-comod-0", "className"),
            Output("btn-comod-1", "className"),
            Output("comod-input-wrapper", "className"),
            Output("comod-draft-input", "value"),
            Output("comodification-filter", "value", allow_duplicate=True),
            Output("comodification-min-filter", "value", allow_duplicate=True),
        ],
        [
            Input("btn-comod-all", "n_clicks"),
            Input("btn-comod-0", "n_clicks"),
            Input("btn-comod-1", "n_clicks"),
            Input("comod-draft-input", "n_submit"),
            Input("comod-draft-input", "n_blur"),
        ],
        [State("comod-draft-input", "value")],
        prevent_initial_call=True,
    )
    def update_comod_ui(n_all, n_0, n_1, n_sub, n_blur, draft_val):
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

        btn_base = "filter-preset-btn"
        btn_active = "filter-preset-btn active"
        wrap_base = "custom-input-wrapper"
        wrap_active = "custom-input-wrapper active"

        if trigger_id == "btn-comod-all":
            return btn_active, btn_base, btn_base, wrap_base, None, "all", 0
        elif trigger_id == "btn-comod-0":
            return btn_base, btn_active, btn_base, wrap_base, None, "none", 0
        elif trigger_id == "btn-comod-1":
            return btn_base, btn_base, btn_active, wrap_base, None, "any", 1
        elif trigger_id in ["comod-draft-input"]:
            try:
                val = (
                    int(draft_val)
                    if draft_val is not None and str(draft_val).strip() != ""
                    else None
                )
            except ValueError:
                val = None
            if val is None and (draft_val is None or str(draft_val).strip() == ""):
                return btn_active, btn_base, btn_base, wrap_base, None, "all", 0
            if val is None or val < 0:
                return no_update

            if val == 0:
                return btn_active, btn_base, btn_base, wrap_base, None, "all", 0

            return btn_base, btn_base, btn_base, wrap_active, val, "custom", val

        return no_update

    @app.callback(
        [
            Output("btn-spread-all", "className"),
            Output("btn-spread-2", "className"),
            Output("spread-input-wrapper", "className"),
            Output("spread-draft-input", "value"),
            Output("service-spread-filter", "value", allow_duplicate=True),
            Output("service-spread-min-filter", "value", allow_duplicate=True),
        ],
        [
            Input("btn-spread-all", "n_clicks"),
            Input("btn-spread-2", "n_clicks"),
            Input("spread-draft-input", "n_submit"),
            Input("spread-draft-input", "n_blur"),
        ],
        [State("spread-draft-input", "value")],
        prevent_initial_call=True,
    )
    def update_spread_ui(n_all, n_2, n_sub, n_blur, draft_val):
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

        btn_base = "filter-preset-btn"
        btn_active = "filter-preset-btn active"
        wrap_base = "custom-input-wrapper"
        wrap_active = "custom-input-wrapper active"

        if trigger_id == "btn-spread-all":
            return btn_active, btn_base, wrap_base, None, "all", 1
        elif trigger_id == "btn-spread-2":
            return btn_base, btn_active, wrap_base, None, 2, 2
        elif trigger_id in ["spread-draft-input"]:
            try:
                val = (
                    int(draft_val)
                    if draft_val is not None and str(draft_val).strip() != ""
                    else None
                )
            except ValueError:
                val = None

            if val is None and (draft_val is None or str(draft_val).strip() == ""):
                return btn_active, btn_base, wrap_base, None, "all", 1
            if val is None or val <= 0:
                return no_update

            if val == 1:
                return btn_active, btn_base, wrap_base, None, "all", 1

            return btn_base, btn_base, wrap_active, val, "custom", val

        return no_update

    @app.callback(
        Output("cross-service-filter", "value", allow_duplicate=True),
        [
            Input("cross-service-filter", "options"),
            Input("service-scope-filter", "value"),
            Input("comodification-filter", "value"),
            Input("comodification-min-filter", "value"),
            Input("code-type-store", "data"),
            Input("service-spread-filter", "value"),
            Input("service-spread-min-filter", "value"),
        ],
        State("cross-service-filter", "value"),
        prevent_initial_call=True,
    )
    def clear_invalid_clone_id(
        options,
        _scope,
        _comodification,
        _comodification_min,
        _code_type,
        _service_spread,
        _service_spread_min,
        current_value,
    ):
        if not current_value or current_value == "all":
            return no_update
        valid_values = {str(option.get("value")) for option in (options or [])}
        if str(current_value) in valid_values:
            return no_update
        return "all"

    # ── Active Filter Tags ──
    @app.callback(
        Output("active-filter-tags", "children"),
        [
            Input("project-selector", "value"),
            Input("service-scope-filter", "value"),
            Input("comodification-filter", "value"),
            Input("comodification-min-filter", "value"),
            Input("code-type-store", "data"),
            Input("cross-service-filter", "value"),
            Input("service-spread-filter", "value"),
            Input("service-spread-min-filter", "value"),
            Input("clone-id-filter", "value"),
            Input("service-a-filter", "value"),
            Input("service-b-filter", "value"),
        ],
    )
    def update_active_filter_tags(
        project_value,
        scope_filter,
        comod_filter,
        comodification_min,
        code_type,
        cross_service_filter,
        service_spread_filter,
        service_spread_min,
        clone_id_filter,
        service_a,
        service_b,
    ):
        """3段目に適用中フィルタ情報とクローンペア数を表示する."""
        tags = []

        if scope_filter and scope_filter != "all":
            label = "Within Service" if scope_filter == "within" else "Cross Service"
            tags.append(
                html.Span(
                    [
                        html.I(
                            className="bi bi-diagram-3", style={"marginRight": "4px"}
                        ),
                        label,
                    ],
                    className="filter-tag",
                )
            )

        if comod_filter and comod_filter != "all":
            comod_labels = {
                "yes": "Any co-modification",
                "true": "Any co-modification",
                "any": "Any co-modification",
                "no": "No co-modification",
                "false": "No co-modification",
                "none": "No co-modification",
                "once": "Co-modified once",
                "repeated": "Repeated co-modification",
                "custom": f"Co-modification >= {comodification_min}",
            }
            label = comod_labels.get(comod_filter, str(comod_filter))
            tags.append(
                html.Span(
                    [
                        html.I(
                            className="bi bi-arrow-repeat", style={"marginRight": "4px"}
                        ),
                        label,
                    ],
                    className="filter-tag",
                )
            )

        if (
            service_spread_filter
            and service_spread_filter != "all"
            and scope_filter != "within"
        ):
            threshold = (
                service_spread_min
                if service_spread_filter == "custom"
                else service_spread_filter
            )
            tags.append(
                html.Span(
                    [
                        html.I(
                            className="bi bi-diagram-3", style={"marginRight": "4px"}
                        ),
                        f"{threshold}+ services",
                    ],
                    className="filter-tag",
                )
            )

        if code_type and code_type != "all":
            type_labels = {
                "logic": "Logic",
                "data": "Data",
                "test": "Test",
                "config": "Config",
                "mixed": "Mixed",
            }
            label = type_labels.get(code_type, code_type.capitalize())
            tags.append(
                html.Span(
                    [
                        html.I(
                            className="bi bi-file-code", style={"marginRight": "4px"}
                        ),
                        label,
                    ],
                    className="filter-tag",
                )
            )

        if cross_service_filter and cross_service_filter != "all":
            tags.append(
                html.Span(
                    [
                        html.I(className="bi bi-hash", style={"marginRight": "4px"}),
                        f"Clone {cross_service_filter}",
                    ],
                    className="filter-tag",
                )
            )

        if clone_id_filter and clone_id_filter != "all":
            tags.append(
                html.Span(
                    [
                        html.I(className="bi bi-search", style={"marginRight": "4px"}),
                        f"Clone ID {clone_id_filter}",
                    ],
                    className="filter-tag",
                )
            )

        if service_a and service_b:
            tags.append(
                html.Span(
                    [
                        html.I(
                            className="bi bi-arrow-left-right",
                            style={"marginRight": "4px"},
                        ),
                        f"{service_a} ↔ {service_b}",
                    ],
                    className="filter-tag",
                )
            )
        elif service_a:
            tags.append(
                html.Span(
                    [
                        html.I(
                            className="bi bi-bullseye", style={"marginRight": "4px"}
                        ),
                        service_a,
                    ],
                    className="filter-tag",
                )
            )

        if not tags:
            tags.append(html.Span("All Data", className="filter-tags-empty"))

        if not project_value or "|||" not in project_value:
            tags.append(
                html.Span(
                    [html.B("0"), " / 0 pairs (0.0%)"],
                    className="filter-pair-summary",
                    style={"marginLeft": "16px"},
                )
            )
            return tags

        try:
            project, commit, language = project_value.split("|||", 2)
        except ValueError as e:
            logger.warning(
                "Pair summary parse error for project_value=%s: %s", project_value, e
            )
            tags.append(
                html.Span("Pair summary unavailable", className="filter-pair-summary")
            )
            return tags

        try:
            df_raw, _, _ = load_and_process_data(project, commit, language)
        except Exception as e:
            logger.error(
                (
                    "Pair summary load error for project=%s commit=%s "
                    "language=%s project_value=%s: %s"
                ),
                project,
                commit,
                language,
                project_value,
                e,
            )
            tags.append(
                html.Span("Pair summary unavailable", className="filter-pair-summary")
            )
            return tags

        if df_raw is None:
            total = 0
            current = 0
        else:
            total = len(df_raw)
            df_filtered = _apply_common_pair_filters(
                df_raw,
                detection_method="all",
                comodified_val=comod_filter,
                service_scope=scope_filter,
                code_type_filter=code_type,
                cross_service=cross_service_filter,
                service_spread=service_spread_filter,
                comodification_min=comodification_min,
                service_spread_min=service_spread_min,
            )
            df_filtered = _apply_clone_id_filter(df_filtered, clone_id_filter)
            df_filtered = _apply_focus_related_service_filter(
                df_filtered, service_a, service_b
            )
            current = len(df_filtered)

        ratio = (current / total * 100) if total > 0 else 0.0

        if 0 < ratio < 0.1:
            ratio_str = "< 0.1%"
        else:
            ratio_str = f"{ratio:.1f}%"

        tags.append(
            html.Span(
                [html.B(f"{current:,}"), f" / {total:,} pairs ({ratio_str})"],
                className="filter-pair-summary",
                style={"marginLeft": "16px"},
            )
        )
        return tags
