"""data_loaderパッケージ: データ読み込みと前処理を管理する.

旧 data_loader.py の後方互換性を維持しつつ,
プロジェクト発見・CSV読み込み・ファイルツリーの3モジュールに分割.
"""

# --- Project discovery ---
from .project_discovery import (
    load_project_summary,
    load_dashboard_data,
    get_actual_service_count,
    get_available_projects_enhanced,
    get_available_languages,
    get_available_projects,
    get_project_names,
    get_csv_options_for_project,
)

# --- CSV / data loading ---
from .csv_loader import (
    load_service_file_ranges_cached,
    load_full_services_json,
    resolve_services_json_path,
    load_clone_metrics,
    load_service_file_ranges,
    file_id_to_service,
    vectorized_file_id_to_service,
    load_and_process_data,
    load_from_scatter_csv,
    load_from_unified_loader,
    load_from_no_imports_json,
    load_from_project_csv_with_rnr,
    load_from_project_csv,
    load_from_csv_fallback,
    clear_data_cache,
    SCATTER_FILE_COMMIT_PREFIX,
)

# --- File tree ---
from .file_tree import (
    build_file_tree_data,
    get_clone_related_files,
)

# --- Clone metrics (list view) ---
from .metrics_loader import (
    load_metrics_dataframes,
    clear_metrics_cache,
    get_service_table_df,
    get_file_table_df,
    get_cs_table_df,
    read_code_fragment,
)

__all__ = [
    # project_discovery
    "load_project_summary",
    "load_dashboard_data",
    "get_actual_service_count",
    "get_available_projects_enhanced",
    "get_available_languages",
    "get_available_projects",
    "get_project_names",
    "get_csv_options_for_project",
    # csv_loader
    "load_service_file_ranges_cached",
    "load_full_services_json",
    "resolve_services_json_path",
    "load_clone_metrics",
    "load_service_file_ranges",
    "file_id_to_service",
    "vectorized_file_id_to_service",
    "load_and_process_data",
    "load_from_scatter_csv",
    "load_from_unified_loader",
    "load_from_no_imports_json",
    "load_from_project_csv_with_rnr",
    "load_from_project_csv",
    "load_from_csv_fallback",
    "clear_data_cache",
    "SCATTER_FILE_COMMIT_PREFIX",
    # file_tree
    "build_file_tree_data",
    "get_clone_related_files",
    # metrics_loader
    "load_metrics_dataframes",
    "clear_metrics_cache",
    "get_service_table_df",
    "get_file_table_df",
    "get_cs_table_df",
    "read_code_fragment",
]
