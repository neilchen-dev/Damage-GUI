"""Tkinter desktop workbench adapter.

The window coordinates shared services and presentation components. Scientific
calculation, persistence, validation, and task execution remain outside this
module; this class translates user actions into service calls and renders the
structured results.
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

import matplotlib

from damage_gui.config import CONDITION_LIMITS, CONFIG, Config
from damage_gui.errors import DataValidationError, TaskStateError
from damage_gui.gui.dpi import (
    enable_windows_dpi_awareness,
    install_tk_scaling_monitor,
    sync_tk_scaling,
)
from damage_gui.gui.i18n import Translator
from damage_gui.gui.navigation import NAVIGATION_LABELS
from damage_gui.gui.panels import (
    AimPanel,
    BatchPanel,
    DatasetPanel,
    ExportPanel,
    HistoryPanel,
    ModelPanel,
    PredictionPanel,
    ValidationPanel,
)
from damage_gui.gui.presentation import (
    choice_value,
    model_type_choices,
    validation_choices,
)
from damage_gui.gui.resources import app_base_dir, resolve_icon_paths
from damage_gui.gui.styles import configure_styles
from damage_gui.gui.theme import Theme
from damage_gui.gui.workbench import WorkbenchShell
from damage_gui.logging_setup import setup_logging
from damage_gui.services.conditions import validate_condition
from damage_gui.storage.db import resolve_db_path
from damage_gui.tasks import TaskEvent, TaskManager, TaskStatus

if TYPE_CHECKING:
    import numpy as np
    from matplotlib.figure import Figure

    from damage_gui.data.loader import Condition, DamageDataManager
    from damage_gui.model.bundle import DamageModelService, ModelBundle
    from damage_gui.model.ood import OODReport
    from damage_gui.services.aim_service import AimService, AimServiceResult
    from damage_gui.services.batch_service import BatchReport, BatchService
    from damage_gui.services.prediction_service import PredictionResult, PredictionService
    from damage_gui.services.training_service import TrainingResult, TrainingService


class DamagePredictionGUI:
    """Desktop workbench controller and service adapter."""

    CONDITION_LIMITS = CONDITION_LIMITS

    def __init__(self, root: tk.Tk):
        self.root = root
        self.translator = Translator()
        self.root.title(self.translator.t("app.title"))
        self.root.geometry("1600x920")
        self.root.minsize(1280, 780)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.data_dir_var = tk.StringVar(value=str(app_base_dir() / "data"))
        self.level_var = tk.StringVar(value="F")
        self.model_type_var = tk.StringVar(value=model_type_choices(self.translator)[0][0])
        self.pod_components_var = tk.StringVar(value=str(CONFIG.pod_n_components))
        self.validation_var = tk.StringVar(value=validation_choices(self.translator)[0][0])
        self.h_var = tk.StringVar(value="0.0")
        self.v_var = tk.StringVar(value="150.0")
        self.deg_var = tk.StringVar(value="20.0")
        self.status_var = tk.StringVar(value=self.translator.t("status.initial"))

        self.bundle: ModelBundle | None = None
        self.service: DamageModelService | None = None
        self.current_prediction: np.ndarray | None = None
        self.current_truth: np.ndarray | None = None
        self.current_figure: Figure | None = None
        self.current_condition: Condition | None = None

        self.spread_mode_var = tk.StringVar(value="CEP")
        self.cep_var = tk.StringVar(value="5.0")
        self.rep_var = tk.StringVar(value="2.0")
        self.dep_var = tk.StringVar(value="2.0")
        self.aim_rho_var = tk.StringVar(value="0.0")
        self.aim_theta_var = tk.StringVar(value="")
        self.current_aim_result: AimServiceResult | None = None
        self.current_value_field: np.ndarray | None = None
        self.batch_csv_var = tk.StringVar(value="")

        self.task_manager = TaskManager()
        self._logger = logging.getLogger("damage_gui.gui")
        self._db_path = resolve_db_path()
        self._data_manager: DamageDataManager | None = None
        self._service_config = None
        self._runtime_initialized = False
        self.training_service: TrainingService | None = None
        self.prediction_service: PredictionService | None = None
        self.batch_service: BatchService | None = None
        self.aim_service: AimService | None = None

        self._last_train_time: float | None = None
        self._last_predict_time: float | None = None
        self.last_ood_report: OODReport | None = None
        self.theme = Theme.from_config()

        self._apply_window_icon()
        self._configure_styles()
        self._build_workbench()
        # Let the first window paint before importing the data-loader graph.
        # Event handlers still initialize it synchronously if invoked earlier.
        self.root.after(100, self._initialize_runtime_context)

    # ---------- Shell and contextual panels ----------

    def _configure_styles(self) -> None:
        configure_styles(self.root, self.theme)

    def _build_workbench(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        callbacks = {
            "load": self.on_load_model,
            "save": self.on_save_model,
            "export_csv": self.on_export_csv,
            "export_png": self.on_export_png,
            "close": self._on_close,
            "train": self.on_train,
            "cancel_training": self.on_cancel_training,
            "predict": self.on_predict,
            "stop": self._stop_current_task,
            "navigate_dataset": lambda: self._navigate("dataset"),
            "navigate_prediction": lambda: self._navigate("prediction"),
            "navigate_batch": lambda: self._navigate("batch"),
            "navigate_aim": lambda: self._navigate("aim"),
            "navigate_history": lambda: self._navigate("history"),
            "navigate_export": lambda: self._navigate("export"),
        }
        self.workbench = WorkbenchShell(
            self.root,
            theme=self.theme,
            translator=self.translator,
            callbacks=callbacks,
            on_navigate=self._navigate,
            on_view_change=self._on_view_change,
            on_language=self._set_language,
        )
        self.navigation = self.workbench.navigation
        self.properties = self.workbench.properties
        self.visualization = self.workbench.visualization
        self.results = self.workbench.results
        self.status_bar = self.workbench.status
        self.status_var = self.status_bar.status_var

        self.figures = self.visualization.figures
        self.canvases = self.visualization.canvases
        self._build_context_panels()
        self._navigate("dataset")
        self.results.reset()
        self._update_model_status()
        self._set_busy(False)

    def _build_context_panels(self) -> None:
        self.dataset_panel = DatasetPanel(
            self.properties.body,
            data_dir_var=self.data_dir_var,
            level_var=self.level_var,
            on_browse=self.on_browse_data,
            translator=self.translator,
        )
        self.model_panel = ModelPanel(
            self.properties.body,
            model_type_var=self.model_type_var,
            pod_components_var=self.pod_components_var,
            validation_var=self.validation_var,
            on_train=self.on_train,
            on_cancel=self.on_cancel_training,
            on_load=self.on_load_model,
            on_save=self.on_save_model,
            translator=self.translator,
        )
        self.validation_panel = ValidationPanel(
            self.properties.body, validation_var=self.validation_var, translator=self.translator
        )
        self.prediction_panel = PredictionPanel(
            self.properties.body,
            h_var=self.h_var,
            v_var=self.v_var,
            deg_var=self.deg_var,
            on_predict=self.on_predict,
            translator=self.translator,
        )
        self.batch_panel = BatchPanel(
            self.properties.body,
            csv_var=self.batch_csv_var,
            on_browse=self.on_browse_batch_csv,
            on_run=self.on_run_batch,
            on_cancel=lambda: self.task_manager.cancel("batch"),
            translator=self.translator,
        )
        self.aim_panel = AimPanel(
            self.properties.body,
            spread_mode_var=self.spread_mode_var,
            cep_var=self.cep_var,
            rep_var=self.rep_var,
            dep_var=self.dep_var,
            rho_var=self.aim_rho_var,
            theta_var=self.aim_theta_var,
            on_optimize=self.on_optimize_aim,
            translator=self.translator,
        )
        self.history_panel = HistoryPanel(
            self.properties.body, db_path=str(self._db_path), translator=self.translator
        )
        self.export_panel = ExportPanel(
            self.properties.body,
            on_csv=self.on_export_csv,
            on_png=self.on_export_png,
            translator=self.translator,
        )
        for key, panel in (
            ("dataset", self.dataset_panel),
            ("model", self.model_panel),
            ("validation", self.validation_panel),
            ("prediction", self.prediction_panel),
            ("batch", self.batch_panel),
            ("aim", self.aim_panel),
            ("history", self.history_panel),
            ("export", self.export_panel),
        ):
            self.properties.add(key, panel)

    def _navigate(self, key: str) -> None:
        if key not in NAVIGATION_LABELS:
            return
        self.navigation.select(key)
        self.properties.show(key, self.translator.t(f"nav.{key}"))

    def _set_language(self, language: str) -> None:
        model_type = self._selected_model_type()
        validation_mode = self._selected_validation_mode()
        if not self.translator.set_language(language):
            return
        self.root.title(self.translator.t("app.title"))
        self.model_type_var.set(
            next(
                label for label, value in model_type_choices(self.translator) if value == model_type
            )
        )
        self.validation_var.set(
            next(
                label
                for label, value in validation_choices(self.translator)
                if value == validation_mode
            )
        )
        selected = self.navigation.tree.selection()
        self._navigate(selected[0] if selected and selected[0] in NAVIGATION_LABELS else "dataset")
        self._sync_visualization_context()
        self._update_model_status()
        self._set_busy(self.task_manager.is_busy())

    def _on_view_change(self, key: str) -> None:
        figure = self.visualization.figures.get(key)
        self.current_figure = figure
        self._sync_visualization_context()

    def _sync_visualization_context(self) -> None:
        """Keep the viewport header tied to the figure currently selected."""
        if self.visualization.current_view == "aim":
            if self.current_aim_result is None:
                self.visualization.set_context(
                    self.translator.t("visualization.aim_title"),
                    self.translator.t("visualization.aim_empty"),
                )
                return
            result = self.current_aim_result
            self.visualization.set_context(
                self.translator.t("visualization.aim_title"),
                f"{result.spread_mode} · best point ({result.best_x:.1f}, {result.best_y:.1f}) m",
            )
        elif self.current_condition is not None and self.current_prediction is not None:
            condition = self.current_condition
            self.visualization.set_context(
                self.translator.t("visualization.single_title"),
                f"h = {condition.h:g} m · v = {condition.v:g} m/s · θ = {condition.deg:g}°",
            )
        else:
            self.visualization.set_context(
                self.translator.t("visualization.title"),
                self.translator.t("visualization.no_prediction"),
            )

    def _stop_current_task(self) -> None:
        cancelled = False
        for kind in ("training", "batch"):
            cancelled = self.task_manager.cancel(kind) or cancelled
        if cancelled:
            self._set_status("正在取消当前任务…", kind="busy")

    def _apply_window_icon(self) -> None:
        ico_path, png_path = resolve_icon_paths()
        try:
            if ico_path is not None:
                self.root.iconbitmap(default=str(ico_path))
        except tk.TclError:
            pass
        try:
            if png_path is not None:
                icon_image = tk.PhotoImage(file=str(png_path))
                self.root.iconphoto(True, icon_image)
                self._icon_image = icon_image
            else:
                self._icon_image = None
        except tk.TclError:
            self._icon_image = None

    # ---------- Status and service state ----------

    def _set_status(self, text: str, kind: str = "info") -> None:
        self.status_bar.set_status(text, kind)
        self.root.update_idletasks()

    def _set_progress(self, percent: float, stage: str) -> None:
        self.status_bar.set_progress(percent, stage)

    def _set_busy(self, busy: bool) -> None:
        active = busy or self.task_manager.is_busy()
        action_state = "disabled" if active else "normal"
        for button in (
            self.model_panel.train_button,
            self.model_panel.load_button,
            self.workbench.open_button,
        ):
            button.configure(state=action_state)

        model_state = "normal" if not active and self.bundle is not None else "disabled"
        prediction_state = model_state
        aim_state = "normal" if not active and self.current_prediction is not None else "disabled"
        for button in (self.model_panel.save_button, self.workbench.save_button):
            button.configure(state=model_state)
        for button in (
            self.prediction_panel.predict_button,
            self.workbench.run_button,
            self.batch_panel.run_button,
        ):
            button.configure(state=prediction_state)
        self.aim_panel.optimize_button.configure(state=aim_state)
        self.model_panel.cancel_button.configure(
            state="normal" if self._task_is_busy("training") else "disabled"
        )
        self.batch_panel.cancel_button.configure(
            state="normal" if self._task_is_busy("batch") else "disabled"
        )
        self.workbench.stop_button.configure(state="normal" if active else "disabled")

    def _task_is_busy(self, kind: str) -> bool:
        """Check an optional task without assuming it has been submitted."""
        return self.task_manager.get(kind) is not None and self.task_manager.is_busy(kind)

    def _set_data_dir(self, data_dir: str, config: Config | None = None) -> None:
        from damage_gui.data.loader import DamageDataManager

        self.data_dir_var.set(data_dir)
        self._data_manager = DamageDataManager(data_dir)
        self._service_config = config
        self._runtime_initialized = True
        self.service = None
        self.training_service = None
        self.prediction_service = None
        self.batch_service = None
        if hasattr(self, "dataset_panel"):
            self.dataset_panel.refresh(data_dir, self.level_var.get())

    def _initialize_runtime_context(self) -> None:
        """Initialize data context after the initial desktop paint."""
        if not self._runtime_initialized:
            self._set_data_dir(self.data_dir_var.get())

    def _ensure_runtime_context(self) -> None:
        """Preserve synchronous behavior for programmatic early callbacks."""
        if not self._runtime_initialized:
            self._initialize_runtime_context()

    def _ensure_model_service(self) -> DamageModelService:
        self._ensure_runtime_context()
        assert self._data_manager is not None
        if self.service is None:
            from damage_gui.model.bundle import DamageModelService

            self.service = DamageModelService(self._data_manager, config=self._service_config)
        return self.service

    def _ensure_training_service(self) -> TrainingService:
        service = self._ensure_model_service()
        if self.training_service is None:
            from damage_gui.services.training_service import TrainingService

            self.training_service = TrainingService(service, db_path=self._db_path)
        return self.training_service

    def _ensure_prediction_service(self) -> PredictionService:
        self._ensure_runtime_context()
        assert self._data_manager is not None
        if self.prediction_service is None:
            from damage_gui.services.prediction_service import PredictionService

            self.prediction_service = PredictionService(
                self._data_manager,
                model_service=self.service,
                config=self._service_config,
            )
        return self.prediction_service

    def _ensure_batch_service(self) -> BatchService:
        self._ensure_runtime_context()
        assert self._data_manager is not None
        if self.batch_service is None:
            from damage_gui.services.batch_service import BatchService

            self.batch_service = BatchService(self._data_manager, config=self._service_config)
        return self.batch_service

    def _active_config(self) -> Config:
        if self.bundle is not None:
            return self.bundle.resolved_config()
        if self.service is not None:
            return self.service.config
        if self._service_config is not None:
            return self._service_config
        return CONFIG

    def _clear_prediction_state(self) -> None:
        """Remove prediction-dependent UI state before a new result is shown."""
        self.current_prediction = None
        self.current_truth = None
        self.current_condition = None
        self.current_figure = None
        self.current_aim_result = None
        self.current_value_field = None
        self.last_ood_report = None
        self._last_predict_time = None
        for key in ("triple", "full", "aim"):
            self.visualization.clear(key)
        self.visualization.set_view("triple")
        self.visualization.set_context(
            self.translator.t("visualization.title"),
            self.translator.t("visualization.no_prediction"),
        )
        self.results.reset()
        self.prediction_panel.set_reliability(self.translator.t("status.no_prediction"))
        self.aim_panel.set_summary(self.translator.t("status.no_optimization"))

    # ---------- Input mapping ----------

    def _current_condition(self) -> Condition:
        try:
            values = {
                "h": float(self.h_var.get()),
                "v": float(self.v_var.get()),
                "deg": float(self.deg_var.get()),
            }
        except ValueError as exc:
            raise ValueError("h、v、deg 必须是数字") from exc
        try:
            return validate_condition(**values)
        except DataValidationError as exc:
            field = getattr(exc, "condition_field", None)
            value = getattr(exc, "condition_value", None)
            lower = getattr(exc, "condition_lower", None)
            upper = getattr(exc, "condition_upper", None)
            if field is not None:
                raise ValueError(
                    f"{field} 超出合法范围 [{lower:g}, {upper:g}]，当前为 {value:g}"
                ) from exc
            raise

    def _selected_model_type(self) -> str:
        return choice_value(model_type_choices(self.translator), self.model_type_var.get(), "rbf")

    def _selected_validation_mode(self) -> str:
        return choice_value(
            validation_choices(self.translator), self.validation_var.get(), "random"
        )

    def _validation_label(self, mode: str) -> str:
        return next(
            (label for label, value in validation_choices(self.translator) if value == mode),
            mode,
        )

    # ---------- Results and model context ----------

    def _update_key_metrics(self, mean_re: float | None, p95_hybrid: float | None) -> None:
        import pandas as pd

        self.results.set_value(
            "mean_error", None if mean_re is None or pd.isna(mean_re) else f"{mean_re:.2%}"
        )
        self.results.set_value(
            "p95_error",
            None if p95_hybrid is None or pd.isna(p95_hybrid) else f"{p95_hybrid:.2%}",
        )
        if mean_re is None or p95_hybrid is None:
            self.validation_panel.set_result(self.translator.t("status.no_validation"))
        else:
            target = self._active_config().relative_error_target
            self.validation_panel.set_result(
                self.translator.t("validation.summary", mean=mean_re, p95=p95_hybrid, target=target)
            )

    def _update_model_status(self) -> None:
        if self.bundle is None:
            self.model_panel.set_model_status(self.translator.t("status.no_model"))
            return
        bundle = self.bundle
        model = bundle.model
        lines = [
            f"{getattr(model, 'model_name', type(model).__name__)}",
            self.translator.t(
                "model.level_samples",
                level=bundle.level,
                train=len(bundle.train_conditions),
                test=len(bundle.test_conditions),
            ),
        ]
        lines.append(
            self.translator.t(
                "model.validation", label=self._validation_label(bundle.validation_mode)
            )
        )
        metadata = getattr(bundle, "metadata", None)
        if metadata is not None:
            lines.append(self.translator.t("model.id", id=metadata.model_id[:8]))
        else:
            lines.append(self.translator.t("model.legacy"))
        if self._last_train_time is not None:
            lines.append(self.translator.t("model.training", seconds=self._last_train_time))
        self.model_panel.set_model_status("\n".join(lines))

    def _update_results_prediction(self, result: PredictionResult) -> None:
        self.results.set_value("maximum", f"{result.peak_intensity:.4f}")
        self.results.set_value("area", f"{result.damage_area_ratio:.2%}")
        self.results.set_value("grid", f"{result.prediction.shape[1]}×{result.prediction.shape[0]}")
        metrics = result.truth_comparison_metrics
        mean_re = float(metrics["MeanRelativeError"]) if metrics else None
        p95_hybrid = float(metrics["P95HybridError"]) if metrics else None
        self._update_key_metrics(mean_re, p95_hybrid)

        report = result.ood_report
        if report is None:
            for key in ("confidence", "ood_distance", "inside_hull", "local_support"):
                self.results.set_value(key, None)
            self.prediction_panel.set_reliability(self.translator.t("status.no_ood"))
        else:
            confidence_key = {
                "high": "ood.high",
                "medium": "ood.medium",
                "low": "ood.low",
            }.get(report.level, "common.unknown")
            confidence = self.translator.t(confidence_key)
            self.results.set_value("confidence", confidence)
            self.results.set_value("ood_distance", f"{report.distance:.3f}")
            inside_hull = (
                self.translator.t("common.yes")
                if report.in_hull is True
                else self.translator.t("common.no")
                if report.in_hull is False
                else None
            )
            self.results.set_value("inside_hull", inside_hull)
            local_support = getattr(report, "local_support", None)
            self.results.set_value(
                "local_support",
                self.translator.t("common.yes")
                if local_support is True
                else self.translator.t("common.no")
                if local_support is False
                else None,
            )
            reliability = [
                self.translator.t("reliability.summary", level=confidence, distance=report.distance)
            ]
            if report.in_hull is False:
                reliability.append(self.translator.t("reliability.outside"))
            elif local_support is False:
                reliability.append(self.translator.t("reliability.sparse"))
            self.prediction_panel.set_reliability("\n".join(reliability))

        self.results.set_value("elapsed", f"{result.elapsed_ms} ms")
        model_name = "—"
        if self.bundle is not None:
            model_name = getattr(self.bundle.model, "model_name", type(self.bundle.model).__name__)
        self.results.set_value("model", model_name)

    def _update_advice_card(
        self, mean_re: float | None, p95_hybrid: float | None, scope: str
    ) -> None:
        import pandas as pd

        target = self._active_config().relative_error_target
        if mean_re is None or pd.isna(mean_re):
            text = self.translator.t("advice.no_metrics")
        elif mean_re < target and p95_hybrid is not None and p95_hybrid < target:
            text = self.translator.t("advice.pass", scope=scope, target=target)
        elif mean_re < target:
            text = self.translator.t("advice.p95", scope=scope)
        else:
            text = self.translator.t("advice.fail", scope=scope)
        self.results.set_advice(text)

    # ---------- Dataset / model lifecycle ----------

    def on_browse_data(self) -> None:
        selected = filedialog.askdirectory(
            title="选择 data 文件夹", initialdir=self.data_dir_var.get()
        )
        if not selected:
            return
        self._set_data_dir(selected)
        self._set_status(f"已选择数据目录: {selected}")

    def on_train(self) -> None:
        try:
            training_service = self._ensure_training_service()
            level = self.level_var.get().strip().upper()
            model_type = self._selected_model_type()
            validation_mode = self._selected_validation_mode()
            try:
                pod_components = int(self.pod_components_var.get())
            except ValueError as exc:
                raise ValueError("POD 主成分数必须是整数") from exc
            if pod_components < 2:
                raise ValueError("POD 主成分数至少为 2")

            def work(ctx) -> TrainingResult:
                return training_service.train(
                    level,
                    validation_mode=validation_mode,
                    model_type=model_type,
                    pod_n_components=pod_components,
                    progress=ctx.report_progress,
                    cancel_check=ctx.cancel_check,
                )

            self.task_manager.submit("training", work)
            self._set_busy(True)
            self._set_status(
                f"正在后台训练等级 {level} 模型（{self.model_type_var.get()}，"
                f"{self.validation_var.get()}），请稍候…",
                kind="busy",
            )
            self._poll_tasks()
        except TaskStateError as exc:
            self._show_error("训练启动失败", str(exc))
        except Exception as exc:
            self._set_busy(False)
            self._handle_error("训练失败", exc)

    def on_cancel_training(self) -> None:
        if self.task_manager.cancel("training"):
            self._set_status("正在取消训练…", kind="busy")

    def _poll_tasks(self) -> None:
        for event in self.task_manager.poll():
            if event.type == "progress":
                percent = event.done / event.total * 100.0 if event.total > 0 else 0.0
                self._set_progress(percent, event.stage)
            elif event.type == "finished":
                if event.kind == "training":
                    self._on_training_finished(event)
                elif event.kind == "batch":
                    self._on_batch_finished(event)
        if self.task_manager.is_busy():
            self.root.after(80, self._poll_tasks)
        else:
            self._set_busy(False)
            self._set_progress(0.0, "")

    def _on_training_finished(self, event: TaskEvent) -> None:
        if event.status == TaskStatus.SUCCESS:
            self._finish_training(event.result)
        elif event.status == TaskStatus.CANCELLED:
            self._set_status("训练已取消。", kind="info")
        else:
            self._show_error("训练失败", event.error_summary or "未知错误")

    def _finish_training(self, result: TrainingResult) -> None:
        bundle = result.bundle
        self.bundle = bundle
        self._last_train_time = bundle.train_time_seconds
        self._clear_prediction_state()
        self._set_progress(100.0, "训练与评估完成")
        self._update_key_metrics(result.mean_relative_error, result.p95_hybrid_error)
        self._update_model_status()
        self._update_advice_card(result.mean_relative_error, result.p95_hybrid_error, "测试集")
        validation_note = ""
        if bundle.validation_mode != "random":
            validation_label = self._validation_label(bundle.validation_mode)
            validation_note = f" 验证方式: {validation_label}，指标来自未见工况的折外预测。"
        db_note = "" if result.db_recorded else "（警告：训练结果未写入 SQLite 追溯数据库）"
        core_summary = ""
        if result.mean_relative_error is not None:
            core_summary = (
                f"核心指标: 平均相对误差 {result.mean_relative_error:.2%}, "
                f"P95混合误差 {result.p95_hybrid_error:.2%}。"
            )
        self._set_status(
            f"训练完成: {bundle.level}（{getattr(bundle.model, 'model_name', 'RBF')}，"
            f"耗时 {bundle.train_time_seconds:.1f} s）。{core_summary}{validation_note} "
            f"评估结果已保存为 {result.accuracy_report_path.name} 和 "
            f"{result.condition_report_path.name}{db_note}",
            kind="ok" if not db_note else "info",
        )

    def on_save_model(self) -> None:
        try:
            from damage_gui.model.registry import save_model

            if self.bundle is None:
                raise RuntimeError("请先训练或加载模型")
            output_path = filedialog.asksaveasfilename(
                title="保存模型",
                defaultextension=".joblib",
                filetypes=[("Joblib Model", "*.joblib")],
                initialfile=f"damage_model_{self.bundle.level}.joblib",
            )
            if not output_path:
                return
            save_model(self.bundle, output_path)
            note = (
                ""
                if getattr(self.bundle, "metadata", None) is not None
                else "（旧版模型，未写入元数据 sidecar）"
            )
            self._set_status(f"模型已保存: {output_path}{note}", kind="ok")
        except Exception as exc:
            self._handle_error("保存模型失败", exc)

    def on_load_model(self) -> None:
        try:
            from damage_gui.evaluation.metrics import extract_core_metrics
            from damage_gui.model.registry import load_model

            model_path = filedialog.askopenfilename(
                title="加载模型", filetypes=[("Joblib Model", "*.joblib")]
            )
            if not model_path:
                return
            bundle = load_model(model_path)
            self.bundle = bundle
            self._clear_prediction_state()
            self.level_var.set(bundle.level)
            self._last_train_time = getattr(bundle, "train_time_seconds", None) or None
            if bundle.data_dir:
                self._set_data_dir(bundle.data_dir, bundle.resolved_config())
            mean_re, p95_hybrid = extract_core_metrics(
                bundle.accuracy_report, bundle.resolved_config()
            )
            self._update_key_metrics(mean_re, p95_hybrid)
            self._update_model_status()
            self._update_advice_card(mean_re, p95_hybrid, "测试集")
            self._set_busy(False)
            legacy_note = (
                ""
                if getattr(bundle, "metadata", None) is not None
                else "（旧版模型：无元数据追溯信息）"
            )
            self._set_status(f"模型已加载: {model_path}{legacy_note}", kind="ok")
        except Exception as exc:
            self._handle_error("加载模型失败", exc)

    # ---------- Batch prediction ----------

    def on_browse_batch_csv(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择批量预测输入 CSV", filetypes=[("CSV File", "*.csv")]
        )
        if selected:
            self.batch_csv_var.set(selected)
            self.batch_panel.set_selected_path(selected)

    def on_run_batch(self) -> None:
        try:
            if self.bundle is None:
                raise RuntimeError("请先训练或加载模型")
            batch_service = self._ensure_batch_service()
            csv_path = self.batch_csv_var.get().strip()
            if not csv_path:
                raise DataValidationError("请先选择批量预测输入 CSV 文件")
            parsed = batch_service.parse_csv(csv_path, default_level=self.bundle.level)
            self.batch_panel.set_info(
                f"Rows detected: {parsed.total}\n"
                f"Valid: {len(parsed.rows)} · Invalid: {len(parsed.invalid)}"
            )
            if not parsed.rows:
                raise DataValidationError("输入 CSV 中没有可预测的合法行")
            output_path = filedialog.asksaveasfilename(
                title="保存批量预测结果",
                defaultextension=".csv",
                filetypes=[("CSV File", "*.csv")],
                initialfile=Path(csv_path).stem + "_result.csv",
            )
            if not output_path:
                return

            bundle = self.bundle
            data_manager = self._data_manager
            batch_service = self._ensure_batch_service()

            def work(ctx) -> BatchReport:
                return batch_service.run(
                    bundle,
                    parsed,
                    data_manager=data_manager,
                    output_path=output_path,
                    db_path=self._db_path,
                    input_source=Path(csv_path).name,
                    progress=ctx.report_progress,
                    cancel_check=ctx.cancel_check,
                )

            self.task_manager.submit("batch", work)
            self._set_busy(True)
            invalid_note = (
                f"，{len(parsed.invalid)} 行输入无效将标记为失败" if parsed.invalid else ""
            )
            self._set_status(
                f"正在后台批量预测 {parsed.total} 个工况{invalid_note}，请稍候…",
                kind="busy",
            )
            self._poll_tasks()
        except TaskStateError as exc:
            self._show_error("批量预测启动失败", str(exc))
        except DataValidationError as exc:
            self._show_error("批量输入无效", str(exc))
        except Exception as exc:
            self._set_busy(False)
            self._handle_error("批量预测失败", exc)

    def _on_batch_finished(self, event: TaskEvent) -> None:
        if event.status == TaskStatus.SUCCESS:
            report: BatchReport = event.result
            output_name = Path(report.output_path).name if report.output_path else "-"
            db_note = "" if report.db_recorded else "（警告：结果未写入 SQLite 追溯数据库）"
            self._set_status(
                f"批量预测完成: 成功 {report.success_count}/{report.total}，失败 "
                f"{report.failed_count}，耗时 {report.duration_ms} ms。结果已保存为 "
                f"{output_name}{db_note}",
                kind="ok" if report.failed_count == 0 else "info",
            )
        elif event.status == TaskStatus.CANCELLED:
            from damage_gui.services.batch_service import BatchReport

            report = event.result
            if isinstance(report, BatchReport):
                self._set_status(
                    f"批量预测已取消: 已完成 {len(report.rows)}/{report.total} 行，"
                    "已完成部分保留在输出中。"
                )
            else:
                self._set_status("批量预测已取消。")
        else:
            self._show_error("批量预测失败", event.error_summary or "未知错误")

    # ---------- Prediction and export ----------

    def on_predict(self) -> None:
        try:
            if self.bundle is None:
                raise RuntimeError("请先训练或加载模型")
            prediction_service = self._ensure_prediction_service()
            self._clear_prediction_state()
            condition = self._current_condition()
            config = self._active_config()
            self.current_condition = condition
            self._set_status("正在预测并生成热力图…", kind="busy")
            result = prediction_service.predict(self.bundle, condition, config=config)
            self.current_prediction = result.prediction
            self._last_predict_time = result.elapsed_seconds
            self.current_truth = result.truth
            self.last_ood_report = result.ood_report
            self.current_aim_result = None
            self.current_value_field = None
            self._clear_aim_view()

            from damage_gui.visualization.plots import render_full_prediction, render_heatmaps

            triple_figure = render_heatmaps(
                result.truth,
                result.prediction,
                display_threshold=config.display_threshold,
                config=config,
            )
            full_figure = render_full_prediction(result.prediction, config)
            self.visualization.set_figure(triple_figure, "triple")
            self.visualization.set_figure(full_figure, "full")
            selected_view = "triple" if result.truth is not None else "full"
            self.visualization.set_view(selected_view)
            self.current_figure = self.visualization.figures[selected_view]
            self._sync_visualization_context()
            self._update_results_prediction(result)
            self._update_advice_card(
                float(result.truth_comparison_metrics["MeanRelativeError"])
                if result.truth_comparison_metrics
                else None,
                float(result.truth_comparison_metrics["P95HybridError"])
                if result.truth_comparison_metrics
                else None,
                "当前工况",
            )
            ood_note = ""
            if result.ood_report is not None:
                ood_note = (
                    f" 模型可信度: {result.ood_report.level_label} "
                    f"(d={result.ood_report.distance:.3f})。"
                )
                if result.ood_report.in_hull is False:
                    ood_note += " 当前工况位于训练凸包外。"
                elif getattr(result.ood_report, "local_support", None) is False:
                    ood_note += " 当前工况位于局部数据空洞。"
            status_note = (
                "并已匹配到真实矩阵，当前显示对比三联图。"
                if result.truth is not None
                else "当前工况没有真实矩阵，显示全视图预测热力图。"
            )
            self._set_status(
                f"预测完成（耗时 {result.elapsed_ms} ms），{status_note}{ood_note}",
                kind=(
                    "info"
                    if result.ood_report is not None and result.ood_report.is_extrapolation
                    else "ok"
                ),
            )
            if result.ood_report is not None and result.ood_report.is_extrapolation:
                reason = result.advice.ood_geometry_reason or "训练数据覆盖边缘"
                self.results.set_advice(
                    f"⚠ 当前工况位于{reason}（最近训练工况距离 "
                    f"{result.ood_report.distance:.3f}），建议在该区域补充仿真数据后重新训练。"
                )
        except Exception as exc:
            self._handle_error("预测失败", exc)

    def _selected_result_figure(self) -> Figure | None:
        return self.visualization.current_figure or self.current_figure

    def on_export_csv(self) -> None:
        try:
            from damage_gui.services.export_service import export_matrix_csv

            if self.current_prediction is None or self.current_condition is None:
                raise RuntimeError("请先生成预测结果")
            output_path = filedialog.asksaveasfilename(
                title="导出预测矩阵 CSV",
                defaultextension=".csv",
                filetypes=[("CSV File", "*.csv")],
                initialfile=(
                    f"predicted_{self.bundle.level if self.bundle else 'X'}"
                    f"_h_{int(round(self.current_condition.h * 10))}"
                    f"_v_{int(round(self.current_condition.v * 10))}"
                    f"_deg_{int(round(self.current_condition.deg * 10))}.csv"
                ),
            )
            if not output_path:
                return
            export_matrix_csv(self.current_prediction, output_path, self._active_config())
            self._set_status(f"预测矩阵已导出: {output_path}", kind="ok")
        except Exception as exc:
            self._handle_error("导出 CSV 失败", exc)

    def on_export_png(self) -> None:
        try:
            from damage_gui.services.export_service import export_figure_png

            figure = self._selected_result_figure()
            if figure is None:
                raise RuntimeError("请先生成热力图")
            output_path = filedialog.asksaveasfilename(
                title="导出热力图 PNG",
                defaultextension=".png",
                filetypes=[("PNG Image", "*.png")],
                initialfile="damage_heatmap.png",
            )
            if not output_path:
                return
            export_figure_png(figure, output_path, dpi=self._active_config().export_dpi)
            self._set_status(f"热力图已导出: {output_path}", kind="ok")
        except Exception as exc:
            self._handle_error("导出 PNG 失败", exc)

    # ---------- Aim optimization ----------

    def _clear_aim_view(self) -> None:
        self.visualization.clear("aim")
        self.aim_panel.set_summary(self.translator.t("status.no_optimization"))

    def on_optimize_aim(self) -> None:
        try:
            from damage_gui.data.preprocessing import coordinate_axes
            from damage_gui.services.aim_service import AimService
            from damage_gui.visualization.plots import render_aim_optimization

            if self.current_prediction is None:
                raise RuntimeError("请先执行毁伤场预测")
            if self.aim_service is None:
                self.aim_service = AimService()
            x_axis, y_axis = coordinate_axes(self.current_prediction.shape, self._active_config())
            mode = self.spread_mode_var.get()
            result = self.aim_service.optimize(
                self.current_prediction,
                x_axis,
                y_axis,
                spread_mode=mode,
                cep=self.cep_var.get(),
                rep=self.rep_var.get(),
                dep=self.dep_var.get(),
                rho=self.aim_rho_var.get(),
                theta_deg=self.aim_theta_var.get(),
                reliability=1.0,
            )
            self.current_aim_result = result
            self.current_value_field = result.value_field
            figure = render_aim_optimization(self.current_prediction, result, self._active_config())
            self.visualization.set_figure(figure, "aim")
            self.visualization.set_view("aim")
            self.current_figure = figure
            self._sync_visualization_context()
            rho = getattr(result, "rho", 0.0) or 0.0
            spread_text = f"σx={result.sigma_x:.1f} m, σy={result.sigma_y:.1f} m"
            if rho:
                spread_text += f", ρ={rho:.2f}"
            self.aim_panel.set_summary(
                f"Best point: ({result.best_x:.1f}, {result.best_y:.1f}) m\n"
                f"Vmax: {result.vmax:.4f}\n"
                f"Relative gain: {result.gain_relative:+.2%}\n"
                f"Shift: {result.shift_distance:.1f} m\n{spread_text}"
            )
            mode_label = (
                f"CEP={self.cep_var.get()} m"
                if mode == "CEP"
                else f"REP={self.rep_var.get()} m / DEP={self.dep_var.get()} m"
            )
            if mode != "CEP" and rho:
                mode_label += f", ρ={rho:.2f}"
            self._set_status(
                f"瞄准优化完成 ({mode_label}): 最佳瞄准点 "
                f"({result.best_x:.1f}, {result.best_y:.1f}) m, "
                f"Vmax={result.vmax:.4f}, 增益={result.gain_relative:.2%}",
                kind="ok",
            )
        except Exception as exc:
            self._handle_error("瞄准优化失败", exc)

    # ---------- Errors and shutdown ----------

    def _handle_error(self, title: str, exc: Exception) -> None:
        self._logger.exception("%s: %s", title, exc)
        self._set_status(f"{title}: {exc}", kind="error")
        messagebox.showerror(title, f"{exc}\n\n详细信息已记录到日志文件 logs/damage_gui.log。")

    def _show_error(self, title: str, message: str) -> None:
        self._set_status(f"{title}: {message}", kind="error")
        messagebox.showerror(title, message)

    def _on_close(self) -> None:
        self.task_manager.shutdown(timeout=2.0)
        self.root.destroy()


def create_root() -> tk.Tk:
    """Create a desktop root after selecting DPI awareness and Tk scaling."""
    awareness = enable_windows_dpi_awareness()
    matplotlib.use("TkAgg")
    root = tk.Tk()
    scaling = sync_tk_scaling(root)
    install_tk_scaling_monitor(root)
    logging.getLogger("damage_gui.gui.dpi").info(
        "DPI awareness=%s via %s; monitor_dpi=%s; Tk scaling %.4f -> %.4f",
        awareness.mode,
        awareness.api,
        scaling.actual_dpi if scaling.actual_dpi is not None else "unknown",
        scaling.before if scaling.before is not None else 0.0,
        scaling.after if scaling.after is not None else 0.0,
    )
    return root


def main() -> None:
    setup_logging()
    root = create_root()
    DamagePredictionGUI(root)
    root.mainloop()
