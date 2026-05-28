import logging
import json
import os
import re

import pandas as pd
from dash import html, dcc
import difflib

from ..utils import get_local_snippet, extract_common_commits
from .clone_metrics import generate_github_file_url, generate_github_commit_url, generate_github_diff_url
from ..data_loader import load_metrics_dataframes
from modules.util import get_file_type

logger = logging.getLogger(__name__)

def build_clone_details_view(row, project, df, file_ranges):
    """クリックされたクローンの詳細な比較ビューを生成する."""
    # df から言語を推測、デフォルトは "Java"
    language = "Java"
    if df is not None and not df.empty:
        if "language" in df.columns:
            languages = df["language"].dropna().unique()
            if len(languages) > 0:
                language = str(languages[0])
    return build_clone_details_view_single(row, project, language=language)


def build_clone_details_view_single(row, project, language: str = "Java"):
    """単一クローンの詳細ビューを生成する.

    Args:
        row: クローンペアの行データ（pandas Series または dict）
        project: プロジェクト名
        language: 言語（enriched_fragments CSV を読み込む際に使用）

    Returns:
        クローン詳細ビューの Dash HTML Div
    """
    file_x, file_y = row.get("file_path_x"), row.get("file_path_y")
    sx, ex = int(row.get("start_line_x", 0)), int(row.get("end_line_x", 0))
    sy, ey = int(row.get("start_line_y", 0)), int(row.get("end_line_y", 0))

    snippet_x_lines = get_local_snippet(project, file_x, sx, ex, context=0).splitlines()
    snippet_y_lines = get_local_snippet(project, file_y, sy, ey, context=0).splitlines()

    code_x_for_copy = "\n".join(
        [re.sub(r"^[ >]\s*\d+:\s*", "", line) for line in snippet_x_lines]
    )
    code_y_for_copy = "\n".join(
        [re.sub(r"^[ >]\s*\d+:\s*", "", line) for line in snippet_y_lines]
    )

    # 行番号を除いた純粋なコード内容で比較
    code_x_lines = [re.sub(r"^[ >]\s*\d+:\s*", "", line) for line in snippet_x_lines]
    code_y_lines = [re.sub(r"^[ >]\s*\d+:\s*", "", line) for line in snippet_y_lines]
    sm = difflib.SequenceMatcher(None, code_x_lines, code_y_lines)
    rows_x, rows_y = [], []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        # 表示用には元の行番号付きの行を使用
        block_x, block_y = snippet_x_lines[i1:i2], snippet_y_lines[j1:j2]

        is_diff = tag == "equal"  # 完全一致の場合に背景色を付ける

        for line in block_x:
            rows_x.append(_diff_pane(line, is_diff))

        for line in block_y:
            rows_y.append(_diff_pane(line, is_diff))

    return html.Div(
        [
            # ヘッダーやメタ情報は各ペイン内に移動させるため、トップレベルはシンプルに
            html.Div(
                [
                    # Left Pane (Pane X)
                    html.Div(
                        [
                            _file_header(
                                file_x,
                                row.get("service_x", ""),
                                project,
                                sx,
                                ex,
                                row.get("file_id_x", "N/A"),
                            ),
                            html.Div(
                                _code_pane(
                                    rows_x,
                                    code_x_for_copy,
                                    "X",
                                    file_x,
                                    project,
                                    sx,
                                    ex,
                                ),
                                style={"flex": "1", "overflow": "hidden"},
                            ),
                        ],
                        className="split-pane",
                        style={"flex": "0 0 50%"},
                    ),  # Initial 50% width
                    # Gutter (Splitter)
                    html.Div(className="split-gutter", title="Drag to resize"),
                    # Right Pane (Pane Y)
                    html.Div(
                        [
                            _file_header(
                                file_y,
                                row.get("service_y", ""),
                                project,
                                sy,
                                ey,
                                row.get("file_id_y", "N/A"),
                            ),
                            html.Div(
                                _code_pane(
                                    rows_y,
                                    code_y_for_copy,
                                    "Y",
                                    file_y,
                                    project,
                                    sy,
                                    ey,
                                ),
                                style={"flex": "1", "overflow": "hidden"},
                            ),
                        ],
                        className="split-pane",
                        style={"flex": "1"},
                    ),  # Takes remaining space
                ],
                className="split-container",
            ),
            # Co-change History セクションを追加
            build_cochange_history_section(row, project, language),
        ]
    )


