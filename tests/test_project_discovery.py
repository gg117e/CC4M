"""project_discovery のプロジェクト発見ロジックのテスト."""

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_dest(tmp_path, monkeypatch):
    """DEST_* 定数を tmp_path 配下へ向け, 実 dest/ から隔離する.

    project_discovery は project_root 絶対パスの DEST_* 定数を参照するため,
    monkeypatch.chdir だけでは隔離できない. paths モジュールと
    project_discovery モジュール両方の定数を差し替える.
    """
    import visualize.paths as paths_mod
    from visualize.data_loader import project_discovery as pd_mod

    dest = tmp_path / "dest"
    subdirs = {
        "DEST_SCATTER": "scatter",
        "DEST_SERVICES_JSON": "services_json",
        "DEST_ENRICHED_FRAGMENTS": "enriched_fragments",
        "DEST_CSV": "csv",
        "DEST_ANALYSIS_PARAMS": "analysis_params",
        "DEST_CLONE_METRICS": "clone_metrics",
    }
    for const, sub in subdirs.items():
        target = dest / sub
        monkeypatch.setattr(paths_mod, const, target, raising=False)
        monkeypatch.setattr(pd_mod, const, target, raising=False)


def _make_services_json(tmp_path: Path, project: str, languages: dict) -> Path:
    """テスト用の services.json を生成する."""
    sj_dir = tmp_path / "dest" / "services_json"
    sj_dir.mkdir(parents=True, exist_ok=True)
    sj_path = sj_dir / f"{project}.json"
    data = {
        "services": {},
        "URL": f"https://github.com/{project.replace('.', '/')}",
        "language_stats": {
            lang: {
                "services": {f"svc-{i}": {"file_count": 10, "total_loc": 1000} for i in range(svc_count)},
                "total_files": 30,
                "total_loc": 3000,
            }
            for lang, svc_count in languages.items()
        },
    }
    sj_path.write_text(json.dumps(data), encoding="utf-8")
    return sj_path


def _make_scatter_csv(tmp_path: Path, project: str, filename: str) -> Path:
    """テスト用の scatter CSV ダミーを生成する."""
    csv_dir = tmp_path / "dest" / "scatter" / project / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    csv_path = csv_dir / filename
    csv_path.write_text("header\nrow", encoding="utf-8")
    return csv_path


def test_get_project_names_includes_services_json(tmp_path: Path, monkeypatch):
    """services_json のみにあるプロジェクトも列挙される."""
    from visualize.data_loader.project_discovery import get_project_names

    monkeypatch.chdir(tmp_path)

    # scatter CSV を持つプロジェクト
    _make_scatter_csv(
        tmp_path,
        "owner.repoA",
        "repoA_normal_50_filtered_cloneset_merge_20260101_Java.csv",
    )
    # services_json のみのプロジェクト
    _make_services_json(tmp_path, "owner.repoB", {"Python": 3})

    names = get_project_names()
    values = {n["value"] for n in names}
    assert "owner.repoA" in values
    assert "owner.repoB" in values


def test_get_project_names_no_data(tmp_path: Path, monkeypatch):
    """dest がない場合は空リストを返す."""
    from visualize.data_loader.project_discovery import get_project_names

    monkeypatch.chdir(tmp_path)
    assert get_project_names() == []


def test_get_project_names_from_enriched_fragments(tmp_path: Path, monkeypatch):
    """enriched_fragments のみでもプロジェクトが列挙される."""
    from visualize.data_loader.project_discovery import get_project_names

    monkeypatch.chdir(tmp_path)
    enriched = tmp_path / "dest" / "enriched_fragments" / "owner.repoC"
    enriched.mkdir(parents=True)
    (enriched / "Java.csv").write_text("dummy", encoding="utf-8")

    names = get_project_names()
    values = {n["value"] for n in names}
    assert "owner.repoC" in values


def test_get_project_names_from_dest_csv(tmp_path: Path, monkeypatch):
    """dest/csv のみでもプロジェクトが列挙される."""
    from visualize.data_loader.project_discovery import get_project_names

    monkeypatch.chdir(tmp_path)
    csv_dir = tmp_path / "dest" / "csv" / "owner.repoD"
    csv_dir.mkdir(parents=True)
    (csv_dir / "Python.csv").write_text("dummy", encoding="utf-8")

    names = get_project_names()
    values = {n["value"] for n in names}
    assert "owner.repoD" in values


def test_get_csv_options_services_json_fallback(tmp_path: Path, monkeypatch):
    """scatter CSV がないプロジェクトは services.json の language_stats から選択肢を生成する."""
    from visualize.data_loader.project_discovery import get_csv_options_for_project

    monkeypatch.chdir(tmp_path)
    _make_services_json(tmp_path, "owner.repoB", {"Python": 3, "Java": 2})

    options = get_csv_options_for_project("owner.repoB")
    assert len(options) == 2

    languages = {o["language"] for o in options}
    assert languages == {"Python", "Java"}

    # value は latest 形式
    for opt in options:
        assert "|||latest|||" in opt["value"]


def test_get_csv_options_scatter_preferred(tmp_path: Path, monkeypatch):
    """scatter CSV がある場合はそちらを優先する."""
    from visualize.data_loader.project_discovery import get_csv_options_for_project

    monkeypatch.chdir(tmp_path)
    _make_scatter_csv(
        tmp_path,
        "owner.repoA",
        "repoA_normal_50_filtered_cloneset_merge_20260101_Java.csv",
    )
    _make_services_json(tmp_path, "owner.repoA", {"Java": 2})

    options = get_csv_options_for_project("owner.repoA")
    # scatter CSV ベースのオプション (scatter_file: prefix)
    assert len(options) == 1
    assert "scatter_file:" in options[0]["value"]
