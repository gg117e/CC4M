"""build_enriched_fragments モジュールのテスト."""

import json
from pathlib import Path

import pytest

from modules.visualization.build_enriched_fragments import (
    EnrichedFragment,
    build_enriched_fragment,
    build_enriched_fragments_for_language,
)
from modules.visualization.build_scatter_dataset import FragmentRow


# ---------------------------------------------------------------------------
# build_enriched_fragment (純粋関数)
# ---------------------------------------------------------------------------


class TestBuildEnrichedFragment:
    """build_enriched_fragment のテスト."""

    def test_basic(self) -> None:
        """正常な断片から EnrichedFragment を生成する."""
        frag = FragmentRow(
            clone_id="42",
            index=0,
            file_path="src/app.py",
            start_line=10,
            end_line=20,
            modification_raw='[{"type":"modified","commit":"abc123"}]',
        )

        result = build_enriched_fragment(
            frag,
            norm_path="src/app.py",
            service="web",
            file_id=5,
            commits={"abc123"},
            file_type="logic",
        )

        assert isinstance(result, EnrichedFragment)
        assert result.clone_id == "42"
        assert result.fragment_index == 0
        assert result.file_path == "src/app.py"
        assert result.file_id == 5
        assert result.service == "web"
        assert result.start_line == 10
        assert result.end_line == 20
        assert result.line_count == 11
        assert result.file_type == "logic"
        assert result.modified_commits == '["abc123"]'
        assert result.modified_count == 1

    def test_empty_commits(self) -> None:
        """修正コミットが無い場合."""
        frag = FragmentRow(
            clone_id="1",
            index=0,
            file_path="x.py",
            start_line=1,
            end_line=1,
            modification_raw="",
        )

        result = build_enriched_fragment(
            frag,
            norm_path="x.py",
            service="",
            file_id=-1,
            commits=set(),
            file_type="logic",
        )

        assert result.line_count == 1
        assert result.modified_commits == "[]"
        assert result.modified_count == 0

    def test_multiple_commits_sorted(self) -> None:
        """修正コミットが複数ある場合, JSON 中でソートされること."""
        frag = FragmentRow(
            clone_id="1",
            index=0,
            file_path="x.py",
            start_line=1,
            end_line=5,
            modification_raw="",
        )

        result = build_enriched_fragment(
            frag,
            norm_path="x.py",
            service="svc",
            file_id=0,
            commits={"zzz", "aaa", "mmm"},
            file_type="logic",
        )

        parsed = json.loads(result.modified_commits)
        assert parsed == ["aaa", "mmm", "zzz"]
        assert result.modified_count == 3


# ---------------------------------------------------------------------------
# build_enriched_fragments_for_language (結合テスト)
# ---------------------------------------------------------------------------


def _setup_project(
    tmp_path: Path,
    project_name: str = "owner.repo",
    language: str = "Python",
) -> Path:
    """テスト用のプロジェクトディレクトリ構造を作成する.

    Returns:
        project_root (= tmp_path)
    """
    project_root = tmp_path

    # dest/projects/<project>/
    workdir = project_root / "dest/projects" / project_name
    workdir.mkdir(parents=True)

    # dest/analyzed_commits/<project>.json
    ac_dir = project_root / "dest/analyzed_commits"
    ac_dir.mkdir(parents=True)
    (ac_dir / f"{project_name}.json").write_text(
        json.dumps(["abc123def"]), encoding="utf-8"
    )

    # dest/clones_json/<project>/<commit>/<lang>.json
    clones_dir = (
        project_root / "dest/clones_json" / project_name / "abc123def"
    )
    clones_dir.mkdir(parents=True)
    clones_json = {
        "file_data": [
            {
                "file_id": 0,
                "file_path": f"{workdir}/services/alpha/main.py",
                "loc": 100,
                "token_count": 500,
            },
            {
                "file_id": 1,
                "file_path": f"{workdir}/services/alpha/util.py",
                "loc": 50,
                "token_count": 200,
            },
            {
                "file_id": 2,
                "file_path": f"{workdir}/services/beta/app.py",
                "loc": 200,
                "token_count": 800,
            },
        ],
        "clone_sets": [],
    }
    (clones_dir / f"{language}.json").write_text(
        json.dumps(clones_json), encoding="utf-8"
    )

    # dest/services_json/<project>.json
    svc_dir = project_root / "dest/services_json"
    svc_dir.mkdir(parents=True)
    services_data = {
        "services": {
            "services/alpha/": ["svc_alpha"],
            "services/beta/": ["svc_beta"],
        },
        "URL": "https://github.com/owner/repo",
    }
    (svc_dir / f"{project_name}.json").write_text(
        json.dumps(services_data), encoding="utf-8"
    )

    # dest/ms_detection/ (空でOK, services_json が優先される)
    ms_dir = project_root / "dest/ms_detection"
    ms_dir.mkdir(parents=True)

    # dest/csv/<project>/<lang>.csv (断片CSV, delimiter=;)
    csv_dir = project_root / "dest/csv" / project_name
    csv_dir.mkdir(parents=True)
    fragment_lines = [
        "clone_id;index;file_path;start_line;end_line;start_column;end_column;modification",
        '1;0;services/alpha/main.py;10;20;0;0;[{"type":"modified","commit":"c1"}]',
        '1;1;services/beta/app.py;30;45;0;0;[{"type":"modified","commit":"c1"},{"type":"modified","commit":"c2"}]',
        '2;0;services/alpha/main.py;50;55;0;0;[]',
        '2;1;services/alpha/util.py;1;10;0;0;[{"type":"modified","commit":"c3"}]',
    ]
    (csv_dir / f"{language}.csv").write_text(
        "\n".join(fragment_lines), encoding="utf-8"
    )

    return project_root


