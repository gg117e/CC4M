"""コミット間の行変更 (moving_lines) の計算と保存.

親コミット (古い側) から子コミット (新しい側) への unified diff を解析し,
ファイルごとに挿入行, 削除行, 置換行を記録する.

座標の約束:
    - ``inserted_lines`` と ``modified_lines`` は子コミット側の行番号.
    - ``deleted_lines`` と ``modified_parent_lines`` は親コミット側の行番号.
    - ``modified_lines[i]`` と ``modified_parent_lines[i]`` は対応する置換行の組.

詳細は docs/line_tracking.md を参照.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import git

logger = logging.getLogger(__name__)

# moving_lines JSON の形式バージョン.
# v1 (2026-10-16 より前) は hunk のリストをそのまま保存しており,
# 先頭 hunk のみ解析, 行番号 +1 ずれ, diff の向きが逆, という不具合を含む.
MOVING_LINES_FORMAT_VERSION = 2

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class LineChanges:
    """1 ファイル分の行変更."""

    inserted_lines: list[int] = field(default_factory=list)
    deleted_lines: list[int] = field(default_factory=list)
    modified_lines: list[int] = field(default_factory=list)
    modified_parent_lines: list[int] = field(default_factory=list)


@dataclass
class _HunkState:
    old_line: int
    new_line: int
    old_left: int
    new_left: int
    pending_deleted: list[int] = field(default_factory=list)
    pending_inserted: list[int] = field(default_factory=list)


def _parse_hunk_header(line: str) -> _HunkState | None:
    match = _HUNK_HEADER_RE.match(line)
    if match is None:
        return None
    old_start, old_count, new_start, new_count = match.groups()
    return _HunkState(
        old_line=int(old_start),
        new_line=int(new_start),
        old_left=int(old_count) if old_count is not None else 1,
        new_left=int(new_count) if new_count is not None else 1,
    )


def _flush_block(state: _HunkState, changes: LineChanges) -> None:
    """連続する削除行と挿入行のブロックを置換, 純削除, 純挿入に振り分ける.

    先頭から min(削除数, 挿入数) 行を置換の組とし, 残りを純粋な削除または挿入とする.
    """
    paired = min(len(state.pending_deleted), len(state.pending_inserted))
    changes.modified_parent_lines.extend(state.pending_deleted[:paired])
    changes.modified_lines.extend(state.pending_inserted[:paired])
    changes.deleted_lines.extend(state.pending_deleted[paired:])
    changes.inserted_lines.extend(state.pending_inserted[paired:])
    state.pending_deleted.clear()
    state.pending_inserted.clear()


def _consume_hunk_line(line: str, state: _HunkState, changes: LineChanges) -> None:
    if line.startswith("-"):
        state.pending_deleted.append(state.old_line)
        state.old_line += 1
        state.old_left -= 1
    elif line.startswith("+"):
        state.pending_inserted.append(state.new_line)
        state.new_line += 1
        state.new_left -= 1
    else:
        # context 行 (空行は git では " " で表されるが, 念のため "" も context とみなす)
        _flush_block(state, changes)
        state.old_line += 1
        state.new_line += 1
        state.old_left -= 1
        state.new_left -= 1


def parse_unified_diff(diff: str) -> LineChanges:
    """unified diff 文字列 (親 -> 子) の全 hunk を解析する.

    Args:
        diff: 1 ファイル分の unified diff. ``---``/``+++`` ヘッダの有無は問わない.

    Returns:
        子側座標の挿入行と置換行, 親側座標の削除行と置換行.
    """
    changes = LineChanges()
    state: _HunkState | None = None
    for line in diff.split("\n"):
        if line.startswith("@@"):
            if state is not None:
                _flush_block(state, changes)
            state = _parse_hunk_header(line)
            continue
        if state is None or line.startswith("\\"):
            continue
        _consume_hunk_line(line, state, changes)
        if state.old_left <= 0 and state.new_left <= 0:
            _flush_block(state, changes)
            state = None
    if state is not None:
        _flush_block(state, changes)
    return changes


def compute_moving_lines(
    parent_commit: git.Commit, child_commit: git.Commit
) -> list[dict]:
    """親コミットから子コミットへの diff を計算し, ファイルごとの行変更を返す.

    Args:
        parent_commit: 古い側のコミット.
        child_commit: 新しい側のコミット.

    Returns:
        ``child_path``, ``parent_path`` と行変更リストを持つ dict のリスト.
    """
    result: list[dict] = []
    for diff_item in parent_commit.diff(child_commit, create_patch=True):
        if not diff_item.diff:
            continue
        try:
            diff_text = diff_item.diff.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(
                "diff のデコードに失敗したためスキップします: %s -> %s, path=%s",
                parent_commit.hexsha,
                child_commit.hexsha,
                diff_item.b_path,
            )
            continue
        changes = parse_unified_diff(diff_text)
        result.append(
            {
                "child_path": diff_item.b_path,
                "parent_path": diff_item.a_path,
                "inserted_lines": changes.inserted_lines,
                "deleted_lines": changes.deleted_lines,
                "modified_lines": changes.modified_lines,
                "modified_parent_lines": changes.modified_parent_lines,
            }
        )
    return result


def save_moving_lines(path: Path, hunks: list[dict]) -> None:
    """行変更を形式バージョン付きで保存する."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"format_version": MOVING_LINES_FORMAT_VERSION, "hunks": hunks}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def load_moving_lines(path: Path) -> list[dict] | None:
    """保存済みの行変更を読み込む.

    Returns:
        hunk のリスト. ファイルが無い場合, または旧形式 (v1) の場合は None.
    """
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        logger.info("旧形式の moving_lines を無視します: %s", path)
        return None
    if payload.get("format_version") != MOVING_LINES_FORMAT_VERSION:
        logger.info("形式バージョンが異なる moving_lines を無視します: %s", path)
        return None
    return payload["hunks"]
