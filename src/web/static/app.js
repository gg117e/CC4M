// Show/hide conditional fields
const methodSelect = document.getElementById("analysis_method");
const freqParams = document.getElementById("frequency-params");
const detectionSelect = document.getElementById("detection_method");
const tksParams = document.getElementById("tks-params");
const rnrParams = document.getElementById("rnr-params");
const langSelect = document.getElementById("lang_select");
let currentLang = "en";

const DEFAULT_PARAMS = {
  detection_method: "normal",
  tks: 12,
  rnr: 0.5,
  min_tokens: 50,
  import_filter: true,
  generate_scatter_csv: true,
  comod_method: "clone_set",
  analysis_method: "merge_commit",
  analysis_frequency: 50,
  search_depth: -1,
  max_analyzed_commits: -1,
};

function getElementValue(id, fallback) {
  const element = document.getElementById(id);
  return element ? element.value : fallback;
}

function getIntegerValue(id, fallback) {
  const element = document.getElementById(id);
  return element ? parseInt(element.value, 10) : fallback;
}

function getFloatValue(id, fallback) {
  const element = document.getElementById(id);
  return element ? parseFloat(element.value) : fallback;
}

function getCheckedValue(id, fallback) {
  const element = document.getElementById(id);
  return element ? element.checked : fallback;
}

if (methodSelect && freqParams) {
  methodSelect.addEventListener("change", () => {
    freqParams.classList.toggle("visible", methodSelect.value === "frequency");
  });
}
if (detectionSelect) {
  detectionSelect.addEventListener("change", () => {
    if (tksParams) {
      tksParams.classList.toggle("visible", detectionSelect.value === "tks");
    }
    if (rnrParams) {
      rnrParams.classList.toggle("visible", detectionSelect.value === "rnr");
    }
  });
}

// Log helpers
function classifyLine(text) {
  if (text.startsWith("[step")) return "log-step";
  if (text.startsWith("[error")) return "log-error";
  if (text.startsWith("[job")) return "log-job";
  return "log-normal";
}

function appendLog(text) {
  const box = document.getElementById("log-box");
  const span = document.createElement("span");
  span.className = classifyLine(text);
  span.textContent = text + "\n";
  box.appendChild(span);
  box.scrollTop = box.scrollHeight;
}

function isInteger(value) {
  return Number.isInteger(value);
}

function validateParams(params) {
  const errors = [];

  if (!params.url) {
    errors.push("Repository URL is required");
  } else {
    const normalizedUrl =
      typeof params.url === "string"
        ? params.url.trim().replace(/\/+$/, "")
        : "";
    if (!/^https:\/\/github\.com\/[^/\s]+\/[^/\s]+$/.test(normalizedUrl)) {
      errors.push("Repository URL must be a GitHub repository URL");
    }
  }

  if (!["normal", "tks", "rnr"].includes(params.detection_method)) {
    errors.push("Detection method must be one of normal,tks,rnr");
  }
  if (params.detection_method !== "normal") {
    errors.push("TKS and RNR are not implemented");
  }

  if (!isInteger(params.tks) || params.tks <= 0) {
    errors.push("TKS must be an integer greater than 0");
  }
  if (!(params.rnr > 0 && params.rnr <= 1)) {
    errors.push("RNR must satisfy 0 < RNR <= 1");
  }

  if (!isInteger(params.min_tokens) || params.min_tokens <= 0) {
    errors.push("Minimum matching tokens must be an integer greater than 0");
  }

  if (typeof params.import_filter !== "boolean") {
    errors.push("Import filtering must be true/false");
  }

  if (!["clone_set", "clone_pair"].includes(params.comod_method)) {
    errors.push("Co-modification method must be one of clone_set,clone_pair");
  }
  if (params.comod_method !== "clone_set") {
    errors.push("clone_pair is not implemented");
  }

  if (!["merge_commit", "tag", "frequency"].includes(params.analysis_method)) {
    errors.push("Analysis method must be one of merge_commit,tag,frequency");
  }

  if (!isInteger(params.analysis_frequency) || params.analysis_frequency <= 0) {
    errors.push("ANALYSIS_FREQUENCY must be an integer greater than 0");
  }

  if (!isInteger(params.search_depth) || params.search_depth < -1) {
    errors.push("SEARCH_DEPTH must be an integer >= -1");
  }

  if (!isInteger(params.max_analyzed_commits) || params.max_analyzed_commits < -1) {
    errors.push("MAX_ANALYZED_COMMITS must be an integer >= -1");
  }

  return errors;
}

