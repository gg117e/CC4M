import plotly.graph_objects as go

from src.visualize.callbacks.scatter_callbacks import (
    CLONE_SET_LINK_META,
    _add_clicked_point_marker,
    _clear_clone_set_link_traces,
)


def test_add_clicked_point_marker_appends_star_marker_trace():
    fig = go.Figure()

    _add_clicked_point_marker(fig, 12, 34)

    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.meta == CLONE_SET_LINK_META
    assert trace.name == "clone_set_link_clicked"
    assert list(trace.x) == [12]
    assert list(trace.y) == [34]


def test_clear_clone_set_link_traces_removes_overlay_traces_only():
    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(
            x=[1],
            y=[2],
            mode="markers",
            name="base",
        )
    )
    fig.add_trace(
        go.Scattergl(
            x=[3],
            y=[4],
            mode="markers",
            name="overlay",
            meta=CLONE_SET_LINK_META,
        )
    )

    cleaned = _clear_clone_set_link_traces(fig)

    assert len(cleaned.data) == 1
    assert cleaned.data[0].name == "base"
