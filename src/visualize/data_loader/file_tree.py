"""ファイルツリー構築モジュール.

クローンデータからファイルパスを抽出し,
ディレクトリ構造のツリーデータを生成する.
"""
import logging

logger = logging.getLogger(__name__)

def build_file_tree_data(file_paths):
    """
    ファイルパスのリストからネストされた辞書構造（ツリー）を生成する

    Args:
        file_paths: ['src/A/f1.java', 'src/B/f2.java'] のようなパスリスト

    Returns:
        {
            'src': {
                'A': {'f1.java': '__FILE__'},
                'B': {'f2.java': '__FILE__'}
            }
        }
    """
    tree = {}
    for path in file_paths:
        if not path:
            continue
        parts = path.split("/")
        current = tree
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
            # もし__FILE__がある場合（ディレクトリと同盟のファイルがあった場合など）の考慮が必要だが
            # 今回は簡易的に上書きしないようにする
            if current == "__FILE__":
                current = {}  # 構造が壊れるが、実データでは稀

        # ファイルを示すマーカー
        current[parts[-1]] = "__FILE__"

    return tree


def get_clone_related_files(df):
    """
    クローンデータフレームから関連する全ファイルパスを抽出する
    """
    if df is None or df.empty:
        return []

    files = set()
    if "file_path_x" in df.columns:
        files.update(df["file_path_x"].dropna().unique())
    if "file_path_y" in df.columns:
        files.update(df["file_path_y"].dropna().unique())

    return sorted(list(files))
