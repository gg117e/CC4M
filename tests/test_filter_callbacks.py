import pandas as pd

from src.visualize.callbacks.filter_callbacks import (
    _apply_clone_id_filter,
    _apply_focus_related_service_filter,
    _build_code_type_buttons,
    _calculate_code_type_counts,
    _calculate_code_type_pair_counts,
    _normalize_code_type_selection,
)
from src.visualize.components.clone_metrics import generate_cross_service_filter_options


def _sample_pairs():
    return pd.DataFrame(
        [
            {
                "clone_id": 1,
                "service_x": "svc-a",
                "service_y": "svc-a",
                "file_type_x": "logic",
                "file_type_y": "logic",
            },
            {
                "clone_id": 2,
                "service_x": "svc-a",
                "service_y": "svc-b",
                "file_type_x": "data",
                "file_type_y": "data",
            },
            {
                "clone_id": 3,
                "service_x": "svc-a",
                "service_y": "svc-c",
                "file_type_x": "test",
                "file_type_y": "logic",
            },
            {
                "clone_id": 4,
                "service_x": "svc-b",
                "service_y": "svc-c",
                "file_type_x": "config",
                "file_type_y": "config",
            },
        ]
    )


def test_focus_service_changes_code_type_counts():
    df = _sample_pairs()

    filtered = _apply_focus_related_service_filter(df, focus_service="svc-a")
    counts = _calculate_code_type_counts(filtered)

    assert counts == {
        "all": 3,
        "logic": 1,
        "data": 1,
        "test": 0,
        "config": 0,
        "mixed": 1,
    }


def test_related_service_narrows_code_type_counts():
    df = _sample_pairs()

    filtered = _apply_focus_related_service_filter(
        df, focus_service="svc-a", related_service="svc-b"
    )
    counts = _calculate_code_type_counts(filtered)

    assert counts == {
        "all": 1,
        "logic": 0,
        "data": 1,
        "test": 0,
        "config": 0,
        "mixed": 0,
    }


def test_invalid_selected_code_type_falls_back_to_all():
    df = _sample_pairs()

    filtered = _apply_focus_related_service_filter(
        df, focus_service="svc-a", related_service="svc-b"
    )
    counts = _calculate_code_type_counts(filtered)

    assert _normalize_code_type_selection("mixed", counts) == "all"
    assert _normalize_code_type_selection("data", counts) == "data"


def test_code_type_counts_are_clone_set_based():
    df = pd.DataFrame(
        [
            {
                "clone_id": 10,
                "service_x": "svc-a",
                "service_y": "svc-a",
                "file_type_x": "logic",
                "file_type_y": "logic",
            },
            {
                "clone_id": 10,
                "service_x": "svc-a",
                "service_y": "svc-b",
                "file_type_x": "data",
                "file_type_y": "config",
            },
            {
                "clone_id": 11,
                "service_x": "svc-a",
                "service_y": "svc-c",
                "file_type_x": "test",
                "file_type_y": "logic",
            },
        ]
    )

    counts = _calculate_code_type_counts(df)

    assert counts == {
        "all": 2,
        "logic": 1,
        "data": 0,
        "test": 0,
        "config": 0,
        "mixed": 1,
    }


def test_code_type_pair_counts_are_available():
    df = pd.DataFrame(
        [
            {
                "clone_id": 10,
                "service_x": "svc-a",
                "service_y": "svc-a",
                "file_type_x": "logic",
                "file_type_y": "logic",
            },
            {
                "clone_id": 10,
                "service_x": "svc-a",
                "service_y": "svc-b",
                "file_type_x": "data",
                "file_type_y": "config",
            },
            {
                "clone_id": 11,
                "service_x": "svc-a",
                "service_y": "svc-c",
                "file_type_x": "test",
                "file_type_y": "logic",
            },
        ]
    )

    counts = _calculate_code_type_pair_counts(df)

    assert counts == {
        "all": 3,
        "logic": 2,
        "data": 0,
        "test": 0,
        "config": 0,
        "mixed": 1,
    }


def test_build_code_type_buttons_shows_all_categories_by_default():
    buttons = _build_code_type_buttons()
    assert len(buttons) == 6

    labels = [btn.children for btn in buttons]
    assert labels == [
        "All (0)",
        "Logic (0)",
        "Data (0)",
        "Mixed (0)",
        "Test (0)",
        "Config (0)",
    ]


def test_build_code_type_buttons_invalid_active_falls_back_to_all():
    buttons = _build_code_type_buttons(
        active_code_type="logic",
        counts={
            "all": 0,
            "logic": 0,
            "data": 0,
            "test": 0,
            "config": 0,
            "mixed": 0,
        },
        pair_counts={
            "all": 0,
            "logic": 0,
            "data": 0,
            "test": 0,
            "config": 0,
            "mixed": 0,
        },
    )

    all_button = buttons[0]
    logic_button = buttons[1]

    assert all_button.style["fontWeight"] == "600"
    assert logic_button.style["fontWeight"] == "500"


def test_clone_id_options_include_comod_count_in_compact_label():
    options = generate_cross_service_filter_options(
        [
            {
                "clone_id": 161,
                "service_count": 29,
                "pair_count": 406,
                "comod_count": 8,
                "code_type": "Logic",
                "services": ["svc-a"],
            }
        ]
    )

    assert options[1]["label"] == "#161 29 svcs 406 pairs 🔄8 · Logic"


def test_apply_clone_id_filter_numeric_value_matches_clone_id():
    df = _sample_pairs()

    filtered = _apply_clone_id_filter(df, "2")

    assert len(filtered) == 1
    assert int(filtered.iloc[0]["clone_id"]) == 2


def test_apply_clone_id_filter_clone_prefix_matches_clone_id():
    df = _sample_pairs()

    filtered = _apply_clone_id_filter(df, "clone_3")

    assert len(filtered) == 1
    assert int(filtered.iloc[0]["clone_id"]) == 3


def test_apply_clone_id_filter_all_returns_original_df():
    df = _sample_pairs()

    filtered = _apply_clone_id_filter(df, "all")

    assert len(filtered) == len(df)


def test_apply_clone_id_filter_no_digit_fallback():
    df = _sample_pairs()

    filtered = _apply_clone_id_filter(df, "clone_x")

    assert len(filtered) == len(df)
