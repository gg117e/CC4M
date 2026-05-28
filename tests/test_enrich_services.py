"""enrich_services モジュールのテスト."""

import json
from pathlib import Path

import pytest

from modules.visualization.enrich_services import (
    ServiceFileStats,
    compute_service_file_stats,
    enrich_services_json,
)
from modules.visualization.service_mapping import ServiceContext


# ---------------------------------------------------------------------------
# compute_service_file_stats
# ---------------------------------------------------------------------------


def _make_contexts() -> list[ServiceContext]:
    """2 サービスのテスト用 CLAIM コンテキスト."""
    return [
        ServiceContext(service_name="svc_a", context="services/alpha", source="test"),
        ServiceContext(service_name="svc_b", context="services/beta", source="test"),
    ]


def _make_file_data() -> list[dict]:
    """file_data のテストフィクスチャ."""
    return [
        {"file_id": 0, "file_path": "services/alpha/main.py", "loc": 100},
        {"file_id": 1, "file_path": "services/alpha/util.py", "loc": 50},
        {"file_id": 2, "file_path": "services/beta/app.py", "loc": 200},
        {"file_id": 3, "file_path": "unrelated/foo.py", "loc": 30},
    ]


class TestComputeServiceFileStats:
    """compute_service_file_stats のテスト."""

    def test_basic_counts(self, tmp_path: Path) -> None:
        """サービスごとの file_count / total_loc が正しいこと."""
        contexts = _make_contexts()
        file_data = _make_file_data()

        per_service, total_files, total_loc, unresolved_files, unresolved_loc = (
            compute_service_file_stats(file_data, contexts, tmp_path)
        )

        assert total_files == 4
        assert total_loc == 380
        assert per_service["svc_a"].file_count == 2
        assert per_service["svc_a"].total_loc == 150
        assert per_service["svc_b"].file_count == 1
        assert per_service["svc_b"].total_loc == 200
        assert unresolved_files == 1
        assert unresolved_loc == 30

    def test_empty_file_data(self, tmp_path: Path) -> None:
        """file_data が空の場合, すべて 0 を返す."""
        per_service, total_files, total_loc, unresolved_files, unresolved_loc = (
            compute_service_file_stats([], _make_contexts(), tmp_path)
        )
        assert per_service == {}
        assert total_files == 0
        assert total_loc == 0
        assert unresolved_files == 0
        assert unresolved_loc == 0

    def test_all_unresolved(self, tmp_path: Path) -> None:
        """サービス解決が全て失敗する場合."""
        file_data = [
            {"file_id": 0, "file_path": "unknown/path.py", "loc": 10},
        ]
        per_service, total_files, total_loc, unresolved_files, unresolved_loc = (
            compute_service_file_stats(file_data, _make_contexts(), tmp_path)
        )
        assert per_service == {}
        assert unresolved_files == 1
        assert unresolved_loc == 10


# ---------------------------------------------------------------------------
# enrich_services_json
# ---------------------------------------------------------------------------


class TestEnrichServicesJson:
    """enrich_services_json のテスト."""

    def test_adds_language_stats(self, tmp_path: Path) -> None:
        """language_stats セクションが追記されること."""
        services_json = tmp_path / "services.json"
        services_json.write_text(
            json.dumps(
                {
                    "services": {"services/alpha/": ["svc_a"]},
                    "URL": "https://example.com",
                }
            ),
            encoding="utf-8",
        )

        enrich_services_json(
            services_json_path=services_json,
            language="Python",
            file_data=_make_file_data(),
            claim_contexts=_make_contexts(),
            project_dir=tmp_path,
        )

        result = json.loads(services_json.read_text(encoding="utf-8"))

        # 既存キーが残っていること
        assert "services" in result
        assert "URL" in result

        # language_stats が追記されていること
        assert "language_stats" in result
        py_stats = result["language_stats"]["Python"]
        assert py_stats["total_files"] == 4
        assert py_stats["total_loc"] == 380
        assert py_stats["unresolved_files"] == 1
        assert "svc_a" in py_stats["services"]
        assert py_stats["services"]["svc_a"]["file_count"] == 2

    def test_preserves_existing_language_stats(self, tmp_path: Path) -> None:
        """既存の他言語の language_stats を壊さないこと."""
        services_json = tmp_path / "services.json"
        services_json.write_text(
            json.dumps(
                {
                    "services": {"services/alpha/": ["svc_a"]},
                    "URL": "https://example.com",
                    "language_stats": {
                        "JavaScript": {
                            "services": {"svc_a": {"file_count": 3, "total_loc": 100}},
                            "total_files": 3,
                            "total_loc": 100,
                            "unresolved_files": 0,
                            "unresolved_loc": 0,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        enrich_services_json(
            services_json_path=services_json,
            language="Python",
            file_data=_make_file_data(),
            claim_contexts=_make_contexts(),
            project_dir=tmp_path,
        )

        result = json.loads(services_json.read_text(encoding="utf-8"))
        assert "JavaScript" in result["language_stats"]
        assert "Python" in result["language_stats"]
        assert result["language_stats"]["JavaScript"]["total_files"] == 3

    def test_file_not_found(self, tmp_path: Path) -> None:
        """存在しない JSON パスで FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            enrich_services_json(
                services_json_path=tmp_path / "no_such.json",
                language="Python",
                file_data=[],
                claim_contexts=[],
                project_dir=tmp_path,
            )
