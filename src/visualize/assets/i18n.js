/**
 * i18n text replacement for visualize views.
 *
 * This app now uses English only, and applies the English dictionary
 * to elements with data-i18n / data-i18n-placeholder attributes.
 */
window.dash_clientside = window.dash_clientside || {};

const VIS_I18N = {
  en: {
    // Sidebar navigation
    navSettings: "Clone Detection",
    navScatter: "Scatter Plot",
    navListView: "List View",
    navStats: "Metric View",
    navStatistics: "Statistics View",
    // Sidebar explorer (List View)
    sidebarExplorer: "EXPLORER",
    sidebarCloneOutline: "CLONE OUTLINE",
    editorPlaceholder: "Select a file to view",
    emptyState: "Select a file from the explorer to view its content.",
    // Filters
    filterComod: "Co-modification",
    filterScope: "Scope",
    filterCodeType: "File Category (sets / pairs)",
    filterCloneId: "Clone ID",
    filterManyServices: "Multi-Service Clones",
    filterFocusService: "Focus Service",
    filterRelatedService: "Related Service",
    filterDetails: "Details",
    cloneIdPlaceholder: "Input Clone ID",
    manyServicesPlaceholder: "Select Clone ID (Multi-Service)",
    // Scatter details
    scatterClickHint: "Click a point on the graph to view clone details and code comparison here.",
    // Stats
    statsProjInfo: "Project Info",
    statsServiceInfo: "Service Info",
    statsCloneStats: "Clone Statistics",
    // Project selectors
    labelProject: "Project:",
    labelDataset: "Dataset:",
  },
};

/**
 * Replace text of all elements that have data-i18n attributes.
 * Also supports placeholder replacement via data-i18n-placeholder.
 */
function applyVisLanguage(lang) {
  const dict = VIS_I18N[lang] || VIS_I18N["en"];
  document.querySelectorAll("[data-i18n]").forEach(function (el) {
    var key = el.getAttribute("data-i18n");
    if (key && dict[key] !== undefined) {
      el.textContent = dict[key];
    }
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
    var key = el.getAttribute("data-i18n-placeholder");
    if (key && dict[key] !== undefined) {
      el.setAttribute("placeholder", dict[key]);
    }
  });
  document.documentElement.lang = lang;
}

// Dash clientside callback namespace
dash_clientside.i18n = {
  /**
  * clientside callback: update visible text when lang-store changes.
  * Output target is a hidden dummy node.
   */
  applyLang: function (lang) {
    if (lang) {
      applyVisLanguage(lang);
    }
    return "";
  },
};
