from dash import Dash
import plotly.graph_objects as go
import os
import dash_bootstrap_components as dbc
import sys
from pathlib import Path

# パッケージ未解決時のためにプロジェクトrootをパスに追加
if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.append(str(project_root))
    sys.path.append(str(project_root / "src"))

# 可視化モジュール（パッケージとして実行/スクリプト実行の両対応）
from .data_loader import (
    get_available_projects_enhanced,
    get_available_languages,
    get_project_names,
    load_and_process_data,
)
from .plotting import create_scatter_plot
from .components import create_layout, build_project_summary, create_ide_layout
from .callbacks import register_callbacks, app_data


def create_dash_app(url_base_pathname: str = "/") -> Dash:
    """Dashアプリを作成して返す.

    Args:
        url_base_pathname: ルートパス. 例: "/" または "/visualize/".

    Returns:
        初期化済みDashアプリ.
    """

    # --- アプリケーションの初期化 ---
    # assetsフォルダへの絶対パスを構築
    # __file__ はこのファイル(scatter.py)のパス = src/visualize/scatter.py
    # assets は同じ src/visualize/ ディレクトリ配下にある
    assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

    normalized_prefix = (
        url_base_pathname
        if url_base_pathname.endswith("/")
        else f"{url_base_pathname}/"
    )
    if normalized_prefix == "//":
        normalized_prefix = "/"

    # FastAPI の /visualize マウント配下で動かす場合は,
    # 外部リクエストの prefix だけ /visualize/ にし,
    # Dash 側の内部ルーティングは "/" にする.
    # （Mount で prefix が剥がされて WSGI 側へ渡るため）
    routes_prefix = "/" if normalized_prefix != "/" else "/"

    # assets_folderに絶対パスを指定してDashアプリを初期化
    dash_app = Dash(
        __name__,
        assets_folder=assets_path,
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
        ],
        requests_pathname_prefix=normalized_prefix,
        routes_pathname_prefix=routes_prefix,
    )
    dash_app.title = "CC4M - Code Clone Visualization"
    dash_app.config.suppress_callback_exceptions = True  # 動的コンポーネント用の設定
    dash_app.enable_dev_tools(
        debug=False,
        dev_tools_ui=False,
        dev_tools_props_check=False,
        dev_tools_hot_reload=False,
    )

    def serve_layout():
        """ページアクセス毎にレイアウトを再生成する.

        パイプライン完了後にプロジェクト一覧が更新されるよう,
        毎回 ``get_project_names()`` 等を呼び直す.
        """
        available_projects = get_available_projects_enhanced()
        available_languages = get_available_languages()
        project_names = get_project_names()

        initial_fig = go.Figure().update_layout(title="Please select a Project and Dataset")
        initial_summary = build_project_summary(None, {}, "N/A", "N/A", "N/A")

        return create_ide_layout(
            available_projects,
            available_languages,
            None,
            initial_fig,
            initial_summary,
            project_names=project_names,
        )

    # 関数を代入 → Dash がリクエスト毎に呼び出す
    dash_app.layout = serve_layout
    register_callbacks(dash_app)
    return dash_app


app = create_dash_app("/")

# --- アプリケーションの実行 ---
if __name__ == "__main__":
    app.run(debug=False, port=8050, use_reloader=False, dev_tools_hot_reload=False)
