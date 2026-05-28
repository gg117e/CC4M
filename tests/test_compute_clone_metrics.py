"""compute_clone_metrics の単体テスト."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from modules.visualization.compute_clone_metrics import (
    CloneSetMetrics,
    FileMetrics,
    ServiceMetrics,
    _compute_comod_commits_for_clone_set,
    _parse_commits,
    compute_all_metrics,
    compute_clone_set_metrics,
    compute_file_metrics,
    compute_service_metrics,
    load_enriched_fragments,
    load_language_stats,
)


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """テスト用 DataFrame を構築する."""
    df = pd.DataFrame(rows)
    if df.empty:
        # 空 DataFrame でもカラムを保証
        df = pd.DataFrame(columns=[
            "clone_id", "fragment_index", "file_path", "file_id",
            "service", "start_line", "end_line", "line_count",
            "file_type", "modified_commits", "modified_count",
        ])
        return df
    df["service"] = df["service"].fillna("")
    df["modified_commits"] = df["modified_commits"].fillna("[]")
    return df


def _frag(
    clone_id: str = "C1",
    fragment_index: int = 0,
    file_path: str = "svc_a/main.py",
    file_id: int = 1,
    service: str = "svc_a",
    start_line: int = 1,
    end_line: int = 10,
    line_count: int = 10,
    file_type: str = "logic",
    modified_commits: str = "[]",
    modified_count: int = 0,
) -> dict:
    """1 フラグメント行を辞書で返す."""
    return {
        "clone_id": clone_id,
        "fragment_index": fragment_index,
        "file_path": file_path,
        "file_id": file_id,
        "service": service,
        "start_line": start_line,
        "end_line": end_line,
        "line_count": line_count,
        "file_type": file_type,
        "modified_commits": modified_commits,
        "modified_count": modified_count,
    }


# ---------------------------------------------------------------------------
# _parse_commits
# ---------------------------------------------------------------------------


class TestParseCommits:
    def test_empty_string(self) -> None:
        assert _parse_commits("") == set()

    def test_empty_list(self) -> None:
        assert _parse_commits("[]") == set()

    def test_valid(self) -> None:
        assert _parse_commits('["abc", "def"]') == {"abc", "def"}

    def test_invalid_json(self) -> None:
        assert _parse_commits("not-json") == set()


# ---------------------------------------------------------------------------
# _compute_comod_commits_for_clone_set
# ---------------------------------------------------------------------------


class TestComodCommits:
    def test_no_overlap(self) -> None:
        df = _make_df([
            _frag(fragment_index=0, modified_commits='["c1"]'),
            _frag(fragment_index=1, modified_commits='["c2"]'),
        ])
        assert _compute_comod_commits_for_clone_set(df) == set()

    def test_overlap(self) -> None:
        df = _make_df([
            _frag(fragment_index=0, modified_commits='["c1", "c2"]'),
            _frag(fragment_index=1, modified_commits='["c1"]'),
        ])
        assert _compute_comod_commits_for_clone_set(df) == {"c1"}

    def test_three_fragments_partial(self) -> None:
        df = _make_df([
            _frag(fragment_index=0, modified_commits='["c1"]'),
            _frag(fragment_index=1, modified_commits='["c1", "c2"]'),
            _frag(fragment_index=2, modified_commits='["c2"]'),
        ])
        result = _compute_comod_commits_for_clone_set(df)
        assert result == {"c1", "c2"}


# ---------------------------------------------------------------------------
# compute_service_metrics
# ---------------------------------------------------------------------------


class TestServiceMetrics:
    def test_basic(self) -> None:
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   file_path="svc_a/a.py", line_count=10),
            _frag(clone_id="C1", fragment_index=1, service="svc_b",
                   file_path="svc_b/b.py", start_line=1, end_line=20,
                   line_count=20),
            _frag(clone_id="C2", fragment_index=0, service="svc_a",
                   file_path="svc_a/c.py", start_line=1, end_line=5,
                   line_count=5),
        ])
        lang_stats = {
            "services": {
                "svc_a": {"file_count": 10, "total_loc": 100},
                "svc_b": {"file_count": 5, "total_loc": 200},
            }
        }
        result = compute_service_metrics(df, lang_stats)
        assert len(result) == 2

        svc_a = next(m for m in result if m.service == "svc_a")
        assert svc_a.clone_set_count == 2  # C1, C2
        assert svc_a.total_clone_line_count == 15  # 10 + 5
        assert svc_a.clone_file_count == 2  # a.py, c.py
        assert svc_a.roc == round(15 / 100, 6)

        svc_b = next(m for m in result if m.service == "svc_b")
        assert svc_b.clone_set_count == 1  # C1
        assert svc_b.roc == round(20 / 200, 6)

    def test_empty_df(self) -> None:
        df = _make_df([])
        assert compute_service_metrics(df, {}) == []

    def test_all_unresolved(self) -> None:
        df = _make_df([
            _frag(service="", file_path="unknown.py"),
        ])
        assert compute_service_metrics(df, {}) == []

    def test_roc_no_loc(self) -> None:
        """language_stats に total_loc がない場合, ROC = 0."""
        df = _make_df([
            _frag(service="svc_a", line_count=10),
        ])
        result = compute_service_metrics(df, {})
        assert result[0].roc == 0.0

    def test_comod_count(self) -> None:
        """サービス A に属するクローンセットの同時修正数."""
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   file_path="svc_a/a.py",
                   modified_commits='["h1", "h2"]', modified_count=2),
            _frag(clone_id="C1", fragment_index=1, service="svc_b",
                   file_path="svc_b/b.py",
                   modified_commits='["h1"]', modified_count=1),
        ])
        result = compute_service_metrics(df, {})
        svc_a = next(m for m in result if m.service == "svc_a")
        assert svc_a.comod_count == 1  # h1 is comod
        assert svc_a.comod_other_service_count == 1  # svc_b

    def test_comod_count_requires_service_participation(self) -> None:
        """同じクローンセット内の別サービス同士の同時修正は数えない."""
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   file_path="svc_a/a.py", modified_commits="[]"),
            _frag(clone_id="C1", fragment_index=1, service="svc_b",
                   file_path="svc_b/b.py", modified_commits='["h1"]',
                   modified_count=1),
            _frag(clone_id="C1", fragment_index=2, service="svc_c",
                   file_path="svc_c/c.py", modified_commits='["h1"]',
                   modified_count=1),
        ])
        result = compute_service_metrics(df, {})
        svc_a = next(m for m in result if m.service == "svc_a")
        svc_b = next(m for m in result if m.service == "svc_b")

        assert svc_a.comod_count == 0
        assert svc_a.comod_other_service_count == 0
        assert svc_b.comod_count == 1
        assert svc_b.comod_other_service_count == 1


# ---------------------------------------------------------------------------
# compute_clone_set_metrics
# ---------------------------------------------------------------------------


class TestCloneSetMetrics:
    def test_single_service(self) -> None:
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   line_count=10),
            _frag(clone_id="C1", fragment_index=1, service="svc_a",
                   line_count=20),
        ])
        result = compute_clone_set_metrics(df)
        assert len(result) == 1
        m = result[0]
        assert m.service_count == 1
        assert m.cross_service_fragment_count == 0
        assert m.cross_service_line_count == 0
        assert m.cross_service_element_count == 0

    def test_cross_service(self) -> None:
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   line_count=10),
            _frag(clone_id="C1", fragment_index=1, service="svc_b",
                   line_count=20),
            _frag(clone_id="C1", fragment_index=2, service="svc_a",
                   line_count=5),
        ])
        result = compute_clone_set_metrics(df)
        m = result[0]
        assert m.service_count == 2
        assert m.cross_service_fragment_count == 3  # all resolved
        assert m.cross_service_line_count == 35  # 10+20+5
        assert m.cross_service_scale == 3 * 35
        assert m.cross_service_element_count == 3

    def test_comod(self) -> None:
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   modified_commits='["h1"]', modified_count=1),
            _frag(clone_id="C1", fragment_index=1, service="svc_b",
                   modified_commits='["h1", "h2"]', modified_count=2),
        ])
        result = compute_clone_set_metrics(df)
        m = result[0]
        assert m.comod_count == 1  # h1 is comod
        assert m.comod_fragment_count == 2  # both involved
        assert m.comod_fragment_ratio == 1.0

    def test_empty_df(self) -> None:
        df = _make_df([])
        assert compute_clone_set_metrics(df) == []

    def test_cross_service_ratio(self) -> None:
        """未解決フラグメントを含むケース."""
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   line_count=10),
            _frag(clone_id="C1", fragment_index=1, service="svc_b",
                   line_count=20),
            _frag(clone_id="C1", fragment_index=2, service="",
                   line_count=5),
        ])
        result = compute_clone_set_metrics(df)
        m = result[0]
        # cross: 2 resolved fragments out of 3 total
        assert m.cross_service_fragment_count == 2
        assert m.cross_service_fragment_ratio == round(2 / 3, 6)


# ---------------------------------------------------------------------------
# compute_file_metrics
# ---------------------------------------------------------------------------


class TestFileMetrics:
    def test_basic(self) -> None:
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   file_path="svc_a/a.py", line_count=10),
            _frag(clone_id="C1", fragment_index=1, service="svc_b",
                   file_path="svc_b/b.py", line_count=20),
        ])
        result = compute_file_metrics(df, total_service_count=3)
        assert len(result) == 2

        f_a = next(m for m in result if m.file_path == "svc_a/a.py")
        assert f_a.service == "svc_a"
        assert f_a.sharing_service_count == 1  # svc_b
        assert f_a.total_service_count == 3
        assert f_a.cross_service_clone_set_count == 1  # C1
        assert f_a.cross_service_clone_set_ratio == 1.0
        assert f_a.sharing_service_ratio == round(1 / 3, 6)
        assert f_a.cross_service_line_count == 10

    def test_no_cross_service(self) -> None:
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   file_path="svc_a/a.py"),
            _frag(clone_id="C1", fragment_index=1, service="svc_a",
                   file_path="svc_a/b.py"),
        ])
        result = compute_file_metrics(df, total_service_count=2)
        f_a = next(m for m in result if m.file_path == "svc_a/a.py")
        assert f_a.sharing_service_count == 0
        assert f_a.cross_service_clone_set_count == 0

    def test_empty_df(self) -> None:
        df = _make_df([])
        assert compute_file_metrics(df, total_service_count=5) == []

    def test_cross_comod(self) -> None:
        """クロスサービスクローンの同時修正."""
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   file_path="svc_a/a.py",
                   modified_commits='["h1"]', modified_count=1),
            _frag(clone_id="C1", fragment_index=1, service="svc_b",
                   file_path="svc_b/b.py",
                   modified_commits='["h1"]', modified_count=1),
        ])
        result = compute_file_metrics(df, total_service_count=2)
        f_a = next(m for m in result if m.file_path == "svc_a/a.py")
        assert f_a.cross_service_comod_count == 1
        assert f_a.comod_shared_service_count == 1  # svc_b

    def test_cross_comod_requires_file_participation(self) -> None:
        """同じクローンセット内の別ファイル同士の同時修正は数えない."""
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   file_path="svc_a/a.py", modified_commits="[]"),
            _frag(clone_id="C1", fragment_index=1, service="svc_b",
                   file_path="svc_b/b.py", modified_commits='["h1"]',
                   modified_count=1),
            _frag(clone_id="C1", fragment_index=2, service="svc_c",
                   file_path="svc_c/c.py", modified_commits='["h1"]',
                   modified_count=1),
        ])
        result = compute_file_metrics(df, total_service_count=3)
        f_a = next(m for m in result if m.file_path == "svc_a/a.py")
        f_b = next(m for m in result if m.file_path == "svc_b/b.py")

        assert f_a.cross_service_comod_count == 0
        assert f_a.comod_shared_service_count == 0
        assert f_b.cross_service_comod_count == 1
        assert f_b.comod_shared_service_count == 1

    def test_sharing_service_ratio(self) -> None:
        """sharing_service_ratio = sharing / total."""
        df = _make_df([
            _frag(clone_id="C1", fragment_index=0, service="svc_a",
                   file_path="svc_a/x.py", line_count=5),
            _frag(clone_id="C1", fragment_index=1, service="svc_b",
                   file_path="svc_b/y.py", line_count=5),
            _frag(clone_id="C1", fragment_index=2, service="svc_c",
                   file_path="svc_c/z.py", line_count=5),
        ])
        result = compute_file_metrics(df, total_service_count=5)
        f_a = next(m for m in result if m.file_path == "svc_a/x.py")
        # svc_a のファイルから見て svc_b, svc_c の 2 サービスと共有
        assert f_a.sharing_service_count == 2
        assert f_a.sharing_service_ratio == round(2 / 5, 6)


# ---------------------------------------------------------------------------
# load / integration
# ---------------------------------------------------------------------------


class TestLoad:
    def test_load_enriched_fragments(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "clone_id,fragment_index,file_path,file_id,service,"
            "start_line,end_line,line_count,file_type,"
            "modified_commits,modified_count\n"
            'C1,0,svc_a/a.py,1,svc_a,1,10,10,logic,"[]",0\n',
            encoding="utf-8",
        )
        df = load_enriched_fragments(csv_path)
        assert len(df) == 1
        assert df.iloc[0]["clone_id"] == "C1"

    def test_load_enriched_fragments_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_enriched_fragments(tmp_path / "missing.csv")

    def test_load_language_stats(self, tmp_path: Path) -> None:
        path = tmp_path / "services.json"
        path.write_text(json.dumps({
            "services": {},
            "language_stats": {
                "Python": {
                    "services": {"svc_a": {"total_loc": 100}},
                    "total_files": 10,
                    "total_loc": 500,
                }
            }
        }), encoding="utf-8")
        stats = load_language_stats(path, "Python")
        assert stats["services"]["svc_a"]["total_loc"] == 100

    def test_load_language_stats_missing(self, tmp_path: Path) -> None:
        stats = load_language_stats(tmp_path / "missing.json", "Python")
        assert stats == {}


class TestComputeAll:
    def test_integration(self, tmp_path: Path) -> None:
        """compute_all_metrics の統合テスト."""
        csv_path = tmp_path / "enriched.csv"
        lines = [
            "clone_id,fragment_index,file_path,file_id,service,"
            "start_line,end_line,line_count,file_type,"
            "modified_commits,modified_count",
            'C1,0,svc_a/a.py,1,svc_a,1,10,10,logic,"[""h1""]",1',
            'C1,1,svc_b/b.py,2,svc_b,1,20,20,logic,"[""h1""]",1',
            'C2,0,svc_a/c.py,3,svc_a,5,15,11,logic,"[]",0',
            'C2,1,svc_a/d.py,4,svc_a,1,5,5,logic,"[]",0',
        ]
        csv_path.write_text("\n".join(lines), encoding="utf-8")

        svc_json = tmp_path / "services.json"
        svc_json.write_text(json.dumps({
            "services": {"svc_a/": ["svc_a"], "svc_b/": ["svc_b"]},
            "language_stats": {
                "Python": {
                    "services": {
                        "svc_a": {"file_count": 5, "total_loc": 500},
                        "svc_b": {"file_count": 3, "total_loc": 300},
                    },
                    "total_files": 8,
                    "total_loc": 800,
                }
            }
        }), encoding="utf-8")

        result = compute_all_metrics(csv_path, svc_json, "Python")
        assert "service" in result
        assert "clone_set" in result
        assert "file" in result
        assert len(result["service"]) == 2
        assert len(result["clone_set"]) == 2
        assert len(result["file"]) == 4
