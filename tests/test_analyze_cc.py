from modules.analyze_cc import (
    CorrespondedLines,
    correspond_clonesets,
    correspond_code_fragments,
)
from modules.moving_lines import parse_unified_diff
from modules.util import FileMapper

PROJECT_DIR = "/repo"


def _filemap(loc: int) -> FileMapper:
    return FileMapper([{"file_id": 0, "file_path": f"{PROJECT_DIR}/A.java", "loc": loc}], PROJECT_DIR)


def _hunks_from_diff(diff: str) -> list[dict]:
    changes = parse_unified_diff(diff)
    return [
        {
            "child_path": "A.java",
            "parent_path": "A.java",
            "inserted_lines": changes.inserted_lines,
            "deleted_lines": changes.deleted_lines,
            "modified_lines": changes.modified_lines,
            "modified_parent_lines": changes.modified_parent_lines,
        }
    ]


def _single_fragment_set(start: int, end: int) -> list[dict]:
    return [{"clone_id": 0, "fragments": [{"file_id": 0, "start_line": start, "end_line": end}]}]


def _classify(diff: str, child_loc: int, parent_loc: int, child_range, parent_range) -> str:
    hunks = _hunks_from_diff(diff)
    child_map, parent_map = _filemap(child_loc), _filemap(parent_loc)
    lines = CorrespondedLines(hunks, child_map, parent_map)
    child_sets = _single_fragment_set(*child_range)
    parent_sets = _single_fragment_set(*parent_range)
    fragments = correspond_code_fragments(lines, child_sets, parent_sets, child_map, parent_map)
    result = correspond_clonesets(fragments, lines, child_sets, parent_sets, child_map, parent_map)
    return result[0]["fragments"][0]["type"]


def test_corresponded_lines_insertion_at_top_maps_shifted_lines() -> None:
    # 子 (新) の先頭に 3 行挿入: 子 1-3 は対応なし, 子 4 が親 1 に対応する
    diff = "@@ -1,3 +1,6 @@\n+n1\n+n2\n+n3\n o1\n o2\n o3\n"
    lines = CorrespondedLines(_hunks_from_diff(diff), _filemap(23), _filemap(20))

    assert [lines.get_parent_line("A.java", i) for i in (1, 2, 3)] == [None, None, None]
    assert lines.get_parent_line("A.java", 4) == 1
    assert lines.get_parent_line("A.java", 23) == 20


def test_corresponded_lines_second_hunk_shift_applied() -> None:
    # 2 番目の hunk (旧実装では無視されていた) の挿入より後ろの行がずれる
    diff = "@@ -2,1 +2,1 @@\n-a\n+A\n@@ -10,2 +10,3 @@\n x\n+ins\n y\n"
    lines = CorrespondedLines(_hunks_from_diff(diff), _filemap(31), _filemap(30))

    assert lines.get_parent_line("A.java", 11) is None
    assert lines.get_parent_line("A.java", 12) == 11
    assert lines.get_parent_line("A.java", 31) == 30


def test_correspond_clonesets_shift_only_is_stable() -> None:
    # 断片 (子 50-64) より上に 3 行挿入, 下で削除. 断片の中身は変わっていない
    diff = "@@ -3,0 +4,3 @@\n+i1\n+i2\n+i3\n@@ -100,2 +102,0 @@\n-d1\n-d2\n"

    kind = _classify(diff, child_loc=102, parent_loc=101, child_range=(50, 64), parent_range=(47, 61))

    assert kind == "stable"


def test_correspond_clonesets_edit_inside_fragment_is_modified() -> None:
    diff = "@@ -55 +55 @@\n-x = 1;\n+x = 2;\n"

    kind = _classify(diff, child_loc=100, parent_loc=100, child_range=(50, 64), parent_range=(50, 64))

    assert kind == "modified"


def test_correspond_clonesets_deletion_inside_parent_fragment_is_modified() -> None:
    diff = "@@ -55,3 +55,2 @@\n a\n-b\n c\n"

    kind = _classify(diff, child_loc=99, parent_loc=100, child_range=(50, 63), parent_range=(50, 64))

    assert kind == "modified"