def _file_header(file_path, service, project, start_line, end_line, file_id):
    """ファイルヘッダーコンポーネント (VS Code Tab風)"""
    # ファイルタイプ判定
    ftype = get_file_type(file_path)

    # タイプごとのスタイル定義（テキスト色のみ）
    type_styles = {
        "logic": {"color": "#0366d6", "borderColor": "#0366d6"},  # Blue
        "test": {"color": "#28a745", "borderColor": "#28a745"},  # Green
        "data": {"color": "#d73a49", "borderColor": "#d73a49"},  # Red
        "config": {"color": "#6a737d", "borderColor": "#6a737d"},  # Gray
    }
    t_style = type_styles.get(ftype, {"color": "#586069", "borderColor": "#e1e4e8"})

    # ファイル名だけ抽出
    filename = file_path.split("/")[-1] if file_path else "Unknown"
    # ディレクトリパス
    dir_path = os.path.dirname(file_path) if file_path else ""

    # GitHub URL
    github_url = generate_github_file_url(project, file_path, start_line, end_line)

    return html.Div(
        [
            # 左側: タイプバッジ(テキスト), ファイル名, パス
            html.Div(
                [
                    html.Span(
                        ftype.upper(),
                        style={
                            "color": t_style["color"],
                            "fontSize": "10px",
                            "fontWeight": "bold",
                            "border": f"1px solid {t_style['borderColor']}",
                            "padding": "1px 4px",
                            "borderRadius": "3px",
                            "marginRight": "8px",
                        },
                    ),
                    html.Span(
                        filename,
                        title=file_path,
                        style={
                            "fontWeight": "600",
                            "fontSize": "13px",
                            "marginRight": "8px",
                            "color": "#24292e",
                        },
                    ),
                    html.Span(
                        dir_path,
                        title=file_path,
                        style={
                            "color": "#6a737d",
                            "fontSize": "11px",
                            "fontFamily": "monospace",
                            "overflow": "hidden",
                            "textOverflow": "ellipsis",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "overflow": "hidden",
                    "whiteSpace": "nowrap",
                    "flex": "1",
                },
            ),
            # 右側: サービス名, File ID, Actions
            html.Div(
                [
                    html.Span(
                        [html.B("Svc: "), service],
                        style={
                            "fontSize": "11px",
                            "color": "#586069",
                            "marginRight": "10px",
                        },
                    ),
                    html.Span(
                        [html.B("ID: "), str(file_id)],
                        style={
                            "fontSize": "11px",
                            "color": "#586069",
                            "marginRight": "10px",
                        },
                    ),
                    (
                        html.A(
                            "GitHub ↗",
                            href=github_url,
                            target="_blank",
                            style={
                                "fontSize": "11px",
                                "color": "#0366d6",
                                "textDecoration": "none",
                            },
                        )
                        if github_url
                        else None
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "flexShrink": "0"},
            ),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "padding": "8px 12px",
            "borderBottom": "1px solid #e1e4e8",
            "backgroundColor": "#f6f8fa",
            "height": "36px",
            "boxSizing": "border-box",
            "borderTopLeftRadius": "6px",
            "borderTopRightRadius": "6px",
        },
    )


def _code_pane(rows, code_for_copy, suffix, file_path, project, start_line, end_line):
    # ファイル全体の内容を読み込み
    from ..utils import get_file_content

    full_content = get_file_content(project, file_path, start_line, end_line)

    # コード片部分 (dcc.Clipboardはヘッダーに移動してもいいが、一旦ここ)
    # オーバーレイコピーボタンのデザイン調整
    code_snippet = html.Div(
        [
            dcc.Clipboard(
                content=code_for_copy,
                className="copy-button",
                title=f"Copy code {suffix}",
                style={
                    "position": "absolute",
                    "top": "5px",
                    "right": "5px",
                    "zIndex": "10",
                },
            ),
            html.Div(rows, className="code-pane-content", style={"padding": "15px"}),
        ],
        className="code-pane",
        style={
            "position": "relative",
            "backgroundColor": "#fff",
            "borderBottom": "1px solid #eee",
        },
    )

    # ファイル全体部分 (高さ制限を撤廃し、自然に展開)
    full_file_section = html.Div(
        [
            html.Div(
                [
                    html.Span(
                        "📄 Full Source Code",
                        style={
                            "fontWeight": "600",
                            "color": "#444",
                            "fontSize": "13px",
                        },
                    ),
                ],
                style={
                    "padding": "10px 15px",
                    "background": "#f8f9fa",
                    "borderBottom": "1px solid #e1e4e8",
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "space-between",
                },
            ),
            dcc.Markdown(
                full_content,
                className="full-code-markdown",
                style={
                    "padding": "15px",
                    "fontSize": "12px",
                    "lineHeight": "1.5",
                    "fontFamily": "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
                },
            ),
        ],
        className="full-file-content",
        style={
            "borderTop": "none",
            "height": "70vh",
            "overflowY": "auto",
            "display": "block",
        },
    )

    return html.Div(
        [
            html.Div(
                "🔍 Matched Snippet",
                style={
                    "fontSize": "11px",
                    "fontWeight": "bold",
                    "color": "#888",
                    "textTransform": "uppercase",
                    "padding": "10px 15px 5px",
                    "letterSpacing": "0.5px",
                },
            ),
            code_snippet,
            full_file_section,
        ],
        style={
            "backgroundColor": "white",
            "display": "flex",
            "flexDirection": "column",
        },
    )


def _diff_pane(line, is_diff):
    # utils.py generates: f"{prefix}{i+1:5d}: {lines[i]}"
    # old regex: r'([ >])\s*(\d+):\s*(.*)' <- \s* ate leading spaces of code
    # new regex preserves the content after the single space separator
    match = re.match(r"([ >])\s*(\d+): (.*)", line)
    if not match:
        # Fallback for empty lines or unexpected format (try matching without trailing content)
        match = re.match(r"([ >])\s*(\d+):(.*)", line)

    if not match:
        # Completely failed to match format, return as simple line
        return html.Div(line, className="diff-line", style={"whiteSpace": "pre"})

    prefix, ln, text = match.groups()
    return html.Div(
        [
            html.Span(
                ln,
                className="line-num",
                **({"data-prefix": prefix} if prefix != " " else {}),
            ),
            html.Span(text),
        ],
        className=f"diff-line {'diff' if is_diff else ''}",
    )


def _legend_chip(label, color):
    return html.Div(
        label,
        style={
            "background": color,
            "border": "1px solid #ddd",
            "padding": "2px 6px",
            "borderRadius": "3px",
            "fontSize": "11px",
        },
    )


def _normalize_path(path: str) -> str:
    """パスを正規化する（先頭のスラッシュを削除）."""
    if path and path.startswith("/"):
        return path[1:]
    return path or ""


def _safe_int(value) -> int:
    """値を安全に int に変換する（None や pd.NA を 0 として扱う）."""
    if value is None or pd.isna(value):
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _find_fragment_by_location(
    fragments_df: pd.DataFrame,
    file_path: str,
    start_line: int,
    end_line: int,
) -> pd.Series | None:
    """ファイルパスと行番号範囲からフラグメントを検索する.

    Args:
        fragments_df: フラグメントの DataFrame
        file_path: ファイルパス
        start_line: 開始行
        end_line: 終了行

    Returns:
        一致するフラグメントの Series。見つからない場合は None
    """
    if fragments_df.empty or "file_path" not in fragments_df.columns:
        return None

    # パスを正規化して比較
    norm_target = _normalize_path(file_path)

    for _, frag in fragments_df.iterrows():
        frag_path = _normalize_path(str(frag.get("file_path", "")))
        frag_start = _safe_int(frag.get("start_line"))
        frag_end = _safe_int(frag.get("end_line"))

        if frag_path == norm_target and frag_start == start_line and frag_end == end_line:
            return frag

    return None


def _parse_row_comodified_commits(row) -> list[str] | None:
    """Return commit list from scatter CSV row, or None when the column is absent."""

    if "comodified_commits" not in row:
        return None

    raw_commits = row.get("comodified_commits")
    if raw_commits is None:
        return None if _row_indicates_comodification(row) else []
    if isinstance(raw_commits, list):
        candidates = raw_commits
    else:
        try:
            if pd.isna(raw_commits):
                return None if _row_indicates_comodification(row) else []
        except (TypeError, ValueError):
            pass

        text = str(raw_commits).strip()
        if not text or text == "[]":
            return None if _row_indicates_comodification(row) else []
        try:
            candidates = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.debug("Invalid comodified_commits JSON: %s", exc)
            return None

    if not isinstance(candidates, list):
        return []

    commits: list[str] = []
    seen: set[str] = set()
    for commit in candidates:
        if not commit:
            continue
        commit_hash = str(commit)
        if commit_hash in seen:
            continue
        seen.add(commit_hash)
        commits.append(commit_hash)
    return commits


def _row_indicates_comodification(row) -> bool:
    if "comodification_count" in row:
        count = row.get("comodification_count")
        try:
            if count is None or pd.isna(count):
                return False
        except (TypeError, ValueError):
            pass
        try:
            return int(count) > 0
        except (TypeError, ValueError):
            return False

    if "comodified" not in row:
        return False

    value = row.get("comodified")
    try:
        if value is None or pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _build_cochange_history_from_commits(
    common_commits: list[str],
    project: str,
    file_path_x: str,
    start_line_x: int,
    end_line_x: int,
    file_path_y: str,
    start_line_y: int,
    end_line_y: int,
) -> html.Div:
    """Build the Co-change History section from precomputed commit hashes."""

    commit_cards = []
    for commit_hash in common_commits:
        commit_url = generate_github_commit_url(project, commit_hash)
        short_hash = commit_hash[:7] if len(commit_hash) >= 7 else commit_hash

        card_content = [
            html.Span(
                short_hash,
                style={
                    "fontFamily": "monospace",
                    "fontWeight": "600",
                    "color": "#24292e",
                    "fontSize": "13px",
                },
            ),
        ]

        if commit_url:
            card_content.append(
                html.A(
                    "View Commit",
                    href=commit_url,
                    target="_blank",
                    style={
                        "marginLeft": "12px",
                        "color": "#0366d6",
                        "textDecoration": "none",
                        "fontSize": "12px",
                    },
                )
            )

        file_x_url = generate_github_file_url(
            project, file_path_x, start_line_x, end_line_x, commit_hash=commit_hash
        )
        if file_x_url:
            card_content.append(
                html.A(
                    "File X",
                    href=file_x_url,
                    target="_blank",
                    style={
                        "marginLeft": "12px",
                        "color": "#0366d6",
                        "textDecoration": "none",
                        "fontSize": "12px",
                    },
                )
            )

        file_y_url = generate_github_file_url(
            project, file_path_y, start_line_y, end_line_y, commit_hash=commit_hash
        )
        if file_y_url:
            card_content.append(
                html.A(
                    "File Y",
                    href=file_y_url,
                    target="_blank",
                    style={
                        "marginLeft": "12px",
                        "color": "#0366d6",
                        "textDecoration": "none",
                        "fontSize": "12px",
                    },
                )
            )

        diff_x_url = generate_github_diff_url(project, commit_hash, file_path_x)
        if diff_x_url:
            card_content.append(
                html.A(
                    "Diff X",
                    href=diff_x_url,
                    target="_blank",
                    style={
                        "marginLeft": "12px",
                        "color": "#28a745",
                        "textDecoration": "none",
                        "fontSize": "12px",
                    },
                )
            )

        diff_y_url = generate_github_diff_url(project, commit_hash, file_path_y)
        if diff_y_url:
            card_content.append(
                html.A(
                    "Diff Y",
                    href=diff_y_url,
                    target="_blank",
                    style={
                        "marginLeft": "12px",
                        "color": "#28a745",
                        "textDecoration": "none",
                        "fontSize": "12px",
                    },
                )
            )

        commit_cards.append(
            html.Div(
                card_content,
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "padding": "8px 12px",
                    "backgroundColor": "#f6f8fa",
                    "border": "1px solid #e1e4e8",
                    "borderRadius": "6px",
                    "marginBottom": "6px",
                },
            )
        )

    return html.Div(
        [
            html.H4(
                "Co-change History",
                style={
                    "marginTop": "20px",
                    "marginBottom": "12px",
                    "fontSize": "16px",
                    "fontWeight": "600",
                    "color": "#24292e",
                },
            ),
            html.Div(
                f"{len(common_commits)} common commit(s) found",
                style={
                    "marginBottom": "10px",
                    "fontSize": "12px",
                    "color": "#586069",
                },
            ),
            html.Div(
                commit_cards,
                style={
                    "maxHeight": "200px",
                    "overflowY": "auto",
                },
            ),
        ],
        style={
            "padding": "15px",
            "backgroundColor": "white",
            "borderTop": "1px solid #e1e4e8",
        },
    )


def build_cochange_history_section(row, project: str, language: str) -> html.Div:
    """Co-change Historyセクションを生成する.

    Args:
        row: クローンペアの行データ（pandas Series または dict）
        project: プロジェクト名
        language: 言語（enriched_fragments CSV を読み込む際に使用）

    Returns:
        Co-change Historyセクションの Dash HTML Div
    """
    try:
        clone_id = row.get("clone_id")
        if clone_id is None:
            logger.debug("No clone_id found in row")
            return _build_no_cochange_message()

        # 選択されたペアの情報を取得
        file_path_x = row.get("file_path_x")
        file_path_y = row.get("file_path_y")
        start_line_x = _safe_int(row.get("start_line_x"))
        end_line_x = _safe_int(row.get("end_line_x"))
        start_line_y = _safe_int(row.get("start_line_y"))
        end_line_y = _safe_int(row.get("end_line_y"))

        logger.debug(
            "Looking for fragments: X=(%s, %d-%d), Y=(%s, %d-%d), clone_id=%s",
            file_path_x, start_line_x, end_line_x,
            file_path_y, start_line_y, end_line_y,
            clone_id
        )

        # enriched_fragments を取得
        row_common_commits = _parse_row_comodified_commits(row)
        if row_common_commits is not None:
            if not row_common_commits:
                return _build_no_cochange_message()
            return _build_cochange_history_from_commits(
                row_common_commits,
                project,
                file_path_x,
                start_line_x,
                end_line_x,
                file_path_y,
                start_line_y,
                end_line_y,
            )

        metrics = load_metrics_dataframes(project, language)
        fragments_df = metrics.get("fragments", pd.DataFrame())

        if fragments_df.empty:
            logger.debug(
                "No enriched_fragments found for project=%s, language=%s",
                project, language
            )
            return _build_no_cochange_message()

        # clone_id に一致するフラグメントを取得
        if "clone_id" not in fragments_df.columns:
            logger.debug("clone_id column not found in fragments DataFrame")
            return _build_no_cochange_message()

        clone_frags = fragments_df[fragments_df["clone_id"] == clone_id]

        if clone_frags.empty:
            logger.debug("No fragments found for clone_id=%s", clone_id)
            return _build_no_cochange_message()

        # modified_commits 列を取得
        if "modified_commits" not in clone_frags.columns:
            logger.debug("modified_commits column not found in fragments DataFrame")
            return _build_no_cochange_message()

        # 選択されたペアに対応するフラグメントを検索
        fragment_x = _find_fragment_by_location(
            clone_frags, file_path_x, start_line_x, end_line_x
        )
        fragment_y = _find_fragment_by_location(
            clone_frags, file_path_y, start_line_y, end_line_y
        )

        if fragment_x is None:
            logger.debug(
                "Fragment X not found for clone_id=%s, file=%s, lines=%d-%d",
                clone_id, file_path_x, start_line_x, end_line_x
            )
            return _build_no_cochange_message()

        if fragment_y is None:
            logger.debug(
                "Fragment Y not found for clone_id=%s, file=%s, lines=%d-%d",
                clone_id, file_path_y, start_line_y, end_line_y
            )
            return _build_no_cochange_message()

        # 選択されたフラグメントの modified_commits を取得
        modification_x = str(fragment_x.get("modified_commits") or "[]")
        modification_y = str(fragment_y.get("modified_commits") or "[]")

        logger.debug(
            "Found fragments - X commits: %s, Y commits: %s",
            modification_x[:50] + "..." if len(modification_x) > 50 else modification_x,
            modification_y[:50] + "..." if len(modification_y) > 50 else modification_y
        )

        # 共通コミットを抽出
        common_commits = extract_common_commits(modification_x, modification_y)

        if not common_commits:
            return _build_no_cochange_message()

        # 共通コミットのカード形式リストを生成
        commit_cards = []
        for commit_hash in common_commits:
            commit_url = generate_github_commit_url(project, commit_hash)
            short_hash = commit_hash[:7] if len(commit_hash) >= 7 else commit_hash

            card_content = [
                html.Span(
                    f"🔗 {short_hash}",
                    style={
                        "fontFamily": "monospace",
                        "fontWeight": "600",
                        "color": "#24292e",
                        "fontSize": "13px",
                    },
                ),
            ]

            if commit_url:
                card_content.append(
                    html.A(
                        "View Commit ↗",
                        href=commit_url,
                        target="_blank",
                        style={
                            "marginLeft": "12px",
                            "color": "#0366d6",
                            "textDecoration": "none",
                            "fontSize": "12px",
                        },
                    )
                )

            # File X リンクを追加（コミット時点のファイルを参照）
            file_x_url = generate_github_file_url(
                project, file_path_x, start_line_x, end_line_x, commit_hash=commit_hash
            )
            if file_x_url:
                card_content.append(
                    html.A(
                        "File X ↗",
                        href=file_x_url,
                        target="_blank",
                        style={
                            "marginLeft": "12px",
                            "color": "#0366d6",
                            "textDecoration": "none",
                            "fontSize": "12px",
                        },
                    )
                )

            # File Y リンクを追加（コミット時点のファイルを参照）
            file_y_url = generate_github_file_url(
                project, file_path_y, start_line_y, end_line_y, commit_hash=commit_hash
            )
            if file_y_url:
                card_content.append(
                    html.A(
                        "File Y ↗",
                        href=file_y_url,
                        target="_blank",
                        style={
                            "marginLeft": "12px",
                            "color": "#0366d6",
                            "textDecoration": "none",
                            "fontSize": "12px",
                        },
                    )
                )

            # Diff X リンクを追加
            diff_x_url = generate_github_diff_url(project, commit_hash, file_path_x)
            if diff_x_url:
                card_content.append(
                    html.A(
                        "Diff X ↗",
                        href=diff_x_url,
                        target="_blank",
                        style={
                            "marginLeft": "12px",
                            "color": "#28a745",
                            "textDecoration": "none",
                            "fontSize": "12px",
                        },
                    )
                )

            # Diff Y リンクを追加
            diff_y_url = generate_github_diff_url(project, commit_hash, file_path_y)
            if diff_y_url:
                card_content.append(
                    html.A(
                        "Diff Y ↗",
                        href=diff_y_url,
                        target="_blank",
                        style={
                            "marginLeft": "12px",
                            "color": "#28a745",
                            "textDecoration": "none",
                            "fontSize": "12px",
                        },
                    )
                )

            commit_cards.append(
                html.Div(
                    card_content,
                    style={
                        "display": "flex",
                        "alignItems": "center",
                        "padding": "8px 12px",
                        "backgroundColor": "#f6f8fa",
                        "border": "1px solid #e1e4e8",
                        "borderRadius": "6px",
                        "marginBottom": "6px",
                    },
                )
            )

        return html.Div(
            [
                html.H4(
                    "🔄 Co-change History",
                    style={
                        "marginTop": "20px",
                        "marginBottom": "12px",
                        "fontSize": "16px",
                        "fontWeight": "600",
                        "color": "#24292e",
                    },
                ),
                html.Div(
                    f"{len(common_commits)} common commit(s) found",
                    style={
                        "marginBottom": "10px",
                        "fontSize": "12px",
                        "color": "#586069",
                    },
                ),
                html.Div(
                    commit_cards,
                    style={
                        "maxHeight": "200px",
                        "overflowY": "auto",
                    },
                ),
            ],
            style={
                "padding": "15px",
                "backgroundColor": "white",
                "borderTop": "1px solid #e1e4e8",
            },
        )

    except Exception as e:
        logger.warning(
            "Error building co-change history section for clone_id=%s: %s",
            row.get("clone_id"), e
        )
        return _build_no_cochange_message()


def _build_no_cochange_message() -> html.Div:
    """共通コミットがない場合のメッセージを生成する."""
    return html.Div(
        [
            html.H4(
                "🔄 Co-change History",
                style={
                    "marginTop": "20px",
                    "marginBottom": "12px",
                    "fontSize": "16px",
                    "fontWeight": "600",
                    "color": "#24292e",
                },
            ),
            html.Div(
                "No co-changes detected for this clone pair.",
                style={
                    "fontSize": "13px",
                    "color": "#6a737d",
                    "fontStyle": "italic",
                },
            ),
        ],
        style={
            "padding": "15px",
            "backgroundColor": "white",
            "borderTop": "1px solid #e1e4e8",
        },
    )
