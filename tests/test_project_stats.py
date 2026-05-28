"""project_stats アグリゲータのテスト.

services.json と clone_metrics_<lang>.json をテスト用に書き出し,
load_project_stats が KPI / 言語別 / サービス別を正しく集計するか確認する.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _services_json() -> dict:
    return {
        "URL": "https://example.com/foo.bar",
        "services": {
            "svc-a/": ["svc-a"],
            "svc-b/": ["svc-b"],
        },
        "language_stats": {
            "Java": {
                "services": {
                    "svc-a": {"file_count": 4, "total_loc": 400},
                    "svc-b": {"file_count": 2, "total_loc": 100},
                },
                "total_files": 6,
                "total_loc": 500,
                "unresolved_files": 0,
                "unresolved_loc": 0,
            },
            "Go": {
                "services": {
                    "svc-b": {"file_count": 1, "total_loc": 50},
                },
                "total_files": 1,
                "total_loc": 50,
                "unresolved_files": 0,
                "unresolved_loc": 0,
            },
        },
    }


def _java_metrics() -> dict:
    return {
        "service": [
            {
                "service": "svc-a",
                "clone_set_count": 3,
                "inter_clone_set_count": 2,
                "total_clone_line_count": 200,
                "clone_avg_line_count": 10.0,
                "clone_file_count": 3,
                "roc": 0.5,
                "comod_count": 1,
                "comod_other_service_count": 0,
            },
            {
                "service": "svc-b",
                "clone_set_count": 1,
                "inter_clone_set_count": 1,
                "total_clone_line_count": 20,
                "clone_avg_line_count": 20.0,
                "clone_file_count": 1,
                "roc": 0.2,
                "comod_count": 0,
                "comod_other_service_count": 0,
            },
        ],
        "clone_set": [{"clone_id": "1"}, {"clone_id": "2"}, {"clone_id": "3"}],
        "file": [],
    }


def _go_metrics() -> dict:
    return {
        "service": [
            {
                "service": "svc-b",
                "clone_set_count": 2,
                "inter_clone_set_count": 0,
                "total_clone_line_count": 10,
                "clone_avg_line_count": 5.0,
                "clone_file_count": 1,
                "roc": 0.2,
                "comod_count": 0,
                "comod_other_service_count": 0,
            }
        ],
        "clone_set": [{"clone_id": "1"}, {"clone_id": "2"}],
        "file": [],
    }


def _write_scatter_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["clone_id", "comodification_count"]
    lines = [",".join(fields)]
    for row in rows:
        lines.append(",".join(str(row.get(field, "")) for field in fields))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def fake_dest(tmp_path, monkeypatch):
    """dest/services_json と dest/clone_metrics をテスト用に差し替える."""
    services_dir = tmp_path / "services_json"
    metrics_dir = tmp_path / "clone_metrics"
    scatter_root = tmp_path / "scatter"
    services_dir.mkdir()
    metrics_dir.mkdir()

    project = "owner.repo"
    _write_json(services_dir / f"{project}.json", _services_json())
    java_metrics = _java_metrics()
    java_metrics["clone_set"] = [
        {"clone_id": "1", "comod_count": 2},
        {"clone_id": "2", "comod_count": 0},
        {"clone_id": "3", "comod_count": 1},
    ]
    go_metrics = _go_metrics()
    go_metrics["clone_set"] = [
        {"clone_id": "1", "comod_count": 0},
        {"clone_id": "2", "comod_count": 0},
    ]
    _write_json(metrics_dir / f"{project}_Java.json", java_metrics)
    _write_json(metrics_dir / f"{project}_Go.json", go_metrics)
    _write_scatter_csv(
        scatter_root
        / project
        / "csv"
        / "owner.repo_normal_50_filtered_cloneset_merge_20260520_Java.csv",
        [
            {"clone_id": "old", "comodification_count": 0},
        ],
    )
    _write_scatter_csv(
        scatter_root
        / project
        / "csv"
        / "owner.repo_normal_50_filtered_cloneset_merge_20260521_Java.csv",
        [
            {"clone_id": "1", "comodification_count": 1},
            {"clone_id": "1", "comodification_count": 1},
            {"clone_id": "2", "comodification_count": 0},
            {"clone_id": "3", "comodification_count": 0},
        ],
    )
    _write_scatter_csv(
        scatter_root
        / project
        / "csv"
        / "owner.repo_normal_50_filtered_cloneset_merge_20260521_Go.csv",
        [
            {"clone_id": "1", "comodification_count": 0},
        ],
    )

    from src.visualize.data_loader import project_stats as module

    monkeypatch.setattr(module, "DEST_CLONE_METRICS", metrics_dir)
    monkeypatch.setattr(
        module,
        "get_services_json_path",
        lambda p: services_dir / f"{p}.json",
    )
    monkeypatch.setattr(
        module,
        "get_clone_metrics_path",
        lambda p, lang: metrics_dir / f"{p}_{lang}.json",
    )
    monkeypatch.setattr(
        module,
        "get_scatter_csv_dir",
        lambda p: scatter_root / p / "csv",
    )
    return project


def test_load_project_stats_returns_kpi(fake_dest):
    from src.visualize.data_loader.project_stats import load_project_stats

    stats = load_project_stats(fake_dest)
    assert stats is not None
    kpi = stats.kpi
    # svc-a (Java only) + svc-b (Java + Go)
    assert kpi.n_services == 2
    assert kpi.n_files == 7  # 6 Java + 1 Go
    assert kpi.n_clone_sets == 5  # 3 Java + 2 Go
    assert kpi.total_loc == 550
    assert kpi.total_clone_loc == 230  # 200 + 20 + 10
    assert kpi.roc_pct == pytest.approx(230 / 550 * 100, abs=0.05)


def test_load_project_stats_language_breakdown(fake_dest):
    from src.visualize.data_loader.project_stats import load_project_stats

    stats = load_project_stats(fake_dest)
    by_lang = {lang.language: lang for lang in stats.languages}
    assert set(by_lang) == {"Java", "Go"}

    java = by_lang["Java"]
    assert java.n_services == 2
    assert java.n_files == 6
    assert java.total_loc == 500
    assert java.n_clone_sets == 3
    assert java.n_clone_pairs == 4
    assert java.n_comod_clone_sets == 2
    assert java.n_comod_clone_pairs == 2
    assert java.total_clone_loc == 220  # 200 + 20

    go = by_lang["Go"]
    assert go.n_services == 1
    assert go.n_files == 1
    assert go.total_loc == 50
    assert go.n_clone_sets == 2
    assert go.n_clone_pairs == 1
    assert go.n_comod_clone_sets == 0
    assert go.n_comod_clone_pairs == 0
    assert go.total_clone_loc == 10


def test_load_project_stats_service_breakdown(fake_dest):
    from src.visualize.data_loader.project_stats import load_project_stats

    stats = load_project_stats(fake_dest)
    by_svc = {s.service: s for s in stats.services}
    assert set(by_svc) == {"svc-a", "svc-b"}

    a = by_svc["svc-a"]
    assert a.languages == ("Java",)
    assert a.n_files == 4
    assert a.total_loc == 400
    assert a.n_clone_sets == 3
    assert a.total_clone_loc == 200

    b = by_svc["svc-b"]
    assert b.languages == ("Go", "Java")
    assert b.n_files == 3  # 2 Java + 1 Go
    assert b.total_loc == 150  # 100 + 50
    assert b.n_clone_sets == 3  # 1 Java + 2 Go
    assert b.total_clone_loc == 30  # 20 + 10


def test_load_project_stats_services_sorted_by_clone_sets(fake_dest):
    from src.visualize.data_loader.project_stats import load_project_stats

    stats = load_project_stats(fake_dest)
    counts = [s.n_clone_sets for s in stats.services]
    assert counts == sorted(counts, reverse=True)


def test_extract_project_from_composite_value():
    from src.visualize.callbacks.statistics_callbacks import _extract_project

    assert (
        _extract_project("owner.repo|||scatter_file:foo.csv|||Java")
        == "owner.repo"
    )
    assert _extract_project("owner.repo") == "owner.repo"
    assert _extract_project("") is None
    assert _extract_project(None) is None


def test_language_table_rows_include_pair_and_comod_columns(fake_dest):
    from src.visualize.callbacks.statistics_callbacks import _language_table_rows
    from src.visualize.data_loader.project_stats import load_project_stats

    stats = load_project_stats(fake_dest)
    rows = _language_table_rows(stats.languages)
    java = next(row for row in rows if row["language"] == "Java")

    assert "cs_per_service" not in java
    assert "loc_per_file" not in java
    assert java["n_clone_pairs"] == 4
    assert java["n_comod_clone_sets"] == 2
    assert java["n_comod_clone_pairs"] == 2


def test_load_project_stats_missing_services_json_returns_none(tmp_path, monkeypatch):
    from src.visualize.data_loader import project_stats as module
    from src.visualize.data_loader.project_stats import load_project_stats

    monkeypatch.setattr(module, "DEST_CLONE_METRICS", tmp_path / "clone_metrics")
    monkeypatch.setattr(
        module,
        "get_services_json_path",
        lambda p: tmp_path / f"{p}.json",
    )
    assert load_project_stats("missing.proj") is None
