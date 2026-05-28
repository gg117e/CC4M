import logging

logger = logging.getLogger(__name__)
import plotly.graph_objects as go
import numpy as np
import pandas as pd

UNKNOWN_SERVICE_VALUES = {"", "unknown", "nan", "none", "null", "unresolved"}


def _text_series(series, fill_value=""):
    return series.astype("string").fillna(fill_value).astype(str)


def _is_known_service_name(service_name):
    normalized = "" if service_name is None else str(service_name).strip().lower()
    return normalized not in UNKNOWN_SERVICE_VALUES


def _filter_known_service_pairs(df):
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


def _filter_known_file_ranges(file_ranges):
    return {
        service_name: ranges
        for service_name, ranges in (file_ranges or {}).items()
        if _is_known_service_name(service_name)
    }


def _build_display_file_ranges(file_ranges):
    """Known service rangesを空白なしの表示用file_idへ詰め替える."""
    display_file_ranges = {}
    file_id_to_display_id = {}

    sorted_services = sorted(
        (file_ranges or {}).items(),
        key=lambda item: min(r[0] for r in item[1]) if item[1] else float("inf"),
    )
    first_starts = [
        int(r[0])
        for _, ranges in sorted_services
        for r in (ranges or [])
        if r is not None and len(r) >= 2
    ]
    next_display_id = min(first_starts) if first_starts else 0

    for service_name, ranges in sorted_services:
        display_ranges = []
        sorted_ranges = sorted(ranges or [], key=lambda r: (r[0], r[1]))
        for raw_start, raw_end in sorted_ranges:
            try:
                start = int(raw_start)
                end = int(raw_end)
            except (TypeError, ValueError):
                continue
            if end < start:
                continue

            display_start = next_display_id
            for file_id in range(start, end + 1):
                file_id_to_display_id[file_id] = next_display_id
                next_display_id += 1
            display_end = next_display_id - 1
            display_ranges.append((display_start, display_end))

        if display_ranges:
            display_file_ranges[service_name] = display_ranges

    return display_file_ranges, file_id_to_display_id


def _add_display_coordinates(df, file_ranges):
    """元file_idを保持したまま、表示用の圧縮座標列を追加する."""
    display_file_ranges, file_id_to_display_id = _build_display_file_ranges(file_ranges)
    if df is None or df.empty:
        return df, display_file_ranges

    if not {"file_id_x", "file_id_y"} <= set(df.columns):
        return df, display_file_ranges

    df = df.copy()
    raw_x = pd.to_numeric(df["file_id_x"], errors="coerce")
    raw_y = pd.to_numeric(df["file_id_y"], errors="coerce")

    if file_id_to_display_id:
        df["display_file_id_x"] = raw_x.map(file_id_to_display_id)
        df["display_file_id_y"] = raw_y.map(file_id_to_display_id)
        df = df.dropna(subset=["display_file_id_x", "display_file_id_y"]).copy()
        if df.empty:
            return df, display_file_ranges
        df["display_file_id_x"] = df["display_file_id_x"].astype(int)
        df["display_file_id_y"] = df["display_file_id_y"].astype(int)
        return df, display_file_ranges

    df["display_file_id_x"] = raw_x
    df["display_file_id_y"] = raw_y
    df = df.dropna(subset=["display_file_id_x", "display_file_id_y"]).copy()
    return df, display_file_ranges


