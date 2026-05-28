import re

import pandas as pd
from pathlib import Path

from src.visualize.callbacks.filter_callbacks import _apply_common_pair_filters
from src.visualize.plotting import create_scatter_plot


def _sample_row(
    *,
    clone_id: int,
    file_id_x: int,
    file_id_y: int,
    relation: str,
    clone_type: str,
    file_path_x: str,
    file_path_y: str,
    service_x: str,
    service_y: str,
    start_line_x: int = 1,
    end_line_x: int = 5,
    start_line_y: int = 10,
    end_line_y: int = 15,
):
    return {
        "clone_id": clone_id,
        "file_id_x": file_id_x,
        "file_id_y": file_id_y,
        "relation": relation,
        "clone_type": clone_type,
        "file_path_x": file_path_x,
        "file_path_y": file_path_y,
        "start_line_x": start_line_x,
        "end_line_x": end_line_x,
        "start_line_y": start_line_y,
        "end_line_y": end_line_y,
        "service_x": service_x,
        "service_y": service_y,
    }


def _marker_traces(fig):
    traces = []
    for trace in fig.data:
        if getattr(trace, "mode", None) != "markers":
            continue
        customdata = getattr(trace, "customdata", None)
        if customdata is None or len(customdata) == 0:
            continue
        traces.append(trace)
    return traces


def _load_fixture_scatter_df() -> pd.DataFrame:
    fixture_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "scatter"
        / "sample_scatter_java.csv"
    )
    return pd.read_csv(fixture_path)


def test_create_scatter_plot_plots_expected_points_for_all_categories():
    df = pd.DataFrame(
        [
            _sample_row(
                clone_id=1,
                file_id_x=1,
                file_id_y=10,
                relation="intra",
                clone_type="ccfsw",
                file_path_x="/repo/svc-a/src/A.java",
                file_path_y="/repo/svc-a/src/B.java",
                service_x="svc-a",
                service_y="svc-a",
            ),
            _sample_row(
                clone_id=2,
                file_id_x=2,
                file_id_y=20,
                relation="inter",
                clone_type="ccfsw",
                file_path_x="/repo/svc-a/src/C.java",
                file_path_y="/repo/svc-b/src/D.java",
                service_x="svc-a",
                service_y="svc-b",
            ),
            _sample_row(
                clone_id=3,
                file_id_x=3,
                file_id_y=30,
                relation="intra",
                clone_type="tks",
                file_path_x="/repo/svc-a/src/E.java",
                file_path_y="/repo/svc-a/src/F.java",
                service_x="svc-a",
                service_y="svc-a",
            ),
            _sample_row(
                clone_id=4,
                file_id_x=4,
                file_id_y=40,
                relation="inter",
                clone_type="tks",
                file_path_x="/repo/svc-a/src/G.java",
                file_path_y="/repo/svc-b/src/H.java",
                service_x="svc-a",
                service_y="svc-b",
            ),
        ]
    )
    file_ranges = {"svc-a": [(1, 50)], "svc-b": [(51, 100)]}

    fig, _ = create_scatter_plot(df, file_ranges, "owner.repo", "Java")
    traces = _marker_traces(fig)

    plotted = {}
    for trace in traces:
        is_tks = "TKS" in (trace.name or "")
        symbol = trace.marker.symbol
        for x, y in zip(trace.x, trace.y, strict=True):
            plotted[(int(x), int(y))] = (symbol, is_tks)

    assert plotted[(10, 1)] == ("circle", False)
    assert plotted[(20, 2)] == ("square", False)
    assert plotted[(30, 3)] == ("circle", True)
    assert plotted[(40, 4)] == ("square", True)
    assert set(plotted.keys()) == {(10, 1), (20, 2), (30, 3), (40, 4)}


