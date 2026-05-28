"""load_clone_metrics のテスト."""

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_dest(tmp_path, monkeypatch):
    """DEST_CLONE_METRICS を tmp_path 配下へ向け, 実 dest/ から隔離する."""
    import visualize.paths as paths_mod
    from visualize.data_loader import csv_loader as csv_mod

    target = tmp_path / "dest" / "clone_metrics"
    monkeypatch.setattr(paths_mod, "DEST_CLONE_METRICS", target, raising=False)
    monkeypatch.setattr(csv_mod, "DEST_CLONE_METRICS", target, raising=False)


def _sample_metrics() -> dict:
    """テスト用メトリクスデータ."""
    return {
        "service": [
            {
                "service": "svc-a",
                "clone_set_count": 3,
                "total_clone_line_count": 100,
                "clone_avg_line_count": 33.3,
                "clone_file_count": 5,
                "roc": 0.05,
                "comod_count": 2,
                "comod_other_service_count": 1,
            }
        ],
        "clone_set": [
            {
                "clone_id": "1",
                "service_count": 2,
                "cross_service_fragment_count": 3,
                "cross_service_fragment_ratio": 0.75,
                "cross_service_line_count": 50,
                "cross_service_scale": 2,
                "cross_service_element_count": 4,
                "comod_count": 1,
                "comod_fragment_count": 2,
                "comod_fragment_ratio": 0.5,
            }
        ],
        "file": [
            {
                "file_path": "src/main.java",
                "service": "svc-a",
                "sharing_service_count": 1,
                "total_service_count": 3,
                "cross_service_clone_set_count": 1,
                "cross_service_clone_set_ratio": 0.5,
                "sharing_service_ratio": 0.333,
                "cross_service_line_count": 20,
                "cross_service_comod_count": 1,
                "comod_shared_service_count": 1,
            }
        ],
    }


def test_load_clone_metrics_returns_data(tmp_path: Path, monkeypatch):
    """JSON が存在する場合, 辞書として読み込める."""
    from visualize.data_loader.csv_loader import load_clone_metrics

    metrics_dir = tmp_path / "dest" / "clone_metrics"
    metrics_dir.mkdir(parents=True)
    metrics_file = metrics_dir / "owner.repo_Java.json"
    metrics_file.write_text(json.dumps(_sample_metrics()), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    result = load_clone_metrics("owner.repo", "Java")
    assert result is not None
    assert len(result["service"]) == 1
    assert result["service"][0]["service"] == "svc-a"
    assert len(result["clone_set"]) == 1
    assert len(result["file"]) == 1


def test_load_clone_metrics_missing_file(tmp_path: Path, monkeypatch):
    """ファイルが存在しない場合 None を返す."""
    from visualize.data_loader.csv_loader import load_clone_metrics

    monkeypatch.chdir(tmp_path)
    result = load_clone_metrics("nonexistent", "Java")
    assert result is None


def test_load_clone_metrics_invalid_json(tmp_path: Path, monkeypatch):
    """不正な JSON の場合 None を返す."""
    from visualize.data_loader.csv_loader import load_clone_metrics

    metrics_dir = tmp_path / "dest" / "clone_metrics"
    metrics_dir.mkdir(parents=True)
    metrics_file = metrics_dir / "owner.repo_Java_all.json"
    metrics_file.write_text("{invalid json", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    result = load_clone_metrics("owner.repo", "Java")
    assert result is None


def test_load_clone_metrics_custom_filter_type(tmp_path: Path, monkeypatch):
    """別のファイル名パターンでも読み込める."""
    from visualize.data_loader.csv_loader import load_clone_metrics

    metrics_dir = tmp_path / "dest" / "clone_metrics"
    metrics_dir.mkdir(parents=True)
    metrics_file = metrics_dir / "owner.repo_Python.json"
    metrics_file.write_text(json.dumps(_sample_metrics()), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    result = load_clone_metrics("owner.repo", "Python")
    assert result is not None
    assert len(result["service"]) == 1