def extract_service_relative_path_vectorized(file_paths, service_names):
    """サービス名以降の相対パスを抽出する (vectorized).

    file_paths がサービス短縮名を含むとき, 短縮名以降の部分を返し,
    さらに ``/src/`` を含む場合は ``src/...`` 部分のみを返す.
    一致しない場合はファイル名のみを返す.

    Args:
        file_paths: ファイルパスの配列 (numpy / list / Series).
        service_names: 同じ長さのサービス名配列.

    Returns:
        list[str]: 各行に対応する相対パス.
    """
    paths = pd.Series(file_paths, dtype="object").fillna("").astype(str)
    services = pd.Series(service_names, dtype="object").fillna("").astype(str)

    basenames = paths.str.rsplit("/", n=1).str[-1]
    result = basenames.copy()

    invalid_mask = (paths == "") | (services == "")
    if invalid_mask.any():
        result.loc[invalid_mask] = paths.loc[invalid_mask]

    valid_mask = ~invalid_mask
    if not valid_mask.any():
        return result.tolist()

    short_names = services.str.rsplit("/", n=1).str[-1]

    # 短縮名はサービス数 (通常 ~数十) のみなので unique を回す.
    for short_name in short_names[valid_mask].unique():
        if not short_name:
            continue
        candidate_mask = (
            valid_mask
            & (short_names == short_name)
            & paths.str.contains(short_name, regex=False, na=False)
        )
        if not candidate_mask.any():
            continue
        sub = (
            paths.loc[candidate_mask]
            .str.split(short_name, n=1)
            .str[1]
            .fillna("")
            .str.lstrip("/")
        )
        split_src = sub.str.split("/src/", n=1)
        has_src = split_src.str.len() > 1
        with_src = "src/" + split_src.str[1].fillna("")
        result.loc[candidate_mask] = sub.where(~has_src, with_src)

    return result.tolist()


def add_service_boundaries(fig, file_ranges):
    """サービス境界に点線を追加"""
    boundaries = set()
    for ranges in file_ranges.values():
        for start, end in ranges:
            if start > 0:
                boundaries.add(start - 0.5)
            boundaries.add(end + 0.5)

    for boundary in sorted(boundaries):
        fig.add_vline(x=boundary, line_dash="dash", line_color="gray", opacity=0.8)
        fig.add_hline(y=boundary, line_dash="dash", line_color="gray", opacity=0.8)


def add_service_labels(fig, file_ranges):
    """サービス名のラベルを追加（スタッガード配置対応）"""
    logger.debug("add_service_labels called with file_ranges: %s", file_ranges)

    # サービス数が一定以上の場合はスタッガード（千鳥）配置にする
    num_services = len(file_ranges)
    use_staggered = num_services >= 15

    # サービスを開始位置順にソートして処理（確実に隣接順にするため）
    # rangesはリストだが、サービスごとの最小開始位置でソート
    sorted_services = sorted(
        file_ranges.items(),
        key=lambda item: min(r[0] for r in item[1]) if item[1] else float("inf"),
    )

    for i, (service_name, ranges) in enumerate(sorted_services):
        # スタッガード配置用のオフセット計算
        if use_staggered:
            # 偶数/奇数でラベル位置を変える
            is_odd = i % 2 == 1
            x_label_y_pos = -0.20 if is_odd else -0.15
            y_label_x_pos = -0.08 if is_odd else -0.05
        else:
            x_label_y_pos = -0.15
            y_label_x_pos = -0.05

        logger.debug("Processing service %s with ranges %s", service_name, ranges)
        for start, end in ranges:
            center = (start + end) / 2
            text = f"{service_name.split('/')[-1]}<br>[{start}-{end}]"
            # X軸ラベル（下側）- 45度時計回りに回転、位置を下に移動
            fig.add_annotation(
                x=center,
                y=x_label_y_pos,
                xref="x",
                yref="paper",
                text=text,
                showarrow=False,
                font=dict(size=10),
                xanchor="center",
                textangle=90,
            )
            # Y軸ラベル（左側）
            fig.add_annotation(
                x=y_label_x_pos,
                y=center,
                xref="paper",
                yref="y",
                text=text,
                showarrow=False,
                font=dict(size=10),
                textangle=0,
                xanchor="right",
                yanchor="middle",
            )