def test_create_scatter_plot_uses_unique_clone_key_for_overlap_count():
    row_base = _sample_row(
        clone_id=10,
        file_id_x=5,
        file_id_y=7,
        relation="intra",
        clone_type="ccfsw",
        file_path_x="/repo/svc-a/src/A.java",
        file_path_y="/repo/svc-a/src/B.java",
        service_x="svc-a",
        service_y="svc-a",
    )

    duplicate_same_clone_key = dict(row_base)
    different_clone_key_same_coord = _sample_row(
        clone_id=11,
        file_id_x=5,
        file_id_y=7,
        relation="intra",
        clone_type="ccfsw",
        file_path_x="/repo/svc-a/src/C.java",
        file_path_y="/repo/svc-a/src/D.java",
        service_x="svc-a",
        service_y="svc-a",
    )

    df = pd.DataFrame(
        [row_base, duplicate_same_clone_key, different_clone_key_same_coord]
    )
    file_ranges = {"svc-a": [(1, 20)]}

    fig, _ = create_scatter_plot(df, file_ranges, "owner.repo", "Java")
    traces = _marker_traces(fig)

    # 新しいホバー実装では overlap_count は text プロパティに埋め込まれる.
    # trace.x = display_file_id_y, trace.y = display_file_id_x なので
    # 元の file_id_y=7, file_id_x=5 のセルを (7, 5) で探す.
    overlap_counts = []
    for trace in traces:
        texts = list(trace.text) if trace.text is not None else []
        for (x, y), text in zip(
            zip(trace.x, trace.y, strict=True), texts, strict=True
        ):
            if int(x) == 7 and int(y) == 5:
                match = re.search(r"Overlap Count: (\d+)", text)
                if match:
                    overlap_counts.append(int(match.group(1)))

    assert overlap_counts
    assert set(overlap_counts) == {2}


def test_filtered_cross_service_rows_only_are_plotted():
    df = pd.DataFrame(
        [
            _sample_row(
                clone_id=21,
                file_id_x=11,
                file_id_y=101,
                relation="intra",
                clone_type="ccfsw",
                file_path_x="/repo/svc-a/src/A.java",
                file_path_y="/repo/svc-a/src/B.java",
                service_x="svc-a",
                service_y="svc-a",
            ),
            _sample_row(
                clone_id=22,
                file_id_x=12,
                file_id_y=102,
                relation="inter",
                clone_type="ccfsw",
                file_path_x="/repo/svc-a/src/C.java",
                file_path_y="/repo/svc-b/src/D.java",
                service_x="svc-a",
                service_y="svc-b",
            ),
            _sample_row(
                clone_id=23,
                file_id_x=13,
                file_id_y=103,
                relation="inter",
                clone_type="tks",
                file_path_x="/repo/svc-b/src/E.java",
                file_path_y="/repo/svc-c/src/F.java",
                service_x="svc-b",
                service_y="svc-c",
            ),
        ]
    )
    filtered = _apply_common_pair_filters(df, service_scope="cross")

    fig, _ = create_scatter_plot(
        filtered,
        file_ranges={"svc-a": [(1, 40)], "svc-b": [(41, 80)], "svc-c": [(81, 120)]},
        project_name="owner.repo",
        language="Java",
    )
    traces = _marker_traces(fig)

    plotted_points = set()
    for trace in traces:
        for x, y in zip(trace.x, trace.y, strict=True):
            plotted_points.add((int(x), int(y)))

    assert plotted_points == {(102, 12), (103, 13)}


