"""UI components package for MSCC visualization.

All public symbols are re-exported here for backward compatibility.
"""

from .clone_metrics import (
    calculate_unique_pair_count_for_clone,
    calculate_cross_service_metrics,
    generate_cross_service_filter_options,
    get_github_base_url,
    generate_github_file_url,
    find_overlapping_clones,
    build_clone_selector,
    build_clone_selector_options,
)
from .layout import (
    create_layout,
    create_ide_layout,
)
from .list_view import (
    create_list_view_layout,
    build_breadcrumb,
    build_detail_panel,
)
from .stats_metrics_explorer import create_stats_metrics_explorer
from .summary import (
    create_help_section,
    build_dashboard_view,
    build_project_summary,
    create_info_table,
    create_service_table,
    create_project_clone_ratio_display,
    create_stats_header,
)
from .clone_detail import (
    build_clone_details_view,
    build_clone_details_view_single,
)
from .explorer import (
    create_file_tree_component,
    create_clone_list_component,
    create_code_editor_view,
)

__all__ = [
    "calculate_unique_pair_count_for_clone",
    "calculate_cross_service_metrics",
    "generate_cross_service_filter_options",
    "get_github_base_url",
    "generate_github_file_url",
    "find_overlapping_clones",
    "build_clone_selector",
    "build_clone_selector_options",
    "create_layout",
    "create_ide_layout",
    "create_list_view_layout",
    "create_stats_metrics_explorer",
    "create_help_section",
    "build_dashboard_view",
    "build_project_summary",
    "create_info_table",
    "create_service_table",
    "create_project_clone_ratio_display",
    "create_stats_header",
    "build_clone_details_view",
    "build_clone_details_view_single",
    "create_file_tree_component",
    "create_clone_list_component",
    "create_code_editor_view",
]
