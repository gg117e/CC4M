"""callbacksパッケージ: Dashコールバックの登録を管理する.

旧 callbacks.py の後方互換性を保ちつつ,
各サブモジュールにコールバックを分割する.
"""
import logging

import pandas as pd

from .scatter_callbacks import register_scatter_callbacks
from .explorer_callbacks import register_explorer_callbacks
from .nav_callbacks import register_nav_callbacks
from .filter_callbacks import register_filter_callbacks
from .list_view_callbacks import register_list_view_callbacks
from .stats_callbacks import register_stats_callbacks
from .statistics_callbacks import register_statistics_callbacks

logger = logging.getLogger(__name__)

# データキャッシュ用のグローバル変数 (全コールバックで共有)
app_data = {
    "df": pd.DataFrame(),
    "file_ranges": {},
    "project": "",
    "commit": "",
    "language": "",
    "current_clone": {},
}


def register_callbacks(app):
    """Dashアプリにすべてのコールバックを登録する."""
    register_nav_callbacks(app, app_data)
    register_scatter_callbacks(app, app_data)
    register_explorer_callbacks(app, app_data)
    register_filter_callbacks(app, app_data)
    register_list_view_callbacks(app, app_data)
    register_stats_callbacks(app, app_data)
    register_statistics_callbacks(app, app_data)
    logger.info("All callbacks registered successfully")