def test_filtered_data_code_type_only_plots_data_clone_sets():
    df = pd.DataFrame(
        [
            _sample_row(
                clone_id=31,
                file_id_x=1,
                file_id_y=201,
                relation="intra",
                clone_type="ccfsw",
                file_path_x="/repo/svc-a/src/A.java",
                file_path_y="/repo/svc-a/src/B.java",
                service_x="svc-a",
                service_y="svc-a",
            )
            | {"file_type_x": "data", "file_type_y": "data"},
            _sample_row(
                clone_id=32,
                file_id_x=2,
                file_id_y=202,
                relation="inter",
                clone_type="ccfsw",
                file_path_x="/repo/svc-a/src/C.java",
                file_path_y="/repo/svc-b/src/D.java",
                service_x="svc-a",
                service_y="svc-b",
            )
            | {"file_type_x": "logic", "file_type_y": "logic"},
            _sample_row(
                clone_id=33,
                file_id_x=3,
                file_id_y=203,
                relation="inter",
                clone_type="tks",
                file_path_x="/repo/svc-a/src/E.java",
                file_path_y="/repo/svc-b/src/F.java",
                service_x="svc-a",
                service_y="svc-b",
            )
            | {"file_type_x": "test", "file_type_y": "logic"},
        ]
    )
    filtered = _apply_common_pair_filters(df, code_type_filter="data")

    fig, _ = create_scatter_plot(
        filtered,
        file_ranges={"svc-a": [(1, 230)], "svc-b": [(231, 260)]},
        project_name="owner.repo",
        language="Java",
    )
    traces = _marker_traces(fig)

    plotted_points = set()
    for trace in traces:
        for x, y in zip(trace.x, trace.y, strict=True):
            plotted_points.add((int(x), int(y)))

    assert plotted_points == {(201, 1)}


def test_fixture_scatter_data_can_drive_plot_and_filters():
    df = _load_fixture_scatter_df()
    filtered = _apply_common_pair_filters(df, service_scope="cross")

    fig, _ = create_scatter_plot(
        filtered,
        file_ranges={"svc-a": [(1, 50)], "svc-b": [(51, 100)], "svc-c": [(101, 150)]},
        project_name="sample.project",
        language="Java",
    )
    traces = _marker_traces(fig)

    plotted_points = set()
    for trace in traces:
        for x, y in zip(trace.x, trace.y, strict=True):
            plotted_points.add((int(x), int(y)))

    # fixture内の inter 行のみが表示される
    assert plotted_points == {(62, 12), (63, 13), (65, 15)}


def test_create_scatter_plot_hides_axis_tick_labels_and_grid_lines():
    df = pd.DataFrame(
        [
            _sample_row(
                clone_id=41,
                file_id_x=7,
                file_id_y=70,
                relation="intra",
                clone_type="ccfsw",
                file_path_x="/repo/svc-a/src/A.java",
                file_path_y="/repo/svc-a/src/B.java",
                service_x="svc-a",
                service_y="svc-a",
            ),
            _sample_row(
                clone_id=42,
                file_id_x=8,
                file_id_y=80,
                relation="inter",
                clone_type="tks",
                file_path_x="/repo/svc-a/src/C.java",
                file_path_y="/repo/svc-b/src/D.java",
                service_x="svc-a",
                service_y="svc-b",
            ),
        ]
    )

    fig, _ = create_scatter_plot(
        df,
        file_ranges={"svc-a": [(1, 50)], "svc-b": [(51, 100)]},
        project_name="owner.repo",
        language="Java",
    )

    assert fig.layout.xaxis.showticklabels is False
    assert fig.layout.yaxis.showticklabels is False
    assert fig.layout.xaxis.showgrid is False
    assert fig.layout.yaxis.showgrid is False


def test_create_scatter_plot_keeps_marker_outline_lines_in_interactive_mode():
    df = pd.DataFrame(
        [
            _sample_row(
                clone_id=43,
                file_id_x=9,
                file_id_y=90,
                relation="intra",
                clone_type="ccfsw",
                file_path_x="/repo/svc-a/src/E.java",
                file_path_y="/repo/svc-a/src/F.java",
                service_x="svc-a",
                service_y="svc-a",
            ),
        ]
    )

    fig, _ = create_scatter_plot(
        df,
        file_ranges={"svc-a": [(1, 100)]},
        project_name="owner.repo",
        language="Java",
        static_mode=False,
    )

    for trace in _marker_traces(fig):
        assert trace.marker.line.width == 1


