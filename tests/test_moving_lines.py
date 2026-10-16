from pathlib import Path

import git
import pytest

from modules.moving_lines import (
    MOVING_LINES_FORMAT_VERSION,
    compute_moving_lines,
    load_moving_lines,
    parse_unified_diff,
    save_moving_lines,
)


def test_parse_unified_diff_multiple_hunks_all_parsed() -> None:
    # 旧実装は "@@" で split して先頭 hunk しか見ていなかった
    diff = "\n".join(
        [
            "@@ -2,3 +2,3 @@ line1",
            " line2",
            "-line3",
            "+CHANGED3",
            "@@ -20,2 +20,3 @@ line19",
            " line20",
            "+INSERTED",
            " line21",
            "@@ -40,3 +41,2 @@ line39",
            " line40",
            "-line41",
            " line42",
            "",
        ]
    )

    changes = parse_unified_diff(diff)

    assert changes.modified_lines == [3]
    assert changes.modified_parent_lines == [3]
    assert changes.inserted_lines == [21]
    assert changes.deleted_lines == [41]


def test_parse_unified_diff_header_trailing_text_not_counted() -> None:
    # 旧実装はヘッダ行の残り (関数名など) を context 行として数え, 行番号が +1 ずれていた
    diff = "@@ -1,3 +1,6 @@ public class Foo {\n+a\n+b\n+c\n x\n y\n z\n"

    changes = parse_unified_diff(diff)

    assert changes.inserted_lines == [1, 2, 3]
    assert changes.deleted_lines == []


def test_parse_unified_diff_zero_count_hunk_uses_header_start() -> None:
    diff = "@@ -3,0 +4,2 @@ import a;\n+import b;\n+import c;\n@@ -35,2 +37,0 @@\n-x\n-y\n"

    changes = parse_unified_diff(diff)

    assert changes.inserted_lines == [4, 5]
    assert changes.deleted_lines == [35, 36]


def test_parse_unified_diff_unequal_replacement_pairs_leading_lines() -> None:
    diff = "@@ -1,4 +1,3 @@\n a\n-b\n-c\n-d\n+B\n e\n"

    changes = parse_unified_diff(diff)

    assert changes.modified_parent_lines == [2]
    assert changes.modified_lines == [2]
    assert changes.deleted_lines == [3, 4]
    assert changes.inserted_lines == []


def test_parse_unified_diff_no_newline_marker_ignored() -> None:
    diff = "@@ -1 +1 @@\n-old\n\\ No newline at end of file\n+new\n\\ No newline at end of file\n"

    changes = parse_unified_diff(diff)

    assert changes.modified_parent_lines == [1]
    assert changes.modified_lines == [1]


def test_load_moving_lines_legacy_list_format_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text('[{"child_path": "A.java", "parent_path": "A.java"}]', encoding="utf-8")

    assert load_moving_lines(path) is None


def test_load_moving_lines_missing_file_returns_none(tmp_path: Path) -> None:
    assert load_moving_lines(tmp_path / "missing.json") is None


def test_save_moving_lines_roundtrip_keeps_hunks(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "x.json"
    hunks = [{"child_path": "A.java", "parent_path": "A.java", "inserted_lines": [1]}]

    save_moving_lines(path, hunks)

    assert load_moving_lines(path) == hunks
    assert f'"format_version": {MOVING_LINES_FORMAT_VERSION}' in path.read_text(encoding="utf-8")


def _commit_file(repo: git.Repo, repo_dir: Path, text: str, message: str) -> git.Commit:
    (repo_dir / "A.java").write_text(text, encoding="utf-8")
    repo.index.add(["A.java"])
    return repo.index.commit(message)


@pytest.mark.slow
def test_compute_moving_lines_insertion_at_top_uses_child_coordinates(tmp_path: Path) -> None:
    # 旧実装は 新しい側.diff(古い側) を取っており, 挿入と削除の向きが逆になっていた
    repo = git.Repo.init(tmp_path)
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "test")
        cfg.set_value("user", "email", "test@example.com")
    body = "".join(f"old{i}\n" for i in range(1, 21))
    parent = _commit_file(repo, tmp_path, body, "parent")
    child = _commit_file(repo, tmp_path, "new1\nnew2\nnew3\n" + body, "child")

    hunks = compute_moving_lines(parent_commit=parent, child_commit=child)

    assert len(hunks) == 1
    assert hunks[0]["child_path"] == "A.java"
    assert hunks[0]["inserted_lines"] == [1, 2, 3]
    assert hunks[0]["deleted_lines"] == []
