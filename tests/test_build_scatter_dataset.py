import csv
import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from src.modules.visualization import build_scatter_dataset as scatter


def _modification(commits: list[str]) -> str:
    return json.dumps([{"type": "modified", "commit": commit} for commit in commits])


def _build_rows(
    monkeypatch,
    tmp_path: Path,
    left_commits: list[str],
    right_commits: list[str],
):
    monkeypatch.setattr(
        scatter,
        "resolve_service_context_for_file_path",
        lambda *args, **kwargs: SimpleNamespace(service_name="svc-a"),
    )
    monkeypatch.setattr(
        scatter,
        "safe_get_file_id",
        lambda _mapper, file_path: 1 if file_path.endswith("a.py") else 2,
    )
    monkeypatch.setattr(scatter, "get_file_type", lambda *args, **kwargs: "logic")

    fragments = [
        scatter.FragmentRow(
            clone_id="10",
            index=0,
            file_path="svc/a.py",
            start_line=1,
            end_line=5,
            modification_raw=_modification(left_commits),
        ),
        scatter.FragmentRow(
            clone_id="10",
            index=1,
            file_path="svc/b.py",
            start_line=10,
            end_line=15,
            modification_raw=_modification(right_commits),
        ),
    ]

    resolved, unknown = scatter.build_pair_rows(
        fragments,
        language="Python",
        claim_contexts=[],
        project_dir=tmp_path,
        file_mapper=None,
        service_cache={},
        file_id_cache={},
        file_text_cache={},
        token_count_map={"10": 42},
    )
    assert unknown == []
    assert len(resolved) == 1
    return resolved[0]


def test_build_pair_rows_records_all_common_commits(monkeypatch, tmp_path):
    row = _build_rows(
        monkeypatch,
        tmp_path,
        ["shared_b", "left_only", "shared_a"],
        ["right_only", "shared_a", "shared_b"],
    )

    assert row.comodified == 1
    assert row.comodification_count == 2
    assert json.loads(row.comodified_commits) == ["shared_a", "shared_b"]

    output = StringIO()
    writer = csv.writer(output)
    scatter.write_pair_csv_header(writer)
    scatter.write_pair_csv_row(writer, row)
    output.seek(0)

    csv_row = next(csv.DictReader(output))
    assert json.loads(csv_row["comodified_commits"]) == ["shared_a", "shared_b"]
    assert csv_row["comodification_count"] == "2"


def test_build_pair_rows_records_empty_common_commits(monkeypatch, tmp_path):
    row = _build_rows(monkeypatch, tmp_path, ["left_only"], ["right_only"])

    assert row.comodified == 0
    assert row.comodification_count == 0
    assert json.loads(row.comodified_commits) == []


def test_scatter_loader_backfills_comodification_columns_for_old_csv():
    from src.visualize.data_loader.csv_loader import (
        _normalize_scatter_comodification_columns,
    )

    df = pd.DataFrame({"comodified": [True, False]})

    result = _normalize_scatter_comodification_columns(df)

    assert result["comodified_commits"].tolist() == ["[]", "[]"]
    assert result["comodification_count"].astype(int).tolist() == [1, 0]


def test_scatter_loader_preserves_new_comodification_columns():
    from src.visualize.data_loader.csv_loader import (
        _normalize_scatter_comodification_columns,
    )

    df = pd.DataFrame(
        {
            "comodified": [True],
            "comodified_commits": ['["c1", "c2"]'],
            "comodification_count": ["2"],
        }
    )

    result = _normalize_scatter_comodification_columns(df)

    assert result.loc[0, "comodified_commits"] == '["c1", "c2"]'
    assert int(result.loc[0, "comodification_count"]) == 2