def test_create_scatter_plot_returns_tuple_for_empty_dataframe():
    empty_df = pd.DataFrame()

    fig, service_legend = create_scatter_plot(
        empty_df,
        file_ranges={},
        project_name="owner.repo",
        language="Java",
    )

    assert fig.layout.title.text == "No data available"
    assert service_legend == []


def test_create_scatter_plot_uses_click_events_without_selection_redraw():
    df = pd.DataFrame(
        [
            _sample_row(
                clone_id=71,
                file_id_x=10,
                file_id_y=110,
                relation="intra",
                clone_type="ccfsw",
                file_path_x="/repo/svc-a/src/A.java",
                file_path_y="/repo/svc-a/src/B.java",
                service_x="svc-a",
                service_y="svc-a",
            ),
        ]
    )

    fig, _ = create_scatter_plot(
        df,
        file_ranges={"svc-a": [(1, 120)]},
        project_name="owner.repo",
        language="Java",
    )

    assert fig.layout.clickmode == "event"
    marker_traces = _marker_traces(fig)
    assert marker_traces
    marker_json = [
        trace
        for trace in fig.to_plotly_json()["data"]
        if trace.get("mode") == "markers" and trace.get("customdata")
    ]
    assert marker_json
    assert all("selected" not in trace for trace in marker_json)
    assert all("selectedpoints" not in trace for trace in marker_json)


def test_create_scatter_plot_customdata_stays_click_event_compatible():
    df = pd.DataFrame(
        [
            _sample_row(
                clone_id=72,
                file_id_x=10,
                file_id_y=110,
                relation="intra",
                clone_type="ccfsw",
                file_path_x="/repo/svc-a/src/A.java",
                file_path_y="/repo/svc-a/src/B.java",
                service_x="svc-a",
                service_y="svc-a",
            ),
        ],
        index=[123],
    )

    fig, _ = create_scatter_plot(
        df,
        file_ranges={"svc-a": [(1, 120)]},
        project_name="owner.repo",
        language="Java",
    )

    marker_trace = _marker_traces(fig)[0]
    first_customdata = marker_trace.customdata[0]
    serialized_customdata = fig.to_plotly_json()["data"][0]["customdata"]

    assert not hasattr(marker_trace.customdata, "dtype")
    assert first_customdata == [123, 72]
    assert serialized_customdata == [[123, 72]]


def test_create_scatter_plot_compacts_unknown_file_id_gaps():
    df = pd.DataFrame(
        [
            _sample_row(
                clone_id=81,
                file_id_x=1,
                file_id_y=10,
                relation="inter",
                clone_type="ccfsw",
                file_path_x="/repo/svc-a/src/A.java",
                file_path_y="/repo/svc-b/src/B.java",
                service_x="svc-a",
                service_y="svc-b",
            ),
            _sample_row(
                clone_id=82,
                file_id_x=5,
                file_id_y=10,
                relation="inter",
                clone_type="ccfsw",
                file_path_x="/repo/unknown/src/C.java",
                file_path_y="/repo/svc-b/src/B.java",
                service_x="unknown",
                service_y="svc-b",
            ),
        ],
        index=[101, 102],
    )

    fig, service_legend = create_scatter_plot(
        df,
        file_ranges={"svc-a": [(1, 2)], "svc-b": [(10, 11)]},
        project_name="owner.repo",
        language="Java",
    )

    plotted_points = set()
    custom_indices = set()
    for trace in _marker_traces(fig):
        for x, y in zip(trace.x, trace.y, strict=True):
            plotted_points.add((int(x), int(y)))
        for custom in trace.customdata:
            custom_indices.add(int(custom[0]))

    assert plotted_points == {(3, 1)}
    assert custom_indices == {101}
    assert fig.layout.xaxis.range == (-1.0, 6.0)
    assert fig.layout.yaxis.range == (-1.0, 6.0)
    assert service_legend[1]["full_name"] == "svc-b"
    assert service_legend[1]["start"] == 3
    assert service_legend[1]["end"] == 4
