"""Shared sidebar navigation definition for Web and Dash pages."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class SidebarNavItem:
    key: str
    label: str
    icon_class: str
    i18n_key: str
    href: str | None = None
    button_id: str | None = None
    hidden: bool = False


SIDEBAR_NAV_ITEMS: tuple[SidebarNavItem, ...] = (
    SidebarNavItem(
        key="settings",
        label="Clone Detection",
        icon_class="bi bi-gear",
        i18n_key="navSettings",
        href="/",
    ),
    SidebarNavItem(
        key="scatter",
        label="Scatter Plot",
        icon_class="bi bi-graph-up",
        i18n_key="navScatter",
        href="/visualize/?view=scatter",
        button_id="btn-view-scatter",
    ),
    SidebarNavItem(
        key="explorer",
        label="List View",
        icon_class="bi bi-list-ul",
        i18n_key="navListView",
        href="/visualize/?view=explorer",
        button_id="btn-view-explorer",
        hidden=True,
    ),
    SidebarNavItem(
        key="stats",
        label="Metric View",
        icon_class="bi bi-funnel",
        i18n_key="navStats",
        href="/visualize/?view=stats",
        button_id="btn-view-stats",
    ),
    SidebarNavItem(
        key="statistics",
        label="Statistics View",
        icon_class="bi bi-bar-chart-line",
        i18n_key="navStatistics",
        href="/visualize/?view=statistics",
        button_id="btn-view-statistics",
    ),
)


def render_static_sidebar_nav(active_key: str = "settings") -> str:
    """Render sidebar nav list items for the Clone Detection static page."""
    rows: list[str] = []
    for item in SIDEBAR_NAV_ITEMS:
        if item.hidden:
            continue
        active = " active" if item.key == active_key else ""
        href = escape(item.href or "#", quote=True)
        rows.append(
            '<li class="nav-item">'
            f'<a href="{href}" class="nav-link{active}">'
            f'<i class="{escape(item.icon_class, quote=True)} nav-icon"></i>'
            f'<span class="nav-text" data-i18n-key="{escape(item.i18n_key, quote=True)}">'
            f"{escape(item.label)}</span>"
            "</a>"
            "</li>"
        )
    return "\n      ".join(rows)


def build_dash_sidebar_nav(active_key: str = "scatter") -> list:
    """Build Dash nav list children from the shared sidebar definition."""
    from dash import html

    children = []
    for item in SIDEBAR_NAV_ITEMS:
        class_name = "nav-link active" if item.key == active_key else "nav-link"
        content = [
            html.I(className=f"{item.icon_class} nav-icon"),
            html.Span(
                item.label,
                className="nav-text",
                **{"data-i18n": item.i18n_key},
            ),
        ]
        if item.button_id is None:
            control = html.A(content, href=item.href or "#", className=class_name)
        else:
            control = html.Button(
                content,
                id=item.button_id,
                className=class_name,
                n_clicks=0,
            )
        style = {"display": "none"} if item.hidden else None
        children.append(html.Li(control, className="nav-item", style=style))
    return children