class TestBuildEnrichedFragmentsForLanguage:
    """build_enriched_fragments_for_language の結合テスト."""

    def test_generates_csv(self, tmp_path: Path) -> None:
        """enriched_fragments CSV が正しく生成されること."""
        project_root = _setup_project(tmp_path)
        out_dir = project_root / "dest/enriched_fragments"

        result_path = build_enriched_fragments_for_language(
            project_name="owner.repo",
            language="Python",
            filter_type=None,
            project_root=project_root,
            out_dir=out_dir,
            ms_detection_dir=project_root / "dest/ms_detection",
        )

        assert result_path.exists()
        lines = result_path.read_text(encoding="utf-8").strip().splitlines()
        # ヘッダ + 4 断片行
        assert len(lines) == 5, f"Expected 5 lines, got {len(lines)}: {lines}"

        # ヘッダ検証
        header = lines[0]
        assert "clone_id" in header
        assert "fragment_index" in header
        assert "service" in header
        assert "modified_commits" in header

        # clone_id=1 の断片 1 行目
        row1 = lines[1].split(",")
        assert row1[0] == "1"  # clone_id
        assert row1[1] == "0"  # fragment_index
        # service が解決されていること
        assert row1[4] in ("svc_alpha", "svc_beta")

    def test_services_json_enriched(self, tmp_path: Path) -> None:
        """services.json に language_stats が追記されること."""
        project_root = _setup_project(tmp_path)
        out_dir = project_root / "dest/enriched_fragments"

        build_enriched_fragments_for_language(
            project_name="owner.repo",
            language="Python",
            filter_type=None,
            project_root=project_root,
            out_dir=out_dir,
            ms_detection_dir=project_root / "dest/ms_detection",
        )

        svc_json_path = project_root / "dest/services_json/owner.repo.json"
        result = json.loads(svc_json_path.read_text(encoding="utf-8"))
        assert "language_stats" in result
        assert "Python" in result["language_stats"]
        py_stats = result["language_stats"]["Python"]
        assert py_stats["total_files"] == 3
        assert py_stats["total_loc"] == 350  # 100 + 50 + 200

    def test_enrich_services_false(self, tmp_path: Path) -> None:
        """enrich_services=False の場合, services.json は変更されない."""
        project_root = _setup_project(tmp_path)
        out_dir = project_root / "dest/enriched_fragments"
        svc_json_path = project_root / "dest/services_json/owner.repo.json"
        original = svc_json_path.read_text(encoding="utf-8")

        build_enriched_fragments_for_language(
            project_name="owner.repo",
            language="Python",
            filter_type=None,
            project_root=project_root,
            out_dir=out_dir,
            ms_detection_dir=project_root / "dest/ms_detection",
            enrich_services=False,
        )

        assert svc_json_path.read_text(encoding="utf-8") == original

    def test_missing_fragment_csv_raises(self, tmp_path: Path) -> None:
        """断片 CSV が無い場合に FileNotFoundError."""
        project_root = _setup_project(tmp_path)
        # 断片CSVを削除
        csv_file = project_root / "dest/csv/owner.repo/Python.csv"
        csv_file.unlink()

        with pytest.raises(FileNotFoundError, match="fragment csv"):
            build_enriched_fragments_for_language(
                project_name="owner.repo",
                language="Python",
                filter_type=None,
                project_root=project_root,
                out_dir=project_root / "dest/enriched_fragments",
                ms_detection_dir=project_root / "dest/ms_detection",
            )

    def test_line_count_correct(self, tmp_path: Path) -> None:
        """line_count = end_line - start_line + 1 が正しいこと."""
        project_root = _setup_project(tmp_path)
        out_dir = project_root / "dest/enriched_fragments"

        result_path = build_enriched_fragments_for_language(
            project_name="owner.repo",
            language="Python",
            filter_type=None,
            project_root=project_root,
            out_dir=out_dir,
            ms_detection_dir=project_root / "dest/ms_detection",
        )

        lines = result_path.read_text(encoding="utf-8").strip().splitlines()
        # 最初のデータ行: clone_id=1, index=0, start=10, end=20 → line_count=11
        row = lines[1].split(",")
        start_line = int(row[5])
        end_line = int(row[6])
        line_count = int(row[7])
        assert line_count == end_line - start_line + 1

    def test_modified_count_matches_commits(self, tmp_path: Path) -> None:
        """modified_count が modified_commits のJSON要素数と一致すること."""
        import csv

        project_root = _setup_project(tmp_path)
        out_dir = project_root / "dest/enriched_fragments"

        result_path = build_enriched_fragments_for_language(
            project_name="owner.repo",
            language="Python",
            filter_type=None,
            project_root=project_root,
            out_dir=out_dir,
            ms_detection_dir=project_root / "dest/ms_detection",
        )

        with result_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mc_json = row["modified_commits"]
                mc_count = int(row["modified_count"])
                mc_list = json.loads(mc_json)
                assert len(mc_list) == mc_count, (
                    f"clone_id={row['clone_id']} index={row['fragment_index']}: "
                    f"len(commits)={len(mc_list)} != modified_count={mc_count}"
                )
