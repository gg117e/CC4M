/**
 * Promote dash-table column-header tooltips to `position: fixed` so they
 * escape ancestor `overflow: auto` clipping.
 *
 * Why: the dash-table tooltip is rendered with `position: absolute` inside
 * `.dash-spreadsheet-container`. When the closest scrollable ancestor
 * (e.g. `.stats-table-scroll`) is narrower than the tooltip, the tooltip is
 * clipped — leftmost columns (Clone ID) end up partially hidden behind the
 * adjacent filter sidebar. Converting to fixed positioning preserves the
 * current screen position while removing the clipping.
 */
(function () {
    "use strict";

    function pinTooltip(tooltip) {
        if (!tooltip || tooltip.dataset.fixedPositioned === "1") return;
        // Defer one frame so dash-table can apply its inline top/left first.
        requestAnimationFrame(function () {
            if (!tooltip.isConnected) return;
            var rect = tooltip.getBoundingClientRect();
            tooltip.style.position = "fixed";
            tooltip.style.top = rect.top + "px";
            tooltip.style.left = rect.left + "px";
            tooltip.style.zIndex = "9999";
            tooltip.dataset.fixedPositioned = "1";
        });
    }

    function scan(root) {
        if (!root || root.nodeType !== 1) return;
        if (root.classList && root.classList.contains("dash-tooltip")) {
            pinTooltip(root);
            return;
        }
        if (root.querySelectorAll) {
            root.querySelectorAll(".dash-tooltip").forEach(pinTooltip);
        }
    }

    var observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            mutation.addedNodes.forEach(scan);
        });
    });

    function init() {
        if (!document.body) return;
        observer.observe(document.body, { childList: true, subtree: true });
        scan(document.body);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
