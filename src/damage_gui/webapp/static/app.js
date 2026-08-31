(() => {
  "use strict";

  const state = {
    health: null,
    models: [],
    selectedModel: null,
    prediction: null,
    aim: null,
    history: [],
    historyTotal: 0,
    historyOffset: 0,
    historyLimit: 20,
    batchFile: null,
    batchJob: null,
    batchPollTimer: null,
    activePanel: "prediction",
    busy: false,
    imageMode: "fit",
  };

  class ApiError extends Error {
    constructor(message, status = 0) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  }

  const api = {
    baseUrl: String(window.DAMAGE_GUI_API_BASE || "").replace(/\/+$/, ""),

    resolve(path) {
      if (!path) return this.baseUrl || "/";
      if (/^https?:\/\//i.test(path)) return path;
      return `${this.baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
    },

    async request(path, options = {}) {
      const headers = new Headers(options.headers || {});
      if (options.body !== undefined && !headers.has("content-type")) {
        headers.set("content-type", "application/json");
      }
      let response;
      try {
        response = await fetch(this.resolve(path), { ...options, headers });
      } catch (_error) {
        throw new ApiError("API unavailable");
      }

      const text = await response.text();
      let body = null;
      if (text) {
        try { body = JSON.parse(text); } catch (_error) { body = text; }
      }
      if (!response.ok) {
        const detail = body && typeof body === "object" ? body.detail : null;
        const message = detail || `Request failed (${response.status})`;
        throw new ApiError(String(message), response.status);
      }
      return body;
    },

    health() { return this.request("/api/health"); },
    listModels() { return this.request("/api/models"); },
    getModel(modelId) { return this.request(`/api/models/${encodeURIComponent(modelId)}`); },
    predict(payload) {
      return this.request("/api/predict", { method: "POST", body: JSON.stringify(payload) });
    },
    aim(payload) {
      return this.request("/api/aim", { method: "POST", body: JSON.stringify(payload) });
    },
    history(limit, offset) {
      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      return this.request(`/api/history?${params}`);
    },
    result(runId) { return this.request(`/api/results/${encodeURIComponent(runId)}`); },
    submitBatch(file, modelId) {
      const headers = {
        "content-type": file.type || "text/csv",
        "x-filename": file.name,
      };
      const query = modelId ? `?model_id=${encodeURIComponent(modelId)}` : "";
      return this.request(`/api/batch${query}`, { method: "POST", body: file, headers });
    },
    job(jobId) { return this.request(`/api/jobs/${encodeURIComponent(jobId)}`); },
    jobResult(jobId) { return this.request(`/api/jobs/${encodeURIComponent(jobId)}/result`); },
    cancelJob(jobId) {
      return this.request(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
    },
    link(path) { return this.resolve(path); },
  };

  const $ = (id) => document.getElementById(id);
  const app = $("app");
  const elements = {
    serverStatus: $("server-status"),
    serverVersion: $("server-version"),
    refresh: $("refresh-button"),
    toolbarModel: $("toolbar-model"),
    toolbarRun: $("toolbar-run"),
    navApiMode: $("nav-api-mode"),
    propertiesContext: $("properties-context"),
    modelSelect: $("model-select"),
    modelEmpty: $("model-empty"),
    modelSummary: $("model-summary"),
    modelMetadata: $("model-metadata"),
    validationEmpty: $("validation-empty"),
    validationSummary: $("validation-summary"),
    predictionForm: $("prediction-form"),
    predictionSubmit: $("prediction-submit"),
    predictionMessage: $("prediction-form-message"),
    aimForm: $("aim-form"),
    aimSubmit: $("aim-submit"),
    aimMessage: $("aim-form-message"),
    spreadMode: $("spread-mode"),
    cepFields: $("cep-fields"),
    repDepFields: $("rep-dep-fields"),
    historyRefresh: $("history-refresh"),
    historyCount: $("history-count"),
    historyState: $("history-state"),
    historyTable: $("history-table"),
    historyBody: $("history-body"),
    historyPrev: $("history-prev"),
    historyNext: $("history-next"),
    batchFile: $("batch-file"),
    batchFileMeta: $("batch-file-meta"),
    batchSubmit: $("batch-submit"),
    batchCancel: $("batch-cancel"),
    batchProgressBlock: $("batch-progress-block"),
    batchProgressText: $("batch-progress-text"),
    batchProgressStage: $("batch-progress-stage"),
    batchProgressFill: $("batch-progress-fill"),
    batchMessage: $("batch-message"),
    batchDownload: $("batch-download"),
    exportEmpty: $("export-empty"),
    exportSummary: $("export-summary"),
    exportPng: $("export-png"),
    exportCsv: $("export-csv"),
    viewportTitle: $("viewport-title"),
    viewportSubtitle: $("viewport-subtitle"),
    viewportBadge: $("viewport-badge"),
    fit: $("fit-button"),
    actual: $("actual-button"),
    viewportDownload: $("viewport-download"),
    plotSurface: $("plot-surface"),
    viewportLoading: $("viewport-loading"),
    viewportEmpty: $("viewport-empty"),
    resultImage: $("result-image"),
    resultsRun: $("results-run"),
    resultsEmpty: $("results-empty"),
    resultsContent: $("results-content"),
    fieldSummary: $("field-summary"),
    resultValidation: $("result-validation"),
    resultOod: $("result-ood"),
    runSummary: $("run-summary"),
    adviceSummary: $("advice-summary"),
    aimResultSection: $("aim-result-section"),
    aimSummary: $("aim-summary"),
    batchResultSection: $("batch-result-section"),
    batchResultSummary: $("batch-result-summary"),
    batchResultDownload: $("batch-result-download"),
    statusIndicator: $("status-indicator"),
    statusMessage: $("status-message"),
    statusDetail: $("status-detail"),
  };

  function setText(element, value) {
    element.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
  }

  function formatNumber(value, digits = 3) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(number);
  }

  function formatPercent(value, digits = 2) {
    const number = Number(value);
    return Number.isFinite(number) ? `${formatNumber(number * 100, digits)}%` : "—";
  }

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value || "—") : date.toLocaleString();
  }

  function shortId(value) {
    const text = String(value || "—");
    return text.length > 12 ? `${text.slice(0, 8)}…${text.slice(-4)}` : text;
  }

  function humanLabel(key) {
    const known = {
      MeanRelativeError: "Mean relative error",
      P95HybridError: "P95 hybrid error",
      mean_relative_error: "Mean relative error",
      p95_hybrid_error: "P95 hybrid error",
      train_time_seconds: "Train time",
      validation_mode: "Validation mode",
      model_type: "Model type",
      damage_level: "Damage level",
      training_samples: "Training samples",
      app_version: "App version",
      created_at: "Created",
      schema_version: "Schema version",
      model_format_version: "Model format",
      training_data_hash: "Training data hash",
      code_commit: "Code commit",
    };
    return known[key] || String(key).replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function formatValue(value, key = "") {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (typeof value === "number") {
      if (key.toLowerCase().includes("time") && key.toLowerCase().includes("second")) return `${formatNumber(value)} s`;
      if (key.toLowerCase().includes("error") || key.toLowerCase().includes("relative")) return formatPercent(value);
      return formatNumber(value);
    }
    if (Array.isArray(value)) return value.join(" × ");
    if (typeof value === "object") return "Available";
    return String(value);
  }

  function renderPropertyList(element, entries) {
    element.replaceChildren();
    for (const entry of entries) {
      if (!entry || entry.value === undefined) continue;
      const label = document.createElement("dt");
      label.textContent = entry.label;
      const value = document.createElement("dd");
      value.textContent = entry.value === null ? "—" : String(entry.value);
      if (entry.className) value.className = entry.className;
      element.append(label, value);
    }
  }

  function setStatus(message, detail = "", kind = "neutral") {
    setText(elements.statusMessage, message);
    elements.statusDetail.textContent = detail || "";
    elements.statusIndicator.className = `status-dot status-dot-${kind === "ok" ? "ok" : kind === "running" ? "running" : kind === "error" ? "error" : "neutral"}`;
  }

  function showFormMessage(element, message = "") {
    element.textContent = message;
    element.hidden = !message;
  }

  function setServerState(online, message = "") {
    elements.serverStatus.className = `status-text ${online ? "status-good" : "status-error"}`;
    elements.serverStatus.textContent = online ? "Online" : "API unavailable";
    if (message) setStatus(message, "", "error");
  }

  function readNumber(id) {
    const value = $(id).value.trim();
    if (!value) return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function selectedModelId() { return elements.modelSelect.value || null; }

  function updateControlState() {
    const batchActive = Boolean(state.batchJob && !["SUCCEEDED", "FAILED", "CANCELLED"].includes(state.batchJob.state));
    const canPredict = Boolean(state.selectedModel && !state.busy && !batchActive);
    elements.predictionSubmit.disabled = !canPredict;
    elements.toolbarRun.disabled = !canPredict;
    elements.aimSubmit.disabled = !(state.prediction && !state.busy && !batchActive);
    elements.modelSelect.disabled = state.busy || state.models.length === 0;
    elements.batchSubmit.disabled = !Boolean(state.selectedModel && state.batchFile && !state.busy && !batchActive);
    elements.batchCancel.disabled = !batchActive;
  }

  function renderHealth() {
    const health = state.health;
    if (!health) return;
    setServerState(true);
    setText(elements.serverVersion, health.version);
  }

  function renderModelDetails(model) {
    const metadata = model && model.metadata && typeof model.metadata === "object" ? model.metadata : {};
    const active = Boolean(state.health && state.health.active_model_id === model?.model_id);
    renderPropertyList(elements.modelSummary, [
      { label: "Model ID", value: model?.model_id || "—" },
      { label: "Type", value: model?.model_type || "—" },
      { label: "Damage level", value: model?.damage_level || "—" },
      { label: "Training samples", value: formatValue(model?.training_samples, "training_samples") },
      { label: "Active", value: active ? "Yes" : "No", className: active ? "status-good" : "" },
    ]);

    const metadataEntries = [
      "app_version", "created_at", "schema_version", "model_format_version",
      "training_data_hash", "code_commit",
    ].filter((key) => metadata[key] !== undefined).map((key) => ({
      label: humanLabel(key), value: formatValue(metadata[key], key),
    }));
    renderPropertyList(elements.modelMetadata, metadataEntries);
  }

  function renderValidation(model) {
    const validation = model?.metadata?.validation;
    const entries = validation && typeof validation === "object"
      ? Object.entries(validation)
        .filter(([, value]) => value === null || ["string", "number", "boolean"].includes(typeof value))
        .map(([key, value]) => ({ label: humanLabel(key), value: formatValue(value, key) }))
      : [];
    elements.validationEmpty.hidden = entries.length > 0;
    renderPropertyList(elements.validationSummary, entries);
  }

  function renderModels() {
    const current = state.selectedModel?.model_id;
    elements.modelSelect.replaceChildren();
    for (const model of state.models) {
      const option = document.createElement("option");
      option.value = model.model_id;
      option.textContent = model.model_id;
      elements.modelSelect.append(option);
    }
    elements.modelEmpty.hidden = state.models.length !== 0;
    elements.modelSelect.hidden = state.models.length === 0;
    if (!state.models.length) {
      state.selectedModel = null;
      setText(elements.toolbarModel, "No model selected");
      renderModelDetails(null);
      renderValidation(null);
      updateControlState();
      return;
    }
    const preferred = state.models.some((model) => model.model_id === current)
      ? current
      : state.health?.active_model_id && state.models.some((model) => model.model_id === state.health.active_model_id)
        ? state.health.active_model_id
        : state.models[0].model_id;
    elements.modelSelect.value = preferred;
    setText(elements.toolbarModel, preferred);
  }

  async function selectModel(modelId, { quiet = false } = {}) {
    if (!modelId) return;
    try {
      const model = await api.getModel(modelId);
      state.selectedModel = model;
      elements.modelSelect.value = model.model_id;
      setText(elements.toolbarModel, model.model_id);
      renderModelDetails(model);
      renderValidation(model);
      updateControlState();
      if (!quiet) setStatus(`Model selected · ${model.model_id}`, "", "ok");
    } catch (error) {
      state.selectedModel = null;
      updateControlState();
      setServerState(false, error.message);
    }
  }

  async function refreshModels() {
    const models = await api.listModels();
    state.models = Array.isArray(models) ? models : [];
    renderModels();
    if (state.models.length) await selectModel(elements.modelSelect.value, { quiet: true });
    updateControlState();
  }

  function renderViewport(prediction) {
    if (!prediction) {
      elements.viewportSubtitle.textContent = "Run a prediction to load the server-rendered damage field.";
      elements.viewportBadge.className = "result-badge";
      elements.viewportBadge.textContent = "NO RESULT";
      elements.viewportDownload.href = "#";
      elements.viewportDownload.classList.add("is-disabled");
      elements.viewportEmpty.hidden = false;
      elements.resultImage.hidden = true;
      return;
    }
    const condition = prediction.condition;
    elements.viewportSubtitle.textContent = `h = ${formatNumber(condition.h)} mm · v = ${formatNumber(condition.v)} m/s · θ = ${formatNumber(condition.deg)}°`;
    elements.viewportBadge.className = "result-badge is-ready";
    elements.viewportBadge.textContent = "RESULT READY";
    elements.viewportDownload.href = api.link(prediction.links.png);
    elements.viewportDownload.classList.remove("is-disabled");
  }

  function renderResults(prediction) {
    const hasPrediction = Boolean(prediction);
    if (hasPrediction) renderBatchResult(null);
    elements.resultsEmpty.hidden = hasPrediction;
    elements.resultsContent.hidden = !hasPrediction;
    setText(elements.resultsRun, prediction ? shortId(prediction.run_id) : "NO RUN");
    if (!prediction) {
      renderPropertyList(elements.fieldSummary, []);
      renderPropertyList(elements.resultValidation, []);
      renderPropertyList(elements.resultOod, []);
      renderPropertyList(elements.runSummary, []);
      renderPropertyList(elements.adviceSummary, []);
      elements.aimResultSection.hidden = true;
      return;
    }

    renderPropertyList(elements.fieldSummary, [
      { label: "Peak intensity", value: formatNumber(prediction.peak_intensity) },
      { label: "Damaged area", value: formatPercent(prediction.damage_area_ratio) },
    ]);

    const metrics = prediction.metrics && typeof prediction.metrics === "object" ? prediction.metrics : null;
    const validationEntries = metrics
      ? Object.entries(metrics).map(([key, value]) => ({ label: humanLabel(key), value: formatValue(value, key) }))
      : [{ label: "Metrics", value: "Not available for this run" }];
    renderPropertyList(elements.resultValidation, validationEntries);

    const ood = prediction.ood;
    renderPropertyList(elements.resultOod, ood ? [
      { label: "Confidence", value: prediction.confidence || "—" },
      { label: "OOD level", value: ood.level_label || ood.level, className: ood.is_extrapolation ? "status-warn" : "status-good" },
      { label: "Distance", value: formatNumber(ood.distance) },
      { label: "Extrapolation", value: ood.is_extrapolation ? "Yes" : "No", className: ood.is_extrapolation ? "status-warn" : "status-good" },
      { label: "In hull", value: ood.in_hull === null ? "—" : (ood.in_hull ? "Yes" : "No") },
      { label: "Local support", value: ood.local_support === null ? "—" : (ood.local_support ? "Yes" : "No") },
    ] : [
      { label: "Confidence", value: prediction.confidence || "—" },
      { label: "OOD", value: "Not available" },
    ]);

    renderPropertyList(elements.runSummary, [
      { label: "Run ID", value: prediction.run_id },
      { label: "Model", value: prediction.model?.model_id || "—" },
      { label: "Elapsed", value: `${formatNumber(prediction.elapsed_ms, 0)} ms` },
    ]);
    const advice = prediction.advice || {};
    const adviceEntries = [
      { label: "Truth available", value: advice.has_truth ? "Yes" : "No" },
      { label: "Focus damage", value: advice.has_focus_damage ? "Yes" : "No" },
      { label: "Scope", value: advice.scope || "—" },
    ];
    if (advice.ood_geometry_reason) adviceEntries.push({ label: "OOD note", value: advice.ood_geometry_reason });
    renderPropertyList(elements.adviceSummary, adviceEntries);
    renderAimResult(state.aim);
  }

  function renderAimResult(aim) {
    elements.aimResultSection.hidden = !aim;
    if (!aim) {
      renderPropertyList(elements.aimSummary, []);
      return;
    }
    renderPropertyList(elements.aimSummary, [
      { label: "Best x", value: formatNumber(aim.best_x) },
      { label: "Best y", value: formatNumber(aim.best_y) },
      { label: "Vmax", value: formatNumber(aim.vmax) },
      { label: "Relative gain", value: formatPercent(aim.gain_relative) },
      { label: "Shift distance", value: formatNumber(aim.shift_distance) },
      { label: "σx / σy", value: `${formatNumber(aim.sigma_x)} / ${formatNumber(aim.sigma_y)}` },
      { label: "ρ", value: formatNumber(aim.rho) },
      { label: "Field shape", value: Array.isArray(aim.value_field_shape) ? aim.value_field_shape.join(" × ") : "—" },
    ]);
  }

  function isTerminalJob(job) {
    return Boolean(job && ["SUCCEEDED", "FAILED", "CANCELLED"].includes(job.state));
  }

  function renderBatchFile(file) {
    if (!file) {
      renderPropertyList(elements.batchFileMeta, []);
      return;
    }
    renderPropertyList(elements.batchFileMeta, [
      { label: "Name", value: file.name },
      { label: "Size", value: `${formatNumber(file.size / 1024, 1)} KB` },
      { label: "Type", value: file.type || "text/csv" },
    ]);
  }

  function renderBatchJob(job) {
    if (!job) {
      elements.batchProgressBlock.hidden = true;
      elements.batchCancel.disabled = true;
      return;
    }
    const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
    elements.batchProgressBlock.hidden = false;
    elements.batchProgressText.textContent = `Batch · ${formatNumber(job.completed, 0)} / ${formatNumber(job.total, 0)} · ${progress}%`;
    elements.batchProgressStage.textContent = job.stage || job.state;
    elements.batchProgressFill.style.width = `${progress}%`;
    elements.batchProgressFill.setAttribute("aria-valuenow", String(progress));
    elements.batchDownload.hidden = !job.links?.csv;
    if (job.links?.csv) elements.batchDownload.href = api.link(job.links.csv);
    updateControlState();
  }

  function renderBatchResult(result) {
    const summary = result?.summary && typeof result.summary === "object" ? result.summary : {};
    elements.batchResultSection.hidden = !result;
    if (!result) {
      renderPropertyList(elements.batchResultSummary, []);
      elements.batchResultDownload.hidden = true;
      return;
    }
    renderPropertyList(elements.batchResultSummary, [
      { label: "State", value: result.state || "—", className: result.state === "SUCCEEDED" ? "status-good" : result.state === "FAILED" ? "status-error" : "status-warn" },
      { label: "Completed", value: `${formatNumber(summary.completed, 0)} / ${formatNumber(summary.total, 0)}` },
      { label: "Successful rows", value: formatNumber(summary.success_count, 0) },
      { label: "Failed rows", value: formatNumber(summary.failed_count, 0), className: summary.failed_count ? "status-warn" : "" },
      { label: "Duration", value: `${formatNumber(summary.duration_ms, 0)} ms` },
      { label: "Row errors", value: formatNumber(summary.row_error_count, 0) },
    ]);
    elements.batchResultDownload.hidden = !result.links?.csv;
    if (result.links?.csv) elements.batchResultDownload.href = api.link(result.links.csv);
  }

  function loadPredictionImage(prediction) {
    elements.plotSurface.setAttribute("aria-busy", "true");
    elements.viewportLoading.hidden = false;
    elements.viewportEmpty.hidden = true;
    elements.resultImage.hidden = false;
    elements.resultImage.className = `result-image ${state.imageMode}`;
    elements.resultImage.onload = () => {
      elements.plotSurface.setAttribute("aria-busy", "false");
      elements.viewportLoading.hidden = true;
      setStatus(`Prediction complete · ${formatNumber(prediction.elapsed_ms, 0)} ms`, `${prediction.model.model_id} · PNG ready`, "ok");
    };
    elements.resultImage.onerror = () => {
      elements.plotSurface.setAttribute("aria-busy", "false");
      elements.viewportLoading.hidden = true;
      setStatus("Result image unavailable", "The structured result is still available", "error");
    };
    elements.resultImage.src = api.link(prediction.links.png);
  }

  function setBusy(value, message = "") {
    state.busy = value;
    updateControlState();
    if (value && message) setStatus(message, "", "running");
  }

  async function runPrediction(event) {
    event?.preventDefault();
    showFormMessage(elements.predictionMessage);
    if (!state.selectedModel) {
      showFormMessage(elements.predictionMessage, "Select an available server model first.");
      return;
    }
    const h = readNumber("condition-h");
    const v = readNumber("condition-v");
    const deg = readNumber("condition-deg");
    if ([h, v, deg].some((value) => value === null)) {
      showFormMessage(elements.predictionMessage, "Enter finite values for h, v, and θ.");
      return;
    }
    setBusy(true, "Running prediction...");
    try {
      const prediction = await api.predict({ h, v, deg, model_id: state.selectedModel.model_id });
      state.prediction = prediction;
      state.aim = null;
      renderViewport(prediction);
      renderResults(prediction);
      renderExport(prediction);
      loadPredictionImage(prediction);
      showFormMessage(elements.predictionMessage);
    } catch (error) {
      showFormMessage(elements.predictionMessage, error.message);
      setStatus(error.message, "Prediction request failed", "error");
    } finally {
      setBusy(false);
    }
  }

  function updateAimFields() {
    const cepMode = elements.spreadMode.value === "CEP";
    elements.cepFields.hidden = !cepMode;
    elements.repDepFields.hidden = cepMode;
  }

  async function runAim(event) {
    event?.preventDefault();
    showFormMessage(elements.aimMessage);
    if (!state.prediction) {
      showFormMessage(elements.aimMessage, "Run a prediction before AIM optimization.");
      return;
    }
    const spreadMode = elements.spreadMode.value;
    const payload = {
      run_id: state.prediction.run_id,
      spread_mode: spreadMode,
      reliability: readNumber("aim-reliability"),
      kernel_method: "cell_integrated",
    };
    if (payload.reliability === null) {
      showFormMessage(elements.aimMessage, "Enter a finite reliability value.");
      return;
    }
    if (spreadMode === "CEP") {
      payload.cep = readNumber("aim-cep");
      if (payload.cep === null) {
        showFormMessage(elements.aimMessage, "Enter CEP for the selected spread model.");
        return;
      }
    } else {
      payload.rep = readNumber("aim-rep");
      payload.dep = readNumber("aim-dep");
      payload.rho = readNumber("aim-rho");
      payload.theta_deg = readNumber("aim-theta");
      if ([payload.rep, payload.dep].some((value) => value === null)) {
        showFormMessage(elements.aimMessage, "Enter both REP and DEP for the selected spread model.");
        return;
      }
      if (payload.rho === null) payload.rho = 0;
    }
    setBusy(true, "Running AIM optimization...");
    try {
      state.aim = await api.aim(payload);
      renderAimResult(state.aim);
      setStatus("AIM complete", `${state.aim.spread_mode} · summary ready`, "ok");
      showFormMessage(elements.aimMessage);
    } catch (error) {
      showFormMessage(elements.aimMessage, error.message);
      setStatus(error.message, "AIM request failed", "error");
    } finally {
      setBusy(false);
    }
  }

  function scheduleBatchPoll(delay = 700) {
    if (state.batchPollTimer) window.clearTimeout(state.batchPollTimer);
    state.batchPollTimer = window.setTimeout(pollBatchJob, delay);
  }

  async function pollBatchJob() {
    state.batchPollTimer = null;
    if (!state.batchJob || isTerminalJob(state.batchJob)) return;
    try {
      state.batchJob = await api.job(state.batchJob.job_id);
      renderBatchJob(state.batchJob);
      if (isTerminalJob(state.batchJob)) {
        const result = await api.jobResult(state.batchJob.job_id);
        renderBatchResult(result);
        setStatus(
          state.batchJob.state === "SUCCEEDED" ? "Batch complete" : `Batch ${state.batchJob.state.toLowerCase()}`,
          `${formatNumber(state.batchJob.completed, 0)} / ${formatNumber(state.batchJob.total, 0)} rows`,
          state.batchJob.state === "SUCCEEDED" ? "ok" : "error",
        );
      } else {
        setStatus("Batch running...", `${formatNumber(state.batchJob.completed, 0)} / ${formatNumber(state.batchJob.total, 0)} rows`, "running");
        scheduleBatchPoll();
      }
    } catch (error) {
      setStatus(error.message, "Batch status request failed", "error");
      scheduleBatchPoll(2000);
    }
  }

  async function runBatch() {
    showFormMessage(elements.batchMessage);
    if (!state.selectedModel || !state.batchFile) {
      showFormMessage(elements.batchMessage, "Select a server model and CSV file first.");
      return;
    }
    setBusy(true, "Submitting batch...");
    try {
      state.batchJob = await api.submitBatch(state.batchFile, state.selectedModel.model_id);
      renderBatchJob(state.batchJob);
      renderBatchResult(null);
      showFormMessage(elements.batchMessage);
      setStatus("Batch queued", `${formatNumber(state.batchJob.total, 0)} rows`, "running");
      scheduleBatchPoll(250);
    } catch (error) {
      showFormMessage(elements.batchMessage, error.message);
      setStatus(error.message, "Batch submission failed", "error");
    } finally {
      setBusy(false);
    }
  }

  async function cancelBatch() {
    if (!state.batchJob || isTerminalJob(state.batchJob)) return;
    try {
      state.batchJob = await api.cancelJob(state.batchJob.job_id);
      renderBatchJob(state.batchJob);
      setStatus("Cancelling batch...", "Cancellation is cooperative", "running");
      if (isTerminalJob(state.batchJob)) {
        renderBatchResult(await api.jobResult(state.batchJob.job_id));
      } else {
        scheduleBatchPoll(250);
      }
    } catch (error) {
      showFormMessage(elements.batchMessage, error.message);
      setStatus(error.message, "Batch cancellation failed", "error");
    }
  }

  function renderExport(prediction) {
    const enabled = Boolean(prediction);
    elements.exportEmpty.hidden = enabled;
    elements.exportSummary.replaceChildren();
    elements.exportPng.hidden = !enabled;
    elements.exportCsv.hidden = !enabled;
    if (!enabled) return;
    elements.exportSummary.append(...(() => {
      const dl = document.createElement("dt");
      dl.textContent = "Run ID";
      const dd = document.createElement("dd");
      dd.textContent = prediction.run_id;
      return [dl, dd];
    })());
    elements.exportPng.href = api.link(prediction.links.png);
    elements.exportCsv.href = api.link(prediction.links.csv);
  }

  function renderHistory(body) {
    state.history = Array.isArray(body?.items) ? body.items : [];
    state.historyTotal = Number(body?.total || 0);
    state.historyOffset = Number(body?.offset || 0);
    state.historyLimit = Number(body?.limit || state.historyLimit);
    elements.historyCount.textContent = `${state.historyTotal} record${state.historyTotal === 1 ? "" : "s"}`;
    elements.historyBody.replaceChildren();
    for (const item of state.history) {
      const row = document.createElement("tr");
      row.tabIndex = 0;
      row.dataset.historyId = item.id;
      for (const value of [shortId(item.id), item.kind || "—", item.status || "—", formatDate(item.created_at)]) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      }
      row.addEventListener("click", () => openHistoryResult(item));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openHistoryResult(item); }
      });
      elements.historyBody.append(row);
    }
    const hasRows = state.history.length > 0;
    elements.historyState.hidden = hasRows;
    elements.historyState.textContent = hasRows ? "" : "No traceability records returned.";
    elements.historyTable.hidden = !hasRows;
    elements.historyPrev.disabled = state.historyOffset <= 0;
    elements.historyNext.disabled = state.historyOffset + state.history.length >= state.historyTotal;
  }

  async function refreshHistory() {
    elements.historyState.hidden = false;
    elements.historyState.textContent = "Loading history...";
    try {
      const body = await api.history(state.historyLimit, state.historyOffset);
      renderHistory(body);
    } catch (error) {
      elements.historyTable.hidden = true;
      elements.historyState.hidden = false;
      elements.historyState.textContent = error.message;
      setStatus(error.message, "History request failed", "error");
    }
  }

  async function openHistoryResult(item) {
    const runId = item.id;
    setStatus("Loading result...", shortId(runId), "running");
    try {
      if (item.kind === "prediction") {
        const prediction = await api.result(runId);
        state.prediction = prediction;
        state.aim = null;
        renderViewport(prediction);
        renderResults(prediction);
        renderExport(prediction);
        loadPredictionImage(prediction);
        setActivePanel("prediction");
      } else if (item.kind === "aim") {
        const job = await api.jobResult(runId);
        const prediction = await api.result(job.summary.run_id);
        state.prediction = prediction;
        state.aim = job.summary;
        renderViewport(prediction);
        renderResults(prediction);
        renderExport(prediction);
        loadPredictionImage(prediction);
        setActivePanel("aim");
      } else if (item.kind === "batch_prediction") {
        state.batchJob = await api.job(runId);
        renderBatchJob(state.batchJob);
        renderBatchResult(await api.jobResult(runId));
        setActivePanel("batch");
      } else {
        setStatus("No browser result attached", `${shortId(runId)} · unsupported history type`, "neutral");
      }
    } catch (error) {
      setStatus("No browser result attached", `${shortId(runId)} · ${error.message}`, "neutral");
    }
  }

  function setActivePanel(panel) {
    state.activePanel = panel;
    document.querySelectorAll("[data-property-panel]").forEach((section) => {
      section.hidden = section.dataset.propertyPanel !== panel;
    });
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.classList.toggle("is-active", item.dataset.panel === panel);
    });
    setText(elements.propertiesContext, panel.replaceAll("-", " ").toUpperCase());
    if (panel === "history") refreshHistory();
  }

  async function refreshAll() {
    setStatus("Checking API...", "", "running");
    try {
      state.health = await api.health();
      renderHealth();
    } catch (error) {
      state.health = null;
      setServerState(false, "API unavailable");
      setText(elements.serverVersion, "—");
      state.models = [];
      renderModels();
      return;
    }
    try {
      await refreshModels();
      if (state.models.length) setStatus(`Ready · ${state.models.length} model${state.models.length === 1 ? "" : "s"}`, "", "ok");
      else setStatus("Ready · no server models", "", "neutral");
    } catch (error) {
      state.models = [];
      renderModels();
      setServerState(false, error.message);
    }
    await refreshHistory();
  }

  function bindEvents() {
    elements.refresh.addEventListener("click", refreshAll);
    elements.modelSelect.addEventListener("change", () => selectModel(selectedModelId()));
    elements.predictionForm.addEventListener("submit", runPrediction);
    elements.toolbarRun.addEventListener("click", () => runPrediction());
    elements.aimForm.addEventListener("submit", runAim);
    elements.spreadMode.addEventListener("change", updateAimFields);
    elements.batchFile.addEventListener("change", () => {
      state.batchFile = elements.batchFile.files?.[0] || null;
      renderBatchFile(state.batchFile);
      showFormMessage(elements.batchMessage);
      updateControlState();
    });
    elements.batchSubmit.addEventListener("click", runBatch);
    elements.batchCancel.addEventListener("click", cancelBatch);
    elements.historyRefresh.addEventListener("click", refreshHistory);
    elements.historyPrev.addEventListener("click", () => {
      state.historyOffset = Math.max(0, state.historyOffset - state.historyLimit);
      refreshHistory();
    });
    elements.historyNext.addEventListener("click", () => {
      state.historyOffset += state.historyLimit;
      refreshHistory();
    });
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.addEventListener("click", () => setActivePanel(item.dataset.panel));
    });
    elements.fit.addEventListener("click", () => {
      state.imageMode = "fit";
      elements.resultImage.className = "result-image fit";
      elements.fit.classList.add("is-selected");
      elements.actual.classList.remove("is-selected");
    });
    elements.actual.addEventListener("click", () => {
      state.imageMode = "actual";
      elements.resultImage.className = "result-image actual";
      elements.actual.classList.add("is-selected");
      elements.fit.classList.remove("is-selected");
    });
    updateAimFields();
    updateControlState();
  }

  bindEvents();
  app.dataset.ready = "true";
  setText(elements.navApiMode, api.baseUrl ? "CONFIGURED API" : "SAME-ORIGIN");
  refreshAll();
})();
