(() => {
  "use strict";

  const state = {
    language: (() => {
      try {
        const saved = window.localStorage.getItem("damagelab-language");
        if (saved === "zh" || saved === "en") return saved;
      } catch (_error) { /* localStorage may be unavailable in a restricted browser */ }
      return String(navigator.language || "en").toLowerCase().startsWith("zh") ? "zh" : "en";
    })(),
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
    batchResult: null,
    batchPollTimer: null,
    activePanel: "prediction",
    busy: false,
    imageMode: "fit",
    status: null,
  };

  const TRANSLATIONS = {
    en: {
      "brand.title": "DamageLab — Damage-Field Prediction & Analysis", "language.label": "Language",
      "aria.menu": "Workbench menu", "aria.server_context": "Server context", "aria.toolbar": "Workbench toolbar",
      "aria.navigation": "Workbench navigation", "aria.viewport_toolbar": "Viewport toolbar", "prediction.controls": "Prediction inputs", "prediction.steps": "Prediction steps",
      "brand.subtitle": "Damage-Field Prediction & Analysis",
      "menu.file": "File", "menu.view": "View", "menu.analysis": "Analysis",
      "menu.results": "Results", "menu.help": "Help",
      "context.server": "SERVER", "context.version": "VERSION",
      "status.checking": "Checking...", "status.online": "Online",
      "status.api_unavailable": "API unavailable", "status.initializing": "Initializing Workbench...",
      "status.checking_api": "Checking API...", "status.ready_models": "Ready · {{count}} model{{suffix}}",
      "status.ready_no_models": "Ready · no server models", "status.model_selected": "Model selected · {{id}}",
      "status.running_prediction": "Running prediction...", "status.prediction_complete": "Prediction complete · {{ms}} ms",
      "status.prediction_png_ready": "{{id}} · PNG ready", "status.prediction_request_failed": "Prediction request failed",
      "status.result_ready": "RESULT READY",
      "status.running_aim": "Running AIM optimization...", "status.aim_complete": "AIM complete",
      "status.aim_summary_ready": "{{mode}} · summary ready", "status.aim_request_failed": "AIM request failed",
      "status.submitting_batch": "Submitting batch...", "status.batch_queued": "Batch queued",
      "status.cancelling_batch": "Cancelling batch...", "status.batch_cancellation_cooperative": "Cancellation is cooperative",
      "status.batch_running": "Batch running...", "status.batch_complete": "Batch complete",
      "status.batch_failed": "Batch {{state}}", "status.batch_submission_failed": "Batch submission failed",
      "status.batch_status_failed": "Batch status request failed", "status.batch_cancellation_failed": "Batch cancellation failed",
      "status.loading_result": "Loading result...", "status.no_browser_result": "No browser result attached",
      "status.unsupported_history": "{{id}} · unsupported history type", "status.history_request_failed": "History request failed",
      "status.result_image_unavailable": "Result image unavailable", "status.result_image_detail": "The structured result is still available",
      "status.result_image_request_failed": "The result image request failed", "status.rows": "{{completed}} / {{total}} rows", "status.row_count": "{{count}} rows",
      "toolbar.refresh": "Refresh", "toolbar.active_model": "ACTIVE MODEL", "toolbar.prediction": "PREDICTION",
      "toolbar.idle": "Idle", "toolbar.ready": "Ready", "toolbar.ready_hint": "Set conditions in the workspace to begin.",
      "action.run_prediction": "Run Prediction", "action.run_batch": "Run Batch", "action.run_aim": "Run AIM",
      "action.cancel": "Cancel", "action.reload": "Reload", "action.previous": "Previous", "action.next": "Next",
      "action.fit": "Fit", "action.download_png": "Download PNG", "action.download_csv": "Download CSV",
      "action.download_batch_csv": "Download batch CSV",
      "nav.project": "PROJECT", "nav.analysis": "ANALYSIS", "nav.results": "RESULTS",
      "nav.model": "Model", "nav.validation": "Validation", "nav.prediction": "Prediction",
      "nav.batch": "Batch Prediction", "nav.aim": "Aim Optimization", "nav.history": "History", "nav.export": "Export",
      "nav.api_mode": "API MODE", "api.configured": "CONFIGURED API", "api.same_origin": "SAME-ORIGIN",
      "properties.title": "Properties", "properties.title_upper": "PROPERTIES",
      "model.selection": "Model Selection", "model.server_model": "Server model", "model.loading": "Loading models...",
      "model.empty": "No server models available.", "model.toolbar_hint": "Choose the active model from the workbench toolbar.", "model.metadata": "Metadata", "model.none": "No model selected",
      "validation.summary": "Validation Summary", "validation.empty": "Select a model with validation metadata.",
      "prediction.input_kicker": "INPUT CONDITION", "prediction.input_condition": "Input Condition", "prediction.condition_note": "Values are validated by the active server model.",
      "prediction.model_hint": "Select a model from the toolbar to enable prediction.", "prediction.model_selected_hint": "Using {{id}}. Enter conditions to run.",
      "condition.height": "Height, h", "condition.velocity": "Velocity, v", "condition.angle": "Angle, θ",
      "condition.height_placeholder": "e.g. 100", "condition.velocity_placeholder": "e.g. 4", "condition.angle_placeholder": "e.g. 5",
      "batch.title": "Batch Prediction", "batch.note": "Upload a CSV to the server queue. The file path never leaves this browser.",
      "batch.csv_file": "CSV file", "aim.title": "Aim Optimization", "aim.note": "Uses the current prediction result.",
      "aim.spread_model": "Spread model", "aim.reliability": "Reliability",
      "history.title": "Execution History", "history.note": "Traceability records from the configured server database.",
      "history.loading": "Loading history...", "history.id": "ID", "history.type": "Type", "history.status": "Status", "history.created": "Created",
      "export.title": "Result Export", "export.note": "Downloads are generated by the server from the stored result.",
      "export.empty": "Run a prediction to enable exports.",
      "viewport.visualization": "Visualization", "viewport.kicker": "VIEWPORT / RESULT",
      "viewport.title": "Damage Field — Single Prediction", "viewport.subtitle": "Set the input condition, then run a prediction to render the damage field.",
      "viewport.server_png": "Server PNG", "viewport.loading": "Loading result...", "viewport.empty_code": "NO PREDICTION YET", "viewport.empty_title": "No prediction yet",
      "viewport.empty_text": "Enter conditions and run a prediction to render the damage field.", "viewport.step_condition": "Enter conditions", "viewport.step_run": "Run prediction",
      "viewport.image_error_title": "IMAGE UNAVAILABLE", "viewport.image_error": "Unable to load the result image", "viewport.image_error_detail": "The structured result is still available in the Results inspector.", "viewport.image_alt": "Server-rendered damage field",
      "result.no_result": "NO RESULT", "result.no_run": "NO RUN",
      "results.title": "Results", "results.title_upper": "RESULTS", "results.empty_title": "No prediction data", "results.empty": "Run a prediction to populate the inspector.",
      "results.field_summary": "Field Summary", "results.confidence_ood": "Confidence / OOD", "results.run_information": "Run Information",
      "results.advice": "Advice", "results.aim_summary": "AIM Summary", "results.aim_note": "Summary returned by the server. No separate AIM image endpoint is exposed.",
      "results.batch_summary": "Batch Summary",
      "label.model_id": "Model ID", "label.type": "Type", "label.damage_level": "Damage level", "label.training_samples": "Training samples",
      "label.active": "Active", "label.mean_relative_error": "Mean relative error", "label.p95_hybrid_error": "P95 hybrid error",
      "label.raw_mean_relative_error": "Mean relative error (Raw)", "label.raw_p95_hybrid_error": "P95 hybrid error (Raw)",
      "label.r2": "R²", "label.raw_r2": "R² (Raw)", "label.primary_field": "Primary field",
      "label.train_time": "Train time", "label.validation_mode": "Validation mode", "label.model_type": "Model type",
      "label.app_version": "App version", "label.created_at": "Created", "label.schema_version": "Schema version",
      "label.model_format_version": "Model format", "label.training_data_hash": "Training data hash", "label.code_commit": "Code commit",
      "label.peak_intensity": "Peak intensity", "label.damaged_area": "Damaged area", "label.metrics": "Metrics",
      "label.confidence": "Confidence", "label.ood_level": "OOD level", "label.distance": "Distance", "label.extrapolation": "Extrapolation",
      "label.in_hull": "In hull", "label.local_support": "Local support", "label.ood": "OOD", "label.run_id": "Run ID", "label.model": "Model",
      "label.elapsed": "Elapsed", "label.truth_available": "Truth available", "label.focus_damage": "Focus damage", "label.scope": "Scope", "label.ood_note": "OOD note",
      "label.best_x": "Best x", "label.best_y": "Best y", "label.vmax": "Vmax", "label.relative_gain": "Relative gain", "label.shift_distance": "Shift distance",
      "label.sigma": "σx / σy", "label.rho": "ρ", "label.field_shape": "Field shape", "label.name": "Name", "label.size": "Size", "label.file_type": "Type",
      "label.state": "State", "label.completed": "Completed", "label.successful_rows": "Successful rows", "label.failed_rows": "Failed rows",
      "label.duration": "Duration", "label.row_errors": "Row errors",
      "common.yes": "Yes", "common.no": "No", "common.available": "Available", "common.not_available": "Not available for this run",
      "common.unknown": "Unknown", "common.records": "records", "common.record": "record", "common.unavailable": "Unavailable",
      "history.kind_prediction": "Prediction", "history.kind_aim": "AIM", "history.kind_batch": "Batch prediction",
      "history.status_pending": "Queued", "history.status_running": "Running", "history.status_succeeded": "Succeeded",
      "history.status_failed": "Failed", "history.status_cancelled": "Cancelled",
      "model.validation": "Validation: {{label}}", "model.none_status": "No model selected", "validation.select_model": "Select a model with validation metadata.",
      "message.select_model": "Select an available server model first.", "message.enter_condition": "Enter finite values for h, v, and θ.",
      "message.run_prediction_first": "Run a prediction before AIM optimization.", "message.enter_reliability": "Enter a finite reliability value.",
      "message.enter_cep": "Enter CEP for the selected spread model.", "message.enter_rep_dep": "Enter both REP and DEP for the selected spread model.",
      "message.select_model_file": "Select a server model and CSV file first.",
      "batch.progress": "Batch · {{completed}} / {{total}} · {{percent}}%", "batch.rows": "{{completed}} / {{total}} rows",
      "batch.queued": "Queued", "batch.failed": "failed", "batch.succeeded": "succeeded", "batch.cancelled": "cancelled",
      "ood.not_available": "Not available", "history.none": "No traceability records returned.", "history.count_one": "1 record", "history.count_many": "{{count}} records",
      "result.no_browser": "No browser result attached", "result.unsupported": "unsupported history type", "export.run_prediction": "Run a prediction to enable exports.",
      "ood.high_label": "High confidence (interpolation region)", "ood.medium_label": "Medium confidence (sparse-support region)", "ood.low_label": "Low confidence (extrapolation region)",
      "ood.geometry_edge": "At the edge of the training-data coverage", "ood.geometry_hull": "Outside the global convex hull of training conditions", "ood.geometry_local_hole": "A local data gap inside the global convex hull",
      "advice.current_condition": "Current condition",
      "batch.stage_queued": "Queued", "batch.stage_complete": "Complete", "batch.stage_failed": "Failed", "batch.stage_cancelled": "Cancelled before start",
    },
    zh: {
      "brand.title": "DamageLab — 毁伤场快速预测与分析", "language.label": "语言",
      "aria.menu": "工作台菜单", "aria.server_context": "服务端信息", "aria.toolbar": "工作台工具栏",
      "aria.navigation": "工作台导航", "aria.viewport_toolbar": "视口工具栏", "prediction.controls": "预测输入", "prediction.steps": "预测步骤",
      "brand.subtitle": "毁伤场快速预测与分析",
      "menu.file": "文件", "menu.view": "视图", "menu.analysis": "分析", "menu.results": "结果", "menu.help": "帮助",
      "context.server": "服务", "context.version": "版本", "status.checking": "检查中…", "status.online": "在线",
      "status.api_unavailable": "API 不可用", "status.initializing": "正在初始化工作台…", "status.checking_api": "正在检查 API…",
      "status.ready_models": "就绪 · {{count}} 个模型", "status.ready_no_models": "就绪 · 没有可用模型", "status.model_selected": "已选择模型 · {{id}}",
      "status.running_prediction": "正在运行预测…", "status.prediction_complete": "预测完成 · {{ms}} ms", "status.prediction_png_ready": "{{id}} · PNG 已就绪",
      "status.prediction_request_failed": "预测请求失败", "status.result_ready": "结果已就绪", "status.running_aim": "正在运行瞄准优化…", "status.aim_complete": "瞄准优化完成",
      "status.aim_summary_ready": "{{mode}} · 摘要已生成", "status.aim_request_failed": "瞄准优化请求失败", "status.submitting_batch": "正在提交批量任务…",
      "status.batch_queued": "批量任务已排队", "status.cancelling_batch": "正在取消批量任务…", "status.batch_cancellation_cooperative": "取消采用协作式机制",
      "status.batch_running": "批量任务运行中…", "status.batch_complete": "批量任务完成", "status.batch_failed": "批量任务{{state}}",
      "status.batch_submission_failed": "批量任务提交失败", "status.batch_status_failed": "批量状态查询失败", "status.batch_cancellation_failed": "批量取消失败",
      "status.loading_result": "正在加载结果…", "status.no_browser_result": "没有可用的浏览器结果", "status.unsupported_history": "{{id}} · 不支持的历史记录类型",
      "status.history_request_failed": "历史记录查询失败", "status.result_image_unavailable": "结果图像不可用", "status.result_image_detail": "结构化结果仍然可用",
      "status.result_image_request_failed": "结果图像请求失败", "status.rows": "{{completed}} / {{total}} 行", "status.row_count": "{{count}} 行",
      "toolbar.refresh": "刷新", "toolbar.active_model": "当前模型", "toolbar.prediction": "预测状态", "toolbar.idle": "空闲", "toolbar.ready": "就绪", "toolbar.ready_hint": "在工作区填写工况后开始。", "action.run_prediction": "运行预测", "action.run_batch": "运行批量预测",
      "action.run_aim": "运行瞄准优化", "action.cancel": "取消", "action.reload": "重新加载", "action.previous": "上一页", "action.next": "下一页",
      "action.fit": "适配", "action.download_png": "下载 PNG", "action.download_csv": "下载 CSV", "action.download_batch_csv": "下载批量 CSV",
      "nav.project": "项目", "nav.analysis": "分析", "nav.results": "结果", "nav.model": "模型", "nav.validation": "验证", "nav.prediction": "预测",
      "nav.batch": "批量预测", "nav.aim": "瞄准优化", "nav.history": "历史记录", "nav.export": "导出", "nav.api_mode": "API 模式",
      "api.configured": "已配置 API", "api.same_origin": "同源", "properties.title": "属性", "properties.title_upper": "属性",
      "model.selection": "模型选择", "model.server_model": "服务端模型", "model.loading": "正在加载模型…", "model.empty": "没有可用的服务端模型。", "model.toolbar_hint": "请从工作台工具栏选择当前模型。",
      "model.metadata": "元数据", "model.none": "尚未选择模型", "validation.summary": "验证摘要", "validation.empty": "请选择带有验证元数据的模型。",
      "prediction.input_kicker": "输入工况", "prediction.input_condition": "输入工况", "prediction.condition_note": "数值由当前服务端模型校验。", "prediction.model_hint": "请先从工具栏选择模型以启用预测。", "prediction.model_selected_hint": "当前使用 {{id}}，填写工况后运行预测。", "condition.height": "高度 h", "condition.velocity": "速度 v", "condition.angle": "角度 θ", "condition.height_placeholder": "例如 100", "condition.velocity_placeholder": "例如 4", "condition.angle_placeholder": "例如 5",
      "batch.title": "批量预测", "batch.note": "上传 CSV 到服务端队列。文件路径不会离开当前浏览器。", "batch.csv_file": "CSV 文件",
      "aim.title": "瞄准优化", "aim.note": "使用当前预测结果。", "aim.spread_model": "散布模型", "aim.reliability": "可信度",
      "history.title": "执行历史", "history.note": "来自已配置服务端数据库的追溯记录。", "history.loading": "正在加载历史记录…", "history.id": "编号", "history.type": "类型", "history.status": "状态", "history.created": "创建时间",
      "export.title": "结果导出", "export.note": "下载文件由服务端根据已保存结果生成。", "export.empty": "运行预测后可导出结果。",
      "viewport.visualization": "可视化", "viewport.server_png": "服务端 PNG", "viewport.kicker": "视口 / 结果", "viewport.title": "毁伤场 — 单工况预测", "viewport.subtitle": "填写输入工况后运行预测，生成毁伤场。", "viewport.loading": "正在加载结果…", "viewport.empty_code": "尚未运行预测", "viewport.empty_title": "暂无预测结果", "viewport.empty_text": "填写工况并运行预测后，这里将显示毁伤场。", "viewport.step_condition": "填写工况", "viewport.step_run": "运行预测", "viewport.image_error_title": "图像不可用", "viewport.image_error": "结果图像加载失败", "viewport.image_error_detail": "结构化结果仍可在右侧结果检查器中查看。", "viewport.image_alt": "服务端生成的毁伤场",
      "result.no_result": "暂无结果", "result.no_run": "暂无运行", "results.title": "结果", "results.title_upper": "结果", "results.empty_title": "暂无预测数据", "results.empty": "运行预测后将在此显示结果。",
      "results.field_summary": "场摘要", "results.confidence_ood": "可信度 / OOD", "results.run_information": "运行信息", "results.advice": "建议", "results.aim_summary": "瞄准优化摘要",
      "results.aim_note": "摘要由服务端返回，未提供独立的瞄准优化图像接口。", "results.batch_summary": "批量摘要",
      "label.model_id": "模型 ID", "label.type": "类型", "label.damage_level": "毁伤等级", "label.training_samples": "训练样本数", "label.active": "当前使用",
      "label.mean_relative_error": "平均相对误差", "label.p95_hybrid_error": "P95 混合误差", "label.train_time": "训练耗时", "label.validation_mode": "验证方式", "label.model_type": "模型类型",
      "label.raw_mean_relative_error": "平均相对误差（Raw）", "label.raw_p95_hybrid_error": "P95 混合误差（Raw）",
      "label.r2": "R²", "label.raw_r2": "R²（Raw）", "label.primary_field": "主口径",
      "label.app_version": "应用版本", "label.created_at": "创建时间", "label.schema_version": "Schema 版本", "label.model_format_version": "模型格式", "label.training_data_hash": "训练数据指纹", "label.code_commit": "代码提交",
      "label.peak_intensity": "峰值强度", "label.damaged_area": "毁伤面积", "label.metrics": "指标", "label.confidence": "可信度", "label.ood_level": "OOD 等级", "label.distance": "距离", "label.extrapolation": "外推",
      "label.in_hull": "位于凸包内", "label.local_support": "局部支撑", "label.ood": "OOD", "label.run_id": "运行 ID", "label.model": "模型", "label.elapsed": "耗时", "label.truth_available": "真值可用", "label.focus_damage": "重点毁伤", "label.scope": "范围", "label.ood_note": "OOD 说明",
      "label.best_x": "最优 x", "label.best_y": "最优 y", "label.vmax": "Vmax", "label.relative_gain": "相对增益", "label.shift_distance": "偏移距离", "label.sigma": "σx / σy", "label.rho": "ρ", "label.field_shape": "场形状", "label.name": "名称", "label.size": "大小", "label.file_type": "类型",
      "label.state": "状态", "label.completed": "已完成", "label.successful_rows": "成功行数", "label.failed_rows": "失败行数", "label.duration": "耗时", "label.row_errors": "行错误数",
      "common.yes": "是", "common.no": "否", "common.available": "可用", "common.not_available": "本次运行无此数据", "common.unknown": "未知", "common.records": "条记录", "common.record": "条记录", "common.unavailable": "不可用",
      "history.kind_prediction": "预测", "history.kind_aim": "瞄准优化", "history.kind_batch": "批量预测",
      "history.status_pending": "排队中", "history.status_running": "运行中", "history.status_succeeded": "成功",
      "history.status_failed": "失败", "history.status_cancelled": "已取消",
      "model.validation": "验证：{{label}}", "model.none_status": "尚未选择模型", "validation.select_model": "请选择带有验证元数据的模型。", "message.select_model": "请先选择可用的服务端模型。",
      "message.enter_condition": "请输入 h、v、θ 的有限数值。", "message.run_prediction_first": "请先运行预测，再执行瞄准优化。", "message.enter_reliability": "请输入有限的可信度数值。",
      "message.enter_cep": "当前散布模型需要输入 CEP。", "message.enter_rep_dep": "当前散布模型需要同时输入 REP 和 DEP。", "message.select_model_file": "请先选择服务端模型和 CSV 文件。",
      "batch.progress": "批量 · {{completed}} / {{total}} · {{percent}}%", "batch.rows": "{{completed}} / {{total}} 行", "batch.queued": "排队中", "batch.failed": "失败", "batch.succeeded": "成功", "batch.cancelled": "已取消",
      "ood.not_available": "不可用", "history.none": "没有返回追溯记录。", "history.count_one": "1 条记录", "history.count_many": "{{count}} 条记录", "result.no_browser": "没有可用的浏览器结果", "result.unsupported": "不支持的历史记录类型", "export.run_prediction": "运行预测后可导出结果。",
      "ood.high_label": "高（插值区域）", "ood.medium_label": "中（稀疏支撑区域）", "ood.low_label": "低（外推区域）",
      "ood.geometry_edge": "位于训练数据覆盖边缘", "ood.geometry_hull": "位于训练工况全局凸包之外", "ood.geometry_local_hole": "位于全局凸包内的局部数据空洞", "advice.current_condition": "当前工况",
      "batch.stage_queued": "排队中", "batch.stage_complete": "已完成", "batch.stage_failed": "失败", "batch.stage_cancelled": "开始前已取消",
    },
  };

  function t(key, values = {}) {
    const text = TRANSLATIONS[state.language]?.[key] || TRANSLATIONS.en[key] || key;
    return text.replace(/\{\{(\w+)\}\}/g, (_match, name) => String(values[name] ?? ""));
  }

  function rememberLanguage(language) {
    try { window.localStorage.setItem("damagelab-language", language); } catch (_error) { /* best effort */ }
  }

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
        throw new ApiError(t("status.api_unavailable"));
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
    language: $("language-select"),
    refresh: $("refresh-button"),
    toolbarModel: $("toolbar-model"),
    toolbarPredictionState: $("toolbar-prediction-state"),
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
    viewportError: $("viewport-error"),
    predictionModelHint: $("prediction-model-hint"),
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

  function applyStaticLanguage() {
    document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
    document.title = t("brand.title");
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      element.textContent = t(element.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
      element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
    });
    document.querySelectorAll("[data-i18n-alt]").forEach((element) => {
      element.setAttribute("alt", t(element.dataset.i18nAlt));
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
      element.setAttribute("placeholder", t(element.dataset.i18nPlaceholder));
    });
    elements.language.value = state.language;
  }

  function setLanguage(language) {
    if ((language !== "zh" && language !== "en") || language === state.language) return;
    state.language = language;
    rememberLanguage(language);
    applyLanguage();
  }

  function setText(element, value) {
    element.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
  }

  function formatNumber(value, digits = 3) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    const locale = state.language === "zh" ? "zh-CN" : "en-US";
    return new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(number);
  }

  function formatPercent(value, digits = 2) {
    const number = Number(value);
    return Number.isFinite(number) ? `${formatNumber(number * 100, digits)}%` : "—";
  }

  function formatDate(value) {
    const date = new Date(value);
    const locale = state.language === "zh" ? "zh-CN" : "en-US";
    return Number.isNaN(date.getTime()) ? String(value || "—") : date.toLocaleString(locale);
  }

  function shortId(value) {
    const text = String(value || "—");
    return text.length > 12 ? `${text.slice(0, 8)}…${text.slice(-4)}` : text;
  }

  function humanLabel(key) {
    const known = {
      MeanRelativeError: "label.mean_relative_error",
      P95HybridError: "label.p95_hybrid_error",
      mean_relative_error: "label.mean_relative_error",
      p95_hybrid_error: "label.p95_hybrid_error",
      raw_mean_relative_error: "label.raw_mean_relative_error",
      raw_p95_hybrid_error: "label.raw_p95_hybrid_error",
      r2: "label.r2",
      raw_r2: "label.raw_r2",
      primary_field: "label.primary_field",
      train_time_seconds: "label.train_time",
      validation_mode: "label.validation_mode",
      model_type: "label.model_type",
      damage_level: "label.damage_level",
      training_samples: "label.training_samples",
      app_version: "label.app_version",
      created_at: "label.created_at",
      schema_version: "label.schema_version",
      model_format_version: "label.model_format_version",
      training_data_hash: "label.training_data_hash",
      code_commit: "label.code_commit",
    };
    return known[key] ? t(known[key]) : String(key).replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function formatValue(value, key = "") {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "boolean") return value ? t("common.yes") : t("common.no");
    if (typeof value === "number") {
      if (key.toLowerCase().includes("time") && key.toLowerCase().includes("second")) return `${formatNumber(value)} s`;
      if (key.toLowerCase().includes("error") || key.toLowerCase().includes("relative")) return formatPercent(value);
      return formatNumber(value);
    }
    if (Array.isArray(value)) return value.join(" × ");
    if (typeof value === "object") return t("common.available");
    return String(value);
  }

  function localizeServerText(value) {
    const keys = {
      "高（插值区域）": "ood.high_label",
      "High Confidence": "ood.high_label",
      "High confidence": "ood.high_label",
      "中（稀疏支撑区域）": "ood.medium_label",
      "Medium Confidence": "ood.medium_label",
      "Medium confidence": "ood.medium_label",
      "低（外推区域）": "ood.low_label",
      "Low Confidence": "ood.low_label",
      "Low confidence": "ood.low_label",
      "训练数据覆盖边缘": "ood.geometry_edge",
      "训练工况全局凸包之外": "ood.geometry_hull",
      "全局凸包内的局部数据空洞": "ood.geometry_local_hole",
      "当前工况": "advice.current_condition",
    };
    const key = keys[String(value)];
    return key ? t(key) : (value || "—");
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

  function setStatus(
    message,
    detail = "",
    kind = "neutral",
    statusKey = null,
    statusValues = {},
    detailKey = null,
    detailValues = {},
  ) {
    state.status = statusKey ? { statusKey, statusValues, detail, detailKey, detailValues, kind } : null;
    setText(elements.statusMessage, message);
    elements.statusDetail.textContent = detail || "";
    elements.statusIndicator.className = `status-dot status-dot-${statusClass(kind)}`;
  }

  function statusClass(kind) {
    return kind === "ok" ? "ok" : kind === "running" ? "running" : kind === "error" ? "error" : "neutral";
  }

  function setLocalizedStatus(key, values = {}, detail = "", kind = "neutral", detailKey = null, detailValues = {}) {
    setStatus(t(key, values), detailKey ? t(detailKey, detailValues) : detail, kind, key, values, detailKey, detailValues);
  }

  function showFormMessage(element, message = "") {
    element.textContent = message;
    element.hidden = !message;
  }

  function setServerState(online, message = "") {
    elements.serverStatus.className = `status-text ${online ? "status-good" : "status-error"}`;
    elements.serverStatus.textContent = online ? t("status.online") : t("status.api_unavailable");
    if (!online) setLocalizedStatus("status.api_unavailable", {}, message, "error");
  }

  function applyLanguage() {
    applyStaticLanguage();
    setText(elements.navApiMode, api.baseUrl ? t("api.configured") : t("api.same_origin"));
    renderModels();
    renderModelDetails(state.selectedModel);
    renderValidation(state.selectedModel);
    renderViewport(state.prediction);
    renderResults(state.prediction);
    renderExport(state.prediction);
    renderBatchFile(state.batchFile);
    renderBatchJob(state.batchJob);
    if (!state.prediction) renderBatchResult(state.batchResult);
    renderHistory({
      items: state.history,
      total: state.historyTotal,
      offset: state.historyOffset,
      limit: state.historyLimit,
    });
    elements.propertiesContext.textContent = t(`nav.${state.activePanel}`).toUpperCase();
    if (state.status?.statusKey) {
      const status = state.status;
      setText(elements.statusMessage, t(status.statusKey, status.statusValues));
      elements.statusDetail.textContent = status.detailKey
        ? t(status.detailKey, status.detailValues)
        : status.detail || "";
      elements.statusIndicator.className = `status-dot status-dot-${statusClass(status.kind)}`;
    }
    updateControlState();
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
      { label: t("label.model_id"), value: model?.model_id || "—" },
      { label: t("label.type"), value: model?.model_type || "—" },
      { label: t("label.damage_level"), value: model?.damage_level || "—" },
      { label: t("label.training_samples"), value: formatValue(model?.training_samples, "training_samples") },
      { label: t("label.active"), value: active ? t("common.yes") : t("common.no"), className: active ? "status-good" : "" },
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
      setText(elements.toolbarModel, t("model.none"));
      elements.toolbarModel.hidden = false;
      elements.predictionModelHint.textContent = t("prediction.model_hint");
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
    elements.toolbarModel.hidden = true;
    elements.predictionModelHint.textContent = state.selectedModel
      ? t("prediction.model_selected_hint", { id: state.selectedModel.model_id })
      : t("prediction.model_hint");
  }

  async function selectModel(modelId, { quiet = false } = {}) {
    if (!modelId) return;
    try {
      const model = await api.getModel(modelId);
      state.selectedModel = model;
      elements.modelSelect.value = model.model_id;
      setText(elements.toolbarModel, model.model_id);
      elements.toolbarModel.hidden = true;
      elements.predictionModelHint.textContent = t("prediction.model_selected_hint", { id: model.model_id });
      renderModelDetails(model);
      renderValidation(model);
      updateControlState();
      if (!quiet) setLocalizedStatus("status.model_selected", { id: model.model_id }, "", "ok");
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
      elements.viewportSubtitle.textContent = t("viewport.subtitle");
      elements.toolbarPredictionState.className = "toolbar-state-value";
      elements.toolbarPredictionState.textContent = t("toolbar.idle");
      elements.viewportBadge.className = "result-badge";
      elements.viewportBadge.textContent = t("result.no_result");
      elements.viewportDownload.href = "#";
      elements.viewportDownload.classList.add("is-disabled");
      elements.viewportEmpty.hidden = false;
      elements.viewportError.hidden = true;
      elements.viewportLoading.hidden = true;
      elements.resultImage.hidden = true;
      elements.resultImage.removeAttribute("src");
      return;
    }
    const condition = prediction.condition;
    elements.viewportSubtitle.textContent = `h = ${formatNumber(condition.h)} mm · v = ${formatNumber(condition.v)} m/s · θ = ${formatNumber(condition.deg)}°`;
    elements.toolbarPredictionState.className = "toolbar-state-value is-ready";
    elements.toolbarPredictionState.textContent = t("toolbar.ready");
    elements.viewportBadge.className = "result-badge is-ready";
    elements.viewportBadge.textContent = t("status.result_ready");
    elements.viewportDownload.href = api.link(prediction.links.png);
    elements.viewportDownload.classList.remove("is-disabled");
    elements.viewportEmpty.hidden = true;
    elements.viewportError.hidden = true;
  }

  function renderResults(prediction) {
    const hasPrediction = Boolean(prediction);
    if (hasPrediction) renderBatchResult(null);
    elements.resultsEmpty.hidden = hasPrediction;
    elements.resultsContent.hidden = !hasPrediction;
    setText(elements.resultsRun, prediction ? shortId(prediction.run_id) : t("result.no_run"));
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
      { label: t("label.peak_intensity"), value: formatNumber(prediction.peak_intensity) },
      { label: t("label.damaged_area"), value: formatPercent(prediction.damage_area_ratio) },
    ]);

    const metrics = prediction.metrics && typeof prediction.metrics === "object" ? prediction.metrics : null;
    const validationEntries = metrics
      ? Object.entries(metrics).map(([key, value]) => ({ label: humanLabel(key), value: formatValue(value, key) }))
      : [{ label: t("label.metrics"), value: t("common.not_available") }];
    renderPropertyList(elements.resultValidation, validationEntries);

    const ood = prediction.ood;
    renderPropertyList(elements.resultOod, ood ? [
      { label: t("label.confidence"), value: localizeServerText(prediction.confidence) },
      { label: t("label.ood_level"), value: localizeServerText(ood.level_label || ood.level), className: ood.is_extrapolation ? "status-warn" : "status-good" },
      { label: t("label.distance"), value: formatNumber(ood.distance) },
      { label: t("label.extrapolation"), value: ood.is_extrapolation ? t("common.yes") : t("common.no"), className: ood.is_extrapolation ? "status-warn" : "status-good" },
      { label: t("label.in_hull"), value: ood.in_hull === null ? "—" : (ood.in_hull ? t("common.yes") : t("common.no")) },
      { label: t("label.local_support"), value: ood.local_support === null ? "—" : (ood.local_support ? t("common.yes") : t("common.no")) },
    ] : [
      { label: t("label.confidence"), value: localizeServerText(prediction.confidence) },
      { label: t("label.ood"), value: t("ood.not_available") },
    ]);

    renderPropertyList(elements.runSummary, [
      { label: t("label.run_id"), value: prediction.run_id },
      { label: t("label.model"), value: prediction.model?.model_id || "—" },
      { label: t("label.elapsed"), value: `${formatNumber(prediction.elapsed_ms, 0)} ms` },
    ]);
    const advice = prediction.advice || {};
    const adviceEntries = [
      { label: t("label.truth_available"), value: advice.has_truth ? t("common.yes") : t("common.no") },
      { label: t("label.focus_damage"), value: advice.has_focus_damage ? t("common.yes") : t("common.no") },
      { label: t("label.scope"), value: localizeServerText(advice.scope) },
    ];
    if (advice.ood_geometry_reason) adviceEntries.push({ label: t("label.ood_note"), value: localizeServerText(advice.ood_geometry_reason) });
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
      { label: t("label.best_x"), value: formatNumber(aim.best_x) },
      { label: t("label.best_y"), value: formatNumber(aim.best_y) },
      { label: t("label.vmax"), value: formatNumber(aim.vmax) },
      { label: t("label.relative_gain"), value: formatPercent(aim.gain_relative) },
      { label: t("label.shift_distance"), value: formatNumber(aim.shift_distance) },
      { label: t("label.sigma"), value: `${formatNumber(aim.sigma_x)} / ${formatNumber(aim.sigma_y)}` },
      { label: t("label.rho"), value: formatNumber(aim.rho) },
      { label: t("label.field_shape"), value: Array.isArray(aim.value_field_shape) ? aim.value_field_shape.join(" × ") : "—" },
    ]);
  }

  function isTerminalJob(job) {
    return Boolean(job && ["SUCCEEDED", "FAILED", "CANCELLED"].includes(job.state));
  }

  function localizeJobState(stateValue) {
    const keys = {
      PENDING: "history.status_pending",
      QUEUED: "history.status_pending",
      RUNNING: "history.status_running",
      SUCCEEDED: "history.status_succeeded",
      FAILED: "history.status_failed",
      CANCELLED: "history.status_cancelled",
    };
    return keys[stateValue] ? t(keys[stateValue]) : (stateValue || "—");
  }

  function localizeJobStage(stage) {
    if (!stage) return "—";
    const normalized = String(stage).toUpperCase();
    const stageKeys = {
      QUEUED: "batch.stage_queued",
      COMPLETE: "batch.stage_complete",
      FAILED: "batch.stage_failed",
      "CANCELLED BEFORE START": "batch.stage_cancelled",
    };
    if (stageKeys[normalized]) return t(stageKeys[normalized]);
    return normalized in {
      PENDING: true, QUEUED: true, RUNNING: true, SUCCEEDED: true, FAILED: true, CANCELLED: true,
    } ? localizeJobState(normalized) : stage;
  }

  function renderBatchFile(file) {
    if (!file) {
      renderPropertyList(elements.batchFileMeta, []);
      return;
    }
    renderPropertyList(elements.batchFileMeta, [
      { label: t("label.name"), value: file.name },
      { label: t("label.size"), value: `${formatNumber(file.size / 1024, 1)} KB` },
      { label: t("label.file_type"), value: file.type || "text/csv" },
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
    elements.batchProgressText.textContent = t("batch.progress", {
      completed: formatNumber(job.completed, 0), total: formatNumber(job.total, 0), percent: progress,
    });
    elements.batchProgressStage.textContent = localizeJobStage(job.stage || job.state);
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
      { label: t("label.state"), value: localizeJobState(result.state), className: result.state === "SUCCEEDED" ? "status-good" : result.state === "FAILED" ? "status-error" : "status-warn" },
      { label: t("label.completed"), value: `${formatNumber(summary.completed, 0)} / ${formatNumber(summary.total, 0)}` },
      { label: t("label.successful_rows"), value: formatNumber(summary.success_count, 0) },
      { label: t("label.failed_rows"), value: formatNumber(summary.failed_count, 0), className: summary.failed_count ? "status-warn" : "" },
      { label: t("label.duration"), value: `${formatNumber(summary.duration_ms, 0)} ms` },
      { label: t("label.row_errors"), value: formatNumber(summary.row_error_count, 0) },
    ]);
    elements.batchResultDownload.hidden = !result.links?.csv;
    if (result.links?.csv) elements.batchResultDownload.href = api.link(result.links.csv);
  }

  function loadPredictionImage(prediction) {
    elements.plotSurface.setAttribute("aria-busy", "true");
    elements.viewportLoading.hidden = false;
    elements.viewportEmpty.hidden = true;
    elements.viewportError.hidden = true;
    elements.resultImage.hidden = true;
    elements.resultImage.removeAttribute("src");
    elements.resultImage.className = `result-image ${state.imageMode}`;
    elements.resultImage.onload = () => {
      elements.plotSurface.setAttribute("aria-busy", "false");
      elements.viewportLoading.hidden = true;
      elements.resultImage.hidden = false;
      setLocalizedStatus(
        "status.prediction_complete",
        { ms: formatNumber(prediction.elapsed_ms, 0) },
        "",
        "ok",
        "status.prediction_png_ready",
        { id: prediction.model.model_id },
      );
    };
    elements.resultImage.onerror = () => {
      elements.plotSurface.setAttribute("aria-busy", "false");
      elements.viewportLoading.hidden = true;
      elements.resultImage.hidden = true;
      elements.viewportError.hidden = false;
      setLocalizedStatus("status.result_image_unavailable", {}, "", "error", "status.result_image_detail");
    };
    elements.resultImage.src = api.link(prediction.links.png);
  }

  function setBusy(value, message = "", statusKey = null) {
    state.busy = value;
    updateControlState();
    if (value && message) {
      if (statusKey) setLocalizedStatus(statusKey, {}, "", "running");
      else setStatus(message, "", "running");
    }
  }

  async function runPrediction(event) {
    event?.preventDefault();
    showFormMessage(elements.predictionMessage);
    if (!state.selectedModel) {
      showFormMessage(elements.predictionMessage, t("message.select_model"));
      return;
    }
    const h = readNumber("condition-h");
    const v = readNumber("condition-v");
    const deg = readNumber("condition-deg");
    if ([h, v, deg].some((value) => value === null)) {
      showFormMessage(elements.predictionMessage, t("message.enter_condition"));
      return;
    }
    setBusy(true, t("status.running_prediction"), "status.running_prediction");
    elements.toolbarPredictionState.className = "toolbar-state-value";
    elements.toolbarPredictionState.textContent = t("status.running_prediction");
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
      setLocalizedStatus("status.prediction_request_failed", {}, error.message, "error");
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
      showFormMessage(elements.aimMessage, t("message.run_prediction_first"));
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
      showFormMessage(elements.aimMessage, t("message.enter_reliability"));
      return;
    }
    if (spreadMode === "CEP") {
      payload.cep = readNumber("aim-cep");
      if (payload.cep === null) {
        showFormMessage(elements.aimMessage, t("message.enter_cep"));
        return;
      }
    } else {
      payload.rep = readNumber("aim-rep");
      payload.dep = readNumber("aim-dep");
      payload.rho = readNumber("aim-rho");
      payload.theta_deg = readNumber("aim-theta");
      if ([payload.rep, payload.dep].some((value) => value === null)) {
        showFormMessage(elements.aimMessage, t("message.enter_rep_dep"));
        return;
      }
      if (payload.rho === null) payload.rho = 0;
    }
    setBusy(true, t("status.running_aim"), "status.running_aim");
    try {
      state.aim = await api.aim(payload);
      renderAimResult(state.aim);
      setLocalizedStatus(
        "status.aim_complete",
        {},
        "",
        "ok",
        "status.aim_summary_ready",
        { mode: state.aim.spread_mode },
      );
      showFormMessage(elements.aimMessage);
    } catch (error) {
      showFormMessage(elements.aimMessage, error.message);
      setLocalizedStatus("status.aim_request_failed", {}, error.message, "error");
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
        state.batchResult = result;
        renderBatchResult(result);
        setLocalizedStatus(
          state.batchJob.state === "SUCCEEDED" ? "status.batch_complete" : "status.batch_failed",
          {
            state: localizeJobState(state.batchJob.state).toLowerCase(),
            completed: formatNumber(state.batchJob.completed, 0),
            total: formatNumber(state.batchJob.total, 0),
          },
          "",
          state.batchJob.state === "SUCCEEDED" ? "ok" : "error",
          "status.rows",
          {
            completed: formatNumber(state.batchJob.completed, 0),
            total: formatNumber(state.batchJob.total, 0),
          },
        );
      } else {
        setLocalizedStatus(
          "status.batch_running",
          {},
          "",
          "running",
          "status.rows",
          {
            completed: formatNumber(state.batchJob.completed, 0),
            total: formatNumber(state.batchJob.total, 0),
          },
        );
        scheduleBatchPoll();
      }
    } catch (error) {
      setLocalizedStatus("status.batch_status_failed", {}, error.message, "error");
      scheduleBatchPoll(2000);
    }
  }

  async function runBatch() {
    showFormMessage(elements.batchMessage);
    if (!state.selectedModel || !state.batchFile) {
      showFormMessage(elements.batchMessage, t("message.select_model_file"));
      return;
    }
    setBusy(true, t("status.submitting_batch"), "status.submitting_batch");
    try {
      state.batchJob = await api.submitBatch(state.batchFile, state.selectedModel.model_id);
      state.batchResult = null;
      renderBatchJob(state.batchJob);
      renderBatchResult(null);
      showFormMessage(elements.batchMessage);
      setLocalizedStatus("status.batch_queued", {}, "", "running", "status.row_count", { count: formatNumber(state.batchJob.total, 0) });
      scheduleBatchPoll(250);
    } catch (error) {
      showFormMessage(elements.batchMessage, error.message);
      setLocalizedStatus("status.batch_submission_failed", {}, error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function cancelBatch() {
    if (!state.batchJob || isTerminalJob(state.batchJob)) return;
    try {
      state.batchJob = await api.cancelJob(state.batchJob.job_id);
      renderBatchJob(state.batchJob);
      setLocalizedStatus("status.cancelling_batch", {}, "", "running", "status.batch_cancellation_cooperative");
      if (isTerminalJob(state.batchJob)) {
        state.batchResult = await api.jobResult(state.batchJob.job_id);
        renderBatchResult(state.batchResult);
      } else {
        scheduleBatchPoll(250);
      }
    } catch (error) {
      showFormMessage(elements.batchMessage, error.message);
      setLocalizedStatus("status.batch_cancellation_failed", {}, error.message, "error");
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
      dl.textContent = t("label.run_id");
      const dd = document.createElement("dd");
      dd.textContent = prediction.run_id;
      return [dl, dd];
    })());
    elements.exportPng.href = api.link(prediction.links.png);
    elements.exportCsv.href = api.link(prediction.links.csv);
  }

  function localizeHistoryKind(kind) {
    const keys = {
      prediction: "history.kind_prediction",
      aim: "history.kind_aim",
      batch_prediction: "history.kind_batch",
    };
    return keys[kind] ? t(keys[kind]) : (kind || "—");
  }

  function renderHistory(body) {
    state.history = Array.isArray(body?.items) ? body.items : [];
    state.historyTotal = Number(body?.total || 0);
    state.historyOffset = Number(body?.offset || 0);
    state.historyLimit = Number(body?.limit || state.historyLimit);
    elements.historyCount.textContent = state.historyTotal === 1
      ? t("history.count_one")
      : t("history.count_many", { count: formatNumber(state.historyTotal, 0) });
    elements.historyBody.replaceChildren();
    for (const item of state.history) {
      const row = document.createElement("tr");
      row.tabIndex = 0;
      row.dataset.historyId = item.id;
      for (const value of [shortId(item.id), localizeHistoryKind(item.kind), localizeJobState(item.status), formatDate(item.created_at)]) {
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
    elements.historyState.textContent = hasRows ? "" : t("history.none");
    elements.historyTable.hidden = !hasRows;
    elements.historyPrev.disabled = state.historyOffset <= 0;
    elements.historyNext.disabled = state.historyOffset + state.history.length >= state.historyTotal;
  }

  async function refreshHistory() {
    elements.historyState.hidden = false;
    elements.historyState.textContent = t("history.loading");
    try {
      const body = await api.history(state.historyLimit, state.historyOffset);
      renderHistory(body);
    } catch (error) {
      elements.historyTable.hidden = true;
      elements.historyState.hidden = false;
      elements.historyState.textContent = error.message;
      setLocalizedStatus("status.history_request_failed", {}, error.message, "error");
    }
  }

  async function openHistoryResult(item) {
    const runId = item.id;
    setLocalizedStatus("status.loading_result", {}, shortId(runId), "running");
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
        state.batchResult = await api.jobResult(runId);
        renderBatchResult(state.batchResult);
        setActivePanel("batch");
      } else {
        setLocalizedStatus("status.no_browser_result", {}, shortId(runId), "neutral", "status.unsupported_history", { id: shortId(runId) });
      }
    } catch (error) {
      setLocalizedStatus("status.no_browser_result", {}, `${shortId(runId)} · ${error.message}`, "neutral");
    }
  }

  function setActivePanel(panel) {
    state.activePanel = panel;
    app.dataset.activePanel = panel;
    document.querySelectorAll("[data-property-panel]").forEach((section) => {
      section.hidden = section.dataset.propertyPanel !== panel;
    });
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.classList.toggle("is-active", item.dataset.panel === panel);
    });
    setText(elements.propertiesContext, t(`nav.${panel}`).toUpperCase());
    if (panel === "history") refreshHistory();
  }

  async function refreshAll() {
    setLocalizedStatus("status.checking_api", {}, "", "running");
    try {
      state.health = await api.health();
      renderHealth();
    } catch (error) {
      state.health = null;
      setServerState(false);
      setText(elements.serverVersion, "—");
      state.models = [];
      renderModels();
      return;
    }
    try {
      await refreshModels();
      if (state.models.length) {
        setLocalizedStatus(
          "status.ready_models",
          { count: formatNumber(state.models.length, 0), suffix: state.models.length === 1 ? "" : "s" },
          "",
          "ok",
        );
      } else setLocalizedStatus("status.ready_no_models");
    } catch (error) {
      state.models = [];
      renderModels();
      setServerState(false, error.message);
    }
    await refreshHistory();
  }

  function bindEvents() {
    elements.refresh.addEventListener("click", refreshAll);
    elements.language.addEventListener("change", () => setLanguage(elements.language.value));
    elements.modelSelect.addEventListener("change", () => selectModel(selectedModelId()));
    elements.predictionForm.addEventListener("submit", runPrediction);
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

  applyLanguage();
  bindEvents();
  app.dataset.ready = "true";
  refreshAll();
})();
