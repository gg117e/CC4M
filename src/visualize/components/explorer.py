import logging

from dash import html

logger = logging.getLogger(__name__)

def create_file_tree_component(tree_data, level=0):
    """
    再帰的にファイルツリーコンポーネントを生成する
    tree_data: build_file_tree_dataで生成された辞書
    """
    items = []
    # フォルダとファイルを分離してソート
    folders = sorted([k for k, v in tree_data.items() if v != "__FILE__"])
    files = sorted([k for k, v in tree_data.items() if v == "__FILE__"])

    # フォルダ
    for name in folders:
        # 子要素の生成
        children = create_file_tree_component(tree_data[name], level + 1)

        # Details/Summaryでフォルダ表現
        item = html.Details(
            [
                html.Summary(
                    [
                        html.Span("📂", className="tree-item-icon"),
                        html.Span(name, className="tree-item-label"),
                    ],
                    className="tree-item",
                ),
                html.Div(children, style={"paddingLeft": "10px"}),
            ]
        )
        items.append(item)

    # ファイル
    for name in files:
        # パスの構築はコールバック側でやるのが難しいので、IDに埋め込むなどの工夫が必要だが
        # ここでは簡易的にファイル名を表示し、パスの特定は親コンポーネントの構造に依存するか
        # クライアントサイドコールバックでパスを再構築する
        # とりあえずdata属性にパスを持たせることは標準ではできないので、
        # IDを工夫する: "file-node-{path}" (パス中の/はエスケープが必要かも)
        # 簡易実装として、ここでのパス構築は省略し、callbackで解決する前提とする

        item = html.Div(
            [
                html.Span("📄", className="tree-item-icon"),
                html.Span(name, className="tree-item-label"),
            ],
            className="tree-item file-node",
            id={"type": "file-node", "index": name},
        )
        # IDだけではパスが一意にならないので実運用ではフルパスが必要
        items.append(item)

    return items


def create_clone_list_component(clones):
    """
    クローンリストコンポーネントを生成する
    clones: 辞書またはDfのリスト format [{'id': 1, 'partner': 'xxx', 'similarity': 0.8}, ...]
    """
    if not clones:
        return html.Div(
            "No clones found in this file.", style={"padding": "10px", "color": "#999"}
        )

    items = []
    for clone in clones:
        item = html.Div(
            [
                html.Div(
                    [
                        html.Span(f"Clone #{clone['clone_id']}", className="clone-id"),
                        html.Span(
                            f"Line {clone['start_line']}-{clone['end_line']}",
                            style={"fontSize": "11px", "color": "#888"},
                        ),
                    ],
                    className="clone-list-info",
                ),
                html.Div(f"vs {clone['partner_path']}", className="clone-file"),
                html.Div(
                    f"Lines {clone['partner_start']}-{clone['partner_end']}",
                    style={"fontSize": "11px", "color": "#888", "textAlign": "right"},
                ),
            ],
            className="clone-list-item",
            id={"type": "clone-item", "index": str(clone["clone_id"])},
        )
        items.append(item)

    return items


def create_code_editor_view(code_content, file_path, clones=None, start_line=1):
    """
    コードエディタビューを生成する
    code_content: ファイルの中身
    clones: ハイライトすべきクローン情報のリスト
    """
    lines = code_content.splitlines()
    line_elements = []
    code_elements = []

    # マーカーの生成（ハイライト）
    markers = []
    if clones:
        for clone in clones:
            # 1-based index to 0-based index and relative pixel calculation is hard in pure CSS
            # ここでは単純に行背景色を変えるためのクラスを付与する方式はHTML構造上難しいので
            # 行ごとに要素を生成する
            pass

    for i, line in enumerate(lines):
        ln = i + start_line

        # 行に関連するクローンがあるかチェック
        is_cloned = False
        if clones:
            for clone in clones:
                if clone["start_line"] <= ln <= clone["end_line"]:
                    is_cloned = True
                    break

        # Line Number
        line_elements.append(html.Div(str(ln), className="code-line"))

        # Code Line
        style = {}
        if is_cloned:
            style["backgroundColor"] = "rgba(144, 238, 144, 0.1)"

        code_elements.append(
            html.Div(line if line else " ", className="code-line", style=style)
        )

    return html.Div(
        [
            html.Div(line_elements, className="line-numbers"),
            html.Div(code_elements, className="code-lines"),
        ],
        className="code-container",
    )