def add_service_number_labels(fig, file_ranges):
    """サービス区間の番号→サービス名マッピングを構築して返す.

    Args:
        fig: Plotly Figure オブジェクト.
        file_ranges: サービス名 -> [[start, end], ...] のマッピング.

    Returns:
        list[dict]: 番号→サービス名のマッピングリスト.
            各要素は {"number": int, "service_name": str, "full_name": str,
                      "start": int, "end": int} の辞書.
    """
    sorted_services = sorted(
        file_ranges.items(),
        key=lambda item: min(r[0] for r in item[1]) if item[1] else float("inf"),
    )

    service_legend = []
    for i, (service_name, ranges) in enumerate(sorted_services):
        number = i + 1
        for start, end in ranges:
            service_legend.append(
                {
                    "number": number,
                    "service_name": service_name.split("/")[-1],
                    "full_name": service_name,
                    "start": start,
                    "end": end,
                }
            )

    return service_legend


def create_scatter_plot(
    df,
    file_ranges,
    project_name,
    language,
    static_mode=False,
    highlight_service_a=None,
    highlight_service_b=None,
):
    """データフレームから散布図を作成する（ヒートマップ風カラーマップ + マーカー形状区別）"""
    logger.debug(
        "create_scatter_plot called with file_ranges: %s, static_mode=%s",
        file_ranges,
        static_mode,
    )
    if df is None or df.empty:
        return go.Figure().update_layout(title="No data available"), []

    # データのコピーを作成（元データを変更しない）
    df = _filter_known_service_pairs(df.copy()).copy()
    file_ranges = _filter_known_file_ranges(file_ranges)
    if df.empty:
        return go.Figure().update_layout(title="No service-assigned data available"), []
    df, display_file_ranges = _add_display_coordinates(df, file_ranges)
    if df.empty:
        return (
            go.Figure().update_layout(title="No service-assigned coordinates available"),
            [],
        )

    # 必須列の補完（dest/scatter フォーマット対応）
    if "coord_pair" not in df.columns and {"file_id_x", "file_id_y"} <= set(df.columns):
        df["coord_pair"] = (
            df["file_id_y"].astype(str) + "_" + df["file_id_x"].astype(str)
        )

    logger.info("Processing data for visualization...")

    # 重複除去: 同じcoord_pair + clone_id + file情報の組み合わせを除去（高速化）
    clone_key_parts = [
        df["clone_id"].astype(str),
        _text_series(df["file_path_x"]).str.split("/").str[-1],
        df["start_line_x"].astype(str) + "-" + df["end_line_x"].astype(str),
        _text_series(df["file_path_y"]).str.split("/").str[-1],
        df["start_line_y"].astype(str) + "-" + df["end_line_y"].astype(str),
    ]
    df["clone_key"] = (
        clone_key_parts[0]
        + "|"
        + clone_key_parts[1]
        + "|"
        + clone_key_parts[2]
        + "|"
        + clone_key_parts[3]
        + "|"
        + clone_key_parts[4]
    )

    # 重複除去後のユニーククローンのみでoverlap_countを計算（高速化）
    df_unique = df.drop_duplicates(subset=["coord_pair", "clone_key"])
    coord_counts = df_unique["coord_pair"].value_counts()
    df["filtered_overlap_count"] = df["coord_pair"].map(coord_counts)

    # サービス相対パスを計算（ベクトル化で高速化）
    logger.debug(
        "Before extracting relative paths - sample file_path_x: %s",
        df["file_path_x"].iloc[0] if not df.empty else "No data",
    )
    logger.debug(
        "Before extracting relative paths - sample service_x: %s",
        df["service_x"].iloc[0] if not df.empty else "No data",
    )
    df["service_relative_path_x"] = extract_service_relative_path_vectorized(
        df["file_path_x"].values, df["service_x"].values
    )
    df["service_relative_path_y"] = extract_service_relative_path_vectorized(
        df["file_path_y"].values, df["service_y"].values
    )
    df["hover_file_name_x"] = (
        _text_series(df["file_path_x"])
        .str.replace("\\", "/", regex=False)
        .str.split("/")
        .str[-1]
    )
    df["hover_file_name_y"] = (
        _text_series(df["file_path_y"])
        .str.replace("\\", "/", regex=False)
        .str.split("/")
        .str[-1]
    )
    service_x_text = _text_series(df["service_x"])
    service_y_text = _text_series(df["service_y"])
    df["hover_service_pair"] = np.where(
        service_x_text == service_y_text,
        service_x_text,
        service_y_text + " ↔ " + service_x_text,
    )
    logger.debug(
        "After extracting relative paths - sample service_relative_path_x: %s",
        df["service_relative_path_x"].iloc[0] if not df.empty else "No data",
    )
    logger.debug(
        "After extracting relative paths - sample service_relative_path_y: %s",
        df["service_relative_path_y"].iloc[0] if not df.empty else "No data",
    )

    # クローン集中度に基づくカラーマッピング用の値を正規化（高速化）
    max_overlap = df["filtered_overlap_count"].max()
    min_overlap = df["filtered_overlap_count"].min()

    # 正規化された値（0-1）を計算（ベクトル化）
    if max_overlap > min_overlap:
        df["normalized_density"] = (df["filtered_overlap_count"] - min_overlap) / (
            max_overlap - min_overlap
        )
    else:
        df["normalized_density"] = 0

    # ヒートマップ風カラーマップ（ベクトル化で高速化）
    color_map = {
        0: "#0066CC",  # 青
        1: "#00CC66",  # 緑
        2: "#CCCC00",  # 黄
        3: "#FF6600",  # オレンジ
        4: "#CC0000",  # 赤
    }

    # ベクトル化されたカラーマッピング
    color_indices = np.clip((df["normalized_density"] * 5).astype(int), 0, 4)
    df["heatmap_color"] = [color_map[i] for i in color_indices]

    logger.info("Creating scatter plot...")

    # 空のfigureを作成
    fig = go.Figure()

    # サービス着目: 色は維持し、非対象点のみ減光する
    selected_services = [
        s
        for s in [highlight_service_a, highlight_service_b]
        if s is not None and str(s).strip() != ""
    ]
    highlight_scores = None
    if selected_services and {"service_x", "service_y"}.issubset(df.columns):
        sx = _text_series(df["service_x"])
        sy = _text_series(df["service_y"])

        if len(selected_services) == 1 or selected_services[0] == selected_services[-1]:
            target = selected_services[0]
            matched = (sx == target) | (sy == target)
            highlight_scores = pd.Series(
                np.where(matched, 1, 0),
                index=df.index,
            )
        else:
            svc_a = selected_services[0]
            svc_b = selected_services[1]
            pair_ab = ((sx == svc_a) & (sy == svc_b)) | ((sx == svc_b) & (sy == svc_a))
            # 2: A-Bペアのみ強調, 0: それ以外は減光
            highlight_scores = pd.Series(np.where(pair_ab, 2, 0), index=df.index)

    def _opacity_for(data_idx):
        if highlight_scores is None:
            return marker_base["opacity"]
        base = highlight_scores.reindex(data_idx).fillna(0).to_numpy()
        return np.where(base == 2, 1.0, np.where(base == 1, 0.95, 0.12))

    # データを関係別・検出手法別に分割
    intra_mask = df["relation"] == "intra"
    inter_mask = df["relation"] == "inter"
    method_col = (
        "detection_method" if "detection_method" in df.columns else "clone_type"
    )
    tks_mask = df[method_col].astype(str).str.lower() == "tks"
    ccfsw_mask = ~tks_mask

    # 共通のマーカー設定
    marker_base = dict(
        size=5 if static_mode else 8,  # 静的モードでは少し小さく
        line=dict(width=0 if static_mode else 1, color="white"),
        opacity=0.8,
    )

    # ホバー設定
    # 事前にHTML文字列を1個ずつ text に入れ, customdata はクリック処理用の
    # [row_index, clone_id] のみに絞ることで Figure JSON を大幅に軽量化する.
    # static_modeでもホバーを表示するため hoverinfo='skip' は設定しない
    hover_template = "%{text}<extra></extra>"

    def _build_hover_text(data):
        overlap = data["filtered_overlap_count"].to_numpy()
        fnx = data["hover_file_name_x"].to_numpy()
        pathx = data["service_relative_path_x"].to_numpy()
        sx = data["start_line_x"].to_numpy()
        ex = data["end_line_x"].to_numpy()
        fny = data["hover_file_name_y"].to_numpy()
        pathy = data["service_relative_path_y"].to_numpy()
        sy = data["start_line_y"].to_numpy()
        ey = data["end_line_y"].to_numpy()
        svcx = data["service_x"].to_numpy()
        svcy = data["service_y"].to_numpy()
        return [
            (
                f"<b>Overlap Count: {overlap[i]}</b><br>"
                "<br>"
                "<b>X file</b><br>"
                f"Service: <b>{svcx[i]}</b><br>"
                f"{fnx[i]}<br>"
                f"{pathx[i]}:{sx[i]}-{ex[i]}<br>"
                "<br>"
                "<b>Y file</b><br>"
                f"Service: <b>{svcy[i]}</b><br>"
                f"{fny[i]}<br>"
                f"{pathy[i]}:{sy[i]}-{ey[i]}"
            )
            for i in range(len(data))
        ]

    def _build_min_customdata(data):
        # customdata[0]=row_index は scatter_callbacks._resolve_clicked_row,
        # customdata[1]=clone_id は explorer_callbacks のクリックハンドラが参照する.
        return list(zip(data.index.tolist(), data["clone_id"].tolist()))

    hover_settings = dict(hovertemplate=hover_template)
    ScatterClass = go.Scattergl

    # サービス内クローン（丸いマーカー）- CCFSW
    if (intra_mask & ccfsw_mask).any():
        intra_data = df[intra_mask & ccfsw_mask]
        marker_settings = marker_base.copy()
        marker_settings.update(
            dict(
                symbol="circle",
                color=intra_data["heatmap_color"],
                opacity=_opacity_for(intra_data.index),
            )
        )

        trace_args = dict(
            x=intra_data["display_file_id_y"],
            y=intra_data["display_file_id_x"],
            mode="markers",
            marker=marker_settings,
            name="Intra-service (Normal)",
            showlegend=True,
        )
        trace_args.update(hover_settings)

        trace_args["customdata"] = _build_min_customdata(intra_data)
        trace_args["text"] = _build_hover_text(intra_data)

        fig.add_trace(ScatterClass(**trace_args))

    # サービス間クローン（四角いマーカー）- CCFSW
    if (inter_mask & ccfsw_mask).any():
        inter_data = df[inter_mask & ccfsw_mask]
        marker_settings = marker_base.copy()
        marker_settings.update(
            dict(
                symbol="square",
                color=inter_data["heatmap_color"],
                opacity=_opacity_for(inter_data.index),
            )
        )

        trace_args = dict(
            x=inter_data["display_file_id_y"],
            y=inter_data["display_file_id_x"],
            mode="markers",
            marker=marker_settings,
            name="Inter-service (Normal)",
            showlegend=True,
        )
        trace_args.update(hover_settings)

        trace_args["customdata"] = _build_min_customdata(inter_data)
        trace_args["text"] = _build_hover_text(inter_data)

        fig.add_trace(ScatterClass(**trace_args))

    # TKSサービス内クローン（丸いマーカー）
    if (intra_mask & tks_mask).any():
        tks_intra_data = df[intra_mask & tks_mask]
        marker_settings = marker_base.copy()
        marker_settings.update(
            dict(
                symbol="circle",
                color=tks_intra_data["heatmap_color"],
                opacity=_opacity_for(tks_intra_data.index),
            )
        )

        trace_args = dict(
            x=tks_intra_data["display_file_id_y"],
            y=tks_intra_data["display_file_id_x"],
            mode="markers",
            marker=marker_settings,
            name="Intra-service (TKS)",
            showlegend=True,
        )
        trace_args.update(hover_settings)

        trace_args["customdata"] = _build_min_customdata(tks_intra_data)
        trace_args["text"] = _build_hover_text(tks_intra_data)

        fig.add_trace(ScatterClass(**trace_args))

    # TKSサービス間クローン（四角いマーカー）
    if (inter_mask & tks_mask).any():
        tks_inter_data = df[inter_mask & tks_mask]
        marker_settings = marker_base.copy()
        marker_settings.update(
            dict(
                symbol="square",
                color=tks_inter_data["heatmap_color"],
                opacity=_opacity_for(tks_inter_data.index),
            )
        )

        trace_args = dict(
            x=tks_inter_data["display_file_id_y"],
            y=tks_inter_data["display_file_id_x"],
            mode="markers",
            marker=marker_settings,
            name="Inter-service (TKS)",
            showlegend=True,
        )
        trace_args.update(hover_settings)

        trace_args["customdata"] = _build_min_customdata(tks_inter_data)
        trace_args["text"] = _build_hover_text(tks_inter_data)

        fig.add_trace(ScatterClass(**trace_args))

    logger.info("Adding service boundaries and labels...")
    add_service_boundaries(fig, display_file_ranges)
    service_legend = add_service_number_labels(fig, display_file_ranges)

    # カラーバーを追加して集中度の凡例を表示
    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="markers",
            marker=dict(
                colorscale=[
                    [0, "#0066CC"],  # 青
                    [0.25, "#00CC66"],  # 緑
                    [0.5, "#CCCC00"],  # 黄
                    [0.75, "#FF6600"],  # オレンジ
                    [1, "#CC0000"],  # 赤
                ],
                showscale=True,
                cmin=min_overlap,
                cmax=max_overlap,
                colorbar=dict(
                    title=dict(
                        text="Clone pairs",
                        side="right",
                        font=dict(size=11),
                    ),
                    xref="paper",
                    xanchor="left",
                    x=1.02,
                    xpad=12,
                    thickness=14,
                    yref="paper",
                    yanchor="middle",
                    y=0.5,
                    len=1.0,
                    lenmode="fraction",
                ),
            ),
            showlegend=False,
            hoverinfo="skip",
        )
    )

    axis_range = None
    range_values = []
    for ranges in display_file_ranges.values():
        for start, end in ranges:
            range_values.extend([start, end])

    if not range_values and {"display_file_id_x", "display_file_id_y"} <= set(
        df.columns
    ):
        file_ids = pd.concat(
            [df["display_file_id_x"], df["display_file_id_y"]],
            ignore_index=True,
        )
        range_values = pd.to_numeric(file_ids, errors="coerce").dropna().tolist()

    if range_values:
        raw_min = min(range_values)
        raw_max = max(range_values)
        pad = max(2.0, (raw_max - raw_min) * 0.05)
        axis_min = raw_min - pad
        axis_max = raw_max + pad
        if axis_min == axis_max:
            axis_max = axis_min + 1
        axis_range = [axis_min, axis_max]

    fig.update_layout(
        xaxis_title="",
        yaxis_title="",
        margin=dict(l=50, r=70, t=24, b=24),
        title=None,
        autosize=True,
        showlegend=False,
        hoverlabel=dict(
            align="left",
            bgcolor="white",
            bordercolor="#d9dee7",
            font=dict(
                size=12,
                color="#1f2d3d",
                family="Noto Sans JP, Hiragino Kaku Gothic ProN, Yu Gothic UI, sans-serif",
            ),
        ),
        xaxis=dict(
            title=dict(font=dict(color="gray")),
            tickfont=dict(color="gray"),
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            range=axis_range,
            constrain="domain",
            constraintoward="left",
        ),
        yaxis=dict(
            title=dict(font=dict(color="gray")),
            tickfont=dict(color="gray"),
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            range=axis_range,
            scaleanchor="x",
            scaleratio=1,
            constrain="domain",
            constraintoward="middle",
        ),
        clickmode="event",
        uirevision=f"{project_name}_{language}",
    )

    logger.info("Scatter plot creation completed.")
    return fig, service_legend
