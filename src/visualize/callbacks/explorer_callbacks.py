"""エクスプローラー関連のコールバック."""
import logging
import json

import dash
from dash import Input, Output, State, ALL, no_update, html

from ..data_loader import (
    load_and_process_data,
    build_file_tree_data,
    get_clone_related_files,
)
from ..components import (
    build_project_summary,
    create_file_tree_component,
    create_code_editor_view,
    create_clone_list_component,
    build_clone_details_view_single,
)
from ..utils import get_file_content

logger = logging.getLogger(__name__)


def register_explorer_callbacks(app, app_data):
    """エクスプローラー（ファイルツリー・コード表示）関連のコールバックを登録する."""

    # --- New IDE Theme Callbacks ---

    @app.callback(
        [
            Output("file-tree-container", "children"),
            Output("file-tree-data-store", "data"),
            Output("clone-data-store", "data"),
            Output("project-summary-container", "children"),
        ],
        [Input("project-selector", "value")],
        [State("project-selector", "options")],
    )
    def update_project_data(project_value, project_options):
        """プロジェクト選択時にデータをロードし、ツリーとクローンストアを更新"""
        if not project_value:
            return [], {}, [], "Please select a project."

        # Extract selected project info (simple implementation assuming value is just project name or combined string)
        # Assuming project_value is 'project_name|||commit|||language' format based on existing logic
        # But if the user selects from the new dropdown, it might be simpler.
        # Let's adapt to existing format: project|||commit|||default_lang

        try:
            project, commit, lang_from_val = project_value.split("|||", 2)
        except ValueError:
            # If value is just project name (e.g. from URL or clean select)
            project = project_value
            commit = "HEAD"  # fallback
            lang_from_val = None

        target_lang = lang_from_val

        # Load Data
        df, file_ranges, error = load_and_process_data(project, commit, target_lang)

        if df is None:
            return [], {}, [], f"Error loading data: {error}"

        # Generate summary
        summary_view = build_project_summary(
            df, file_ranges, project, commit, target_lang
        )

        # Build Tree
        from ..data_loader import build_file_tree_data, get_clone_related_files
        from ..components import create_file_tree_component

        related_files = get_clone_related_files(df)
        tree_structure = build_file_tree_data(related_files)
        tree_component = create_file_tree_component(tree_structure)

        # Prepare clone data store (minimized)
        # Convert df to dict records for Client-side filtering
        clone_records = df.to_dict("records")

        # Removed generate_clone_id_filter_options logic as we use direct input now

        return tree_component, tree_structure, clone_records, summary_view

    @app.callback(
        [
            Output("editor-content", "children"),
            Output("editor-header", "children"),
            Output("clone-list-container", "children"),
            Output("selected-file-store", "data"),
        ],
        [
            Input({"type": "file-node", "index": ALL}, "n_clicks"),
            Input({"type": "clone-item", "index": ALL}, "n_clicks"),
            Input("scatter-plot", "clickData"),
        ],
        [
            State("clone-data-store", "data"),
            State("project-selector", "value"),
            State("selected-file-store", "data"),
        ],
    )
    def handle_explorer_interaction(
        file_clicks,
        clone_clicks,
        scatter_click,
        clone_data,
        project_value,
        current_file,
    ):
        """ファイルクリックまたはクローンクリック時の処理"""
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

        from ..components import (
            create_code_editor_view,
            create_clone_list_component,
            build_clone_details_view_single,
        )
        from ..utils import get_file_content

        # Project info
        try:
            project, commit, _ = project_value.split("|||", 2)
        except (ValueError, AttributeError):
            project = project_value

        if trigger_id == "scatter-plot":
            if not scatter_click or not clone_data:
                return no_update

            try:
                # customdata[1] is clone_id based on plotting.py
                clone_id = scatter_click["points"][0]["customdata"][1]
                target_clone = next(
                    (c for c in clone_data if str(c["clone_id"]) == str(clone_id)), None
                )

                if target_clone:
                    split_view = build_clone_details_view_single(target_clone, project)
                    view_container = html.Div(
                        split_view,
                        style={"padding": "20px", "height": "100%", "overflow": "auto"},
                    )
                    return (
                        view_container,
                        f"Comparing Clone #{clone_id}",
                        no_update,
                        no_update,
                    )
            except Exception as e:
                logger.error("Error handling scatter click: %s", e)

            return no_update

        try:
            trigger_info = json.loads(trigger_id)
        except (json.JSONDecodeError, TypeError):
            return no_update

        if trigger_info["type"] == "file-node":
            # File Clicked -> Show Code & Clone List
            file_name_short = trigger_info["index"]
            # Reconstruct full path? This is tricky with flat ID.
            # Ideally we traverse the tree or lookup.
            # For now, let's search in clone_data for matching file name (imperfect but works for demo)
            # Better: Store full path in ID or use client-side callback to pass data.
            # Assuming 'index' carries enough info or we scan clone_data

            # Simple scan
            target_file = None
            if not clone_data:
                return no_update

            # Find a clone that has this file name at end of path
            # TODO: Improve this path resolution
            samples = [
                c["file_path_x"]
                for c in clone_data
                if c["file_path_x"].endswith(file_name_short)
            ]
            if not samples:
                samples = [
                    c["file_path_y"]
                    for c in clone_data
                    if c["file_path_y"].endswith(file_name_short)
                ]

            if samples:
                target_file = samples[0]  # Pick first match
            else:
                target_file = f"src/{file_name_short}"  # Guess

            # Filter clones for this file
            related_clones = []
            for c in clone_data:
                if c["file_path_x"] == target_file:
                    related_clones.append(
                        {
                            "clone_id": c["clone_id"],
                            "start_line": int(c["start_line_x"]),
                            "end_line": int(c["end_line_x"]),
                            "partner_path": c["file_path_y"],
                            "partner_start": int(c["start_line_y"]),
                            "partner_end": int(c["end_line_y"]),
                            "similarity": 1.0,  # placeholder
                        }
                    )
                elif c["file_path_y"] == target_file:
                    related_clones.append(
                        {
                            "clone_id": c["clone_id"],
                            "start_line": int(c["start_line_y"]),
                            "end_line": int(c["end_line_y"]),
                            "partner_path": c["file_path_x"],
                            "partner_start": int(c["start_line_x"]),
                            "partner_end": int(c["end_line_x"]),
                            "similarity": 1.0,  # placeholder
                        }
                    )

            # Get Code Content
            content = get_file_content(project, target_file)

            editor_view = create_code_editor_view(content, target_file, related_clones)
            clone_list_view = create_clone_list_component(related_clones)

            return editor_view, f"Editing: {target_file}", clone_list_view, target_file

        elif trigger_info["type"] == "clone-item":
            # Clone Clicked -> Show Split View
            clone_id = trigger_info["index"]  # ID is str

            # Find original row data
            target_clone = next(
                (c for c in clone_data if str(c["clone_id"]) == clone_id), None
            )

            if target_clone:
                split_view = build_clone_details_view_single(target_clone, project)
                # Wrap in container to fit editor area style
                view_container = html.Div(
                    split_view,
                    style={"padding": "20px", "height": "100%", "overflow": "auto"},
                )

                return (
                    view_container,
                    f"Comparing Clone #{clone_id}",
                    no_update,
                    no_update,
                )

        return no_update