// Start analysis
async function startAnalysis() {
  const url = document.getElementById("url").value.trim();
  if (!url) { alert("Repository URL is required"); return; }

  const params = {
    url,
    detection_method: getElementValue("detection_method", DEFAULT_PARAMS.detection_method),
    tks: getIntegerValue("tks", DEFAULT_PARAMS.tks),
    rnr: getFloatValue("rnr", DEFAULT_PARAMS.rnr),
    min_tokens: getIntegerValue("min_tokens", DEFAULT_PARAMS.min_tokens),
    import_filter: getCheckedValue("import_filter", DEFAULT_PARAMS.import_filter),
    generate_scatter_csv: getCheckedValue(
      "generate_scatter_csv",
      DEFAULT_PARAMS.generate_scatter_csv
    ),
    comod_method: getElementValue("comod_method", DEFAULT_PARAMS.comod_method),
    analysis_method: getElementValue("analysis_method", DEFAULT_PARAMS.analysis_method),
    analysis_frequency: getIntegerValue(
      "analysis_frequency",
      DEFAULT_PARAMS.analysis_frequency
    ),
    search_depth: getIntegerValue("search_depth", DEFAULT_PARAMS.search_depth),
    max_analyzed_commits: getIntegerValue(
      "max_analyzed_commits",
      DEFAULT_PARAMS.max_analyzed_commits
    ),
  };

  const errors = validateParams(params);
  if (errors.length > 0) {
    alert(errors.join("\n"));
    return;
  }

  const btn = document.getElementById("btn-run");
  btn.disabled = true;
  btn.textContent = "Running...";

  const logPanel = document.getElementById("log-panel");
  const logBox = document.getElementById("log-box");
  logBox.innerHTML = "";
  logPanel.classList.add("visible");
  document.getElementById("spinner").style.display = "block";
  document.getElementById("status-text").textContent = "Running...";
  document.getElementById("status-text").className = "";

  try {
    const resp = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    if (!resp.ok) {
      const errData = await resp.json();
      throw new Error(errData.detail || "API validation error");
    }
    const data = await resp.json();
    const jobId = data.job_id;

    // Connect to WebSocket for live logs
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${location.host}/ws/logs/${jobId}`);

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "log") {
        appendLog(msg.line);
      } else if (msg.type === "status") {
        document.getElementById("spinner").style.display = "none";
        if (msg.status === "completed") {
          document.getElementById("status-text").textContent = "Completed";
          document.getElementById("status-text").className = "status-done";
        } else {
          document.getElementById("status-text").textContent = "Error occurred";
          document.getElementById("status-text").className = "status-error";
        }
        btn.disabled = false;
        btn.textContent = "Run Analysis";
        ws.close();
      }
    };

    ws.onerror = () => {
      appendLog("[error] WebSocket connection failed.");
      document.getElementById("spinner").style.display = "none";
      document.getElementById("status-text").textContent = "Connection Error";
      document.getElementById("status-text").className = "status-error";
      btn.disabled = false;
      btn.textContent = "Run Analysis";
    };
  } catch (err) {
    appendLog("[error] " + err.message);
    document.getElementById("spinner").style.display = "none";
    document.getElementById("status-text").textContent = "Error";
    document.getElementById("status-text").className = "status-error";
    btn.disabled = false;
    btn.textContent = "Run Analysis";
  }
}
