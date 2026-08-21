"""Tkinter 主窗口：训练编排（后台线程）、预测、可视化与瞄准优化。

训练在后台线程执行（P2 性能优化），通过队列 + root.after 轮询更新进度，
支持随时取消；预测与瞄准优化在主线程（单次计算耗时短）。
"""
from __future__ import annotations

import queue
import threading
import time
import traceback
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from tkinter import filedialog, messagebox, ttk

from damage_gui.config import APP_TITLE, Config, CONFIG
from damage_gui.data.loader import Condition, DamageDataManager, read_damage_matrix
from damage_gui.data.preprocessing import coordinate_axes, evaluation_fields
from damage_gui.evaluation.metrics import extract_core_metrics, metric_row
from damage_gui.model.bundle import DamageModelService, ModelBundle, TrainingCancelled
from damage_gui.model.ood import OODReport
from damage_gui.model.validation import VALIDATION_LABELS
from damage_gui.optimization.aim import AimOptimizationResult, optimize_aim
from damage_gui.visualization.plots import (
    render_aim_optimization,
    render_full_prediction,
    render_heatmaps,
)
from damage_gui.gui.presentation import (
    MODEL_TYPE_CHOICES,
    VALIDATION_CHOICES,
    choice_value,
    metric_display,
)
from damage_gui.gui.resources import app_base_dir, resolve_icon_paths
from damage_gui.gui.widgets import bind_autowrap, rounded_rect


class DamagePredictionGUI:
    # 工况输入的合法范围与 Spinbox 步长：(下限, 上限, 步长)。
    # 箭头微调受 from_/to 约束，手动键入在 _current_condition 中二次校验，
    # 防止非法字符或极端负数进入后端插值器导致崩溃。
    CONDITION_LIMITS: dict[str, tuple[float, float, float]] = {
        "h": (0.0, 500.0, 5.0),
        "v": (0.0, 1000.0, 10.0),
        "deg": (0.0, 90.0, 1.0),
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1600x920")
        self.root.minsize(1280, 780)

        self.data_dir_var = tk.StringVar(value=str(app_base_dir() / "data"))
        self.level_var = tk.StringVar(value="F")
        self.model_type_var = tk.StringVar(value=MODEL_TYPE_CHOICES[0][0])
        self.pod_components_var = tk.StringVar(value=str(CONFIG.pod_n_components))
        self.validation_var = tk.StringVar(value=VALIDATION_CHOICES[0][0])
        self.h_var = tk.StringVar(value="0.0")
        self.v_var = tk.StringVar(value="150.0")
        self.deg_var = tk.StringVar(value="20.0")
        self.status_var = tk.StringVar(value="请选择数据目录并训练模型。")

        self.bundle: ModelBundle | None = None
        self.service: DamageModelService | None = None
        self.current_prediction: np.ndarray | None = None
        self.current_truth: np.ndarray | None = None
        self.current_figure: Figure | None = None
        self.current_condition: Condition | None = None

        # 瞄准优化参数状态
        self.spread_mode_var = tk.StringVar(value="CEP")
        self.cep_var = tk.StringVar(value="5.0")
        self.rep_var = tk.StringVar(value="2.0")
        self.dep_var = tk.StringVar(value="2.0")
        # 相关散布扩展：ρ 相关系数与旋转角 θ（度，留空表示不旋转）
        self.aim_rho_var = tk.StringVar(value="0.0")
        self.aim_theta_var = tk.StringVar(value="")
        self.current_aim_result: AimOptimizationResult | None = None
        self.current_value_field: np.ndarray | None = None

        # 后台训练线程状态
        self._train_thread: threading.Thread | None = None
        self._train_queue: queue.Queue | None = None
        self._cancel_requested = False

        # 耗时统计与 OOD 报告
        self._last_train_time: float | None = None
        self._last_predict_time: float | None = None
        self.last_ood_report: OODReport | None = None

        # 结果区双标签页画布与动画状态
        self.figures: dict[str, Figure | None] = {"triple": None, "full": None, "aim": None}
        self.canvases: dict[str, FigureCanvasTkAgg | None] = {"triple": None, "full": None, "aim": None}
        self._busy_animating = False
        self._anim_phase = 0
        self._syncing_fields = False

        self._apply_window_icon()
        self._configure_styles()
        self._build_layout()
        self._set_data_dir(self.data_dir_var.get())

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

    def _configure_styles(self) -> None:
        self.root.configure(bg=CONFIG.ui_bg)
        style = ttk.Style(self.root)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        default_font = ("Microsoft YaHei", 10)
        title_font = ("Microsoft YaHei", 12, "bold")
        hero_font = ("Microsoft YaHei", 18, "bold")
        small_font = ("Microsoft YaHei", 9)

        style.configure(".", font=default_font)
        style.configure("App.TFrame", background=CONFIG.ui_bg)
        style.configure("Card.TFrame", background=CONFIG.ui_panel_bg, relief="flat")
        style.configure("Soft.TFrame", background=CONFIG.ui_soft_bg, relief="flat")
        style.configure(
            "Title.TLabel",
            background=CONFIG.ui_bg,
            foreground=CONFIG.ui_text,
            font=hero_font,
        )
        style.configure(
            "Subtitle.TLabel",
            background=CONFIG.ui_bg,
            foreground=CONFIG.ui_muted,
            font=small_font,
        )
        style.configure(
            "CardTitle.TLabel",
            background=CONFIG.ui_panel_bg,
            foreground=CONFIG.ui_text,
            font=title_font,
        )
        style.configure(
            "CardText.TLabel",
            background=CONFIG.ui_panel_bg,
            foreground=CONFIG.ui_muted,
            font=small_font,
        )
        style.configure(
            "Section.TLabel",
            background=CONFIG.ui_panel_bg,
            foreground=CONFIG.ui_primary,
            font=("Microsoft YaHei", 10, "bold"),
        )
        style.configure(
            "SoftSection.TLabel",
            background=CONFIG.ui_soft_bg,
            foreground=CONFIG.ui_primary,
            font=("Microsoft YaHei", 10, "bold"),
        )
        style.configure(
            "FieldLabel.TLabel",
            background=CONFIG.ui_panel_bg,
            foreground=CONFIG.ui_muted,
            font=("Microsoft YaHei", 9),
        )
        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor=CONFIG.ui_soft_bg,
            background=CONFIG.ui_accent,
            bordercolor=CONFIG.ui_border,
            lightcolor=CONFIG.ui_accent,
            darkcolor=CONFIG.ui_accent,
            thickness=8,
        )
        style.configure(
            "App.TNotebook",
            background=CONFIG.ui_bg,
            borderwidth=0,
            tabmargins=(0, 0, 0, 6),
        )
        style.configure(
            "App.TNotebook.Tab",
            font=("Microsoft YaHei", 9),
            padding=(18, 6),
            background=CONFIG.ui_bg,
            foreground=CONFIG.ui_muted,
            borderwidth=0,
        )
        style.map(
            "App.TNotebook.Tab",
            background=[("selected", CONFIG.ui_primary)],
            foreground=[("selected", "#FFFFFF")],
        )
        style.configure(
            "Accent.TButton",
            font=("Microsoft YaHei", 10),
            padding=(10, 10),
            background=CONFIG.ui_primary,
            foreground="#FFFFFF",
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", CONFIG.ui_primary_dark),
                ("pressed", CONFIG.ui_primary_dark),
                ("disabled", "#9FAFD6"),
            ],
            foreground=[("disabled", "#F1F4FA"), ("!disabled", "#FFFFFF")],
        )
        style.configure(
            "Ghost.TButton",
            font=("Microsoft YaHei", 9),
            padding=(10, 7),
            background=CONFIG.ui_panel_bg,
            foreground=CONFIG.ui_primary,
            bordercolor=CONFIG.ui_primary,
            lightcolor=CONFIG.ui_panel_bg,
            darkcolor=CONFIG.ui_panel_bg,
            borderwidth=1,
            focusthickness=0,
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#EFF4FB"), ("pressed", "#E4ECF7")],
        )
        style.configure(
            "Primary.TButton",
            font=("Microsoft YaHei", 10),
            padding=(10, 9),
            background=CONFIG.ui_primary,
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", CONFIG.ui_primary_dark), ("pressed", CONFIG.ui_primary_dark)],
            foreground=[("disabled", "#dfe7ed"), ("!disabled", "#ffffff")],
        )
        style.configure(
            "Secondary.TButton",
            font=("Microsoft YaHei", 10),
            padding=(10, 8),
            background=CONFIG.ui_soft_bg,
            foreground=CONFIG.ui_text,
            bordercolor=CONFIG.ui_border,
            lightcolor=CONFIG.ui_soft_bg,
            darkcolor=CONFIG.ui_soft_bg,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#e6edf2"), ("pressed", "#dce5eb")],
        )
        style.configure(
            "App.TEntry",
            fieldbackground="#FFFFFF",
            foreground=CONFIG.ui_text,
            bordercolor=CONFIG.ui_border,
            lightcolor=CONFIG.ui_border,
            darkcolor=CONFIG.ui_border,
            padding=6,
        )
        style.configure(
            "App.TSpinbox",
            fieldbackground="#FFFFFF",
            foreground=CONFIG.ui_text,
            bordercolor=CONFIG.ui_border,
            lightcolor=CONFIG.ui_border,
            darkcolor=CONFIG.ui_border,
            arrowcolor=CONFIG.ui_primary,
            arrowsize=12,
            padding=6,
        )
        style.configure(
            "App.TCombobox",
            fieldbackground="#FFFFFF",
            foreground=CONFIG.ui_text,
            bordercolor=CONFIG.ui_border,
            lightcolor=CONFIG.ui_border,
            darkcolor=CONFIG.ui_border,
            padding=5,
        )
        style.configure(
            "Line.TSeparator",
            background=CONFIG.ui_border,
        )

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_header()

        body = ttk.Frame(self.root, style="App.TFrame", padding=(18, 14, 18, 16))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=0, minsize=320)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_left_panel(body)
        self._build_right_panel(body)

        self._update_key_metrics(None, None)
        self._update_summary_card(None)
        self._update_detail_card()
        self._update_advice_card(None, None, "")

    # ---------- 顶部标题栏 ----------

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=CONFIG.ui_header_bg)
        header.grid(row=0, column=0, sticky="ew")
        inner = tk.Frame(header, bg=CONFIG.ui_header_bg)
        inner.pack(fill="x", padx=20, pady=(7, 7))

        icon = tk.Canvas(
            inner, width=28, height=28, bg=CONFIG.ui_header_bg, highlightthickness=0
        )
        icon.pack(side="left", padx=(0, 10))
        self._draw_header_icon(icon)

        # 顶部保持纯净：模型类型与指标信息在底部卡片中已有体现，此处只保留标题
        tk.Label(
            inner,
            text="基于数据驱动的毁伤效能快速评估",
            bg=CONFIG.ui_header_bg,
            fg=CONFIG.ui_header_fg,
            font=("Microsoft YaHei", 13),
        ).pack(side="left")

    @staticmethod
    def _draw_header_icon(canvas: tk.Canvas) -> None:
        """扁平应用图标：高亮圆角方块 + 导弹剪影 + 数据点。"""
        rounded_rect(canvas, 1, 1, 27, 27, 7, fill="#3B5BC0", outline="")
        canvas.create_polygon(14, 5, 17.5, 13, 10.5, 13, fill="#FFFFFF", outline="")
        canvas.create_rectangle(12.5, 13, 15.5, 19, fill="#FFFFFF", outline="")
        for cx, cy in ((9, 22), (14, 23.5), (19, 22)):
            canvas.create_oval(cx - 1.4, cy - 1.4, cx + 1.4, cy + 1.4, fill="#B6C3E4", outline="")

    # ---------- 圆角卡片工厂 ----------

    def _make_card(
        self,
        parent: tk.Misc,
        title: str | None = None,
        soft: bool = False,
    ) -> tuple[tk.Canvas, tk.Frame, str]:
        """创建圆角+微阴影的信息卡片（Canvas 绘制），返回 (外框, 内容容器, 背景色)。"""
        bg = CONFIG.ui_panel_bg
        pad_x, pad_y = 16, 13
        holder = tk.Canvas(parent, bg=CONFIG.ui_bg, highlightthickness=0, bd=0)
        content = tk.Frame(holder, bg=bg)
        window_id = holder.create_window(pad_x, pad_y, window=content, anchor="nw")

        def redraw(_event: object = None) -> None:
            width = holder.winfo_width()
            if width <= 1:
                return
            holder.itemconfigure(window_id, width=max(width - 2 * pad_x - 3, 10))
            wanted = content.winfo_reqheight() + 2 * pad_y + 3
            if int(holder.cget("height")) != wanted:
                holder.configure(height=wanted)
            height = max(holder.winfo_height(), wanted)
            holder.delete("cardbg")
            # 微弱阴影：向右下偏移 2px 的浅灰圆角矩形
            rounded_rect(holder, 3, 4, width - 1, height - 1, 9,
                         fill=CONFIG.ui_shadow, outline="", tags="cardbg")
            rounded_rect(holder, 0, 0, width - 3, height - 4, 8,
                         fill=bg, outline="", tags="cardbg")
            holder.tag_lower("cardbg")

        holder.bind("<Configure>", redraw)
        content.bind("<Configure>", redraw)
        if title:
            # 统一对齐基准：卡片标题一律加粗、靠左上
            tk.Label(
                content, text=title, bg=bg, fg=CONFIG.ui_muted,
                font=("Microsoft YaHei", 9, "bold"),
            ).pack(anchor="nw", pady=(0, 8))
        return holder, content, bg

    # ---------- 左侧：参数配置（可滚动） ----------

    def _build_left_panel(self, body: ttk.Frame) -> None:
        # Canvas + Scrollbar 实现左侧可滚动容器
        container = ttk.Frame(body, style="App.TFrame")
        container.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=0)

        canvas = tk.Canvas(container, highlightthickness=0, bg=CONFIG.ui_bg)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        # 内部 Frame 承载所有卡片
        left = ttk.Frame(canvas, style="App.TFrame")
        left.columnconfigure(0, weight=1)
        self._left_canvas_window = canvas.create_window((0, 0), window=left, anchor="nw")

        # 内容变化时更新 scrollregion
        def _on_left_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 确保内部 frame 宽度与 canvas 一致（水平不滚动）
            canvas.itemconfig(self._left_canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_left_configure)

        # 鼠标滚轮支持
        def _on_mousewheel(event):
            # Windows: event.delta 通常为 ±120 的倍数
            canvas.yview_scroll(int(-event.delta / 120), "units")

        def _on_enter(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _on_leave(event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _on_enter)
        canvas.bind("<Leave>", _on_leave)

        self._left_canvas = canvas

        card, box, bg = self._make_card(left, "模型操作")
        card.grid(row=0, column=0, sticky="ew")
        tk.Label(box, text="数据目录", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9)).pack(anchor="w")
        # 路径选择器紧凑化：输入框与浏览按钮横向并排，节省纵向空间
        dir_row = tk.Frame(box, bg=bg)
        dir_row.pack(fill="x", pady=(4, 0))
        ttk.Entry(dir_row, textvariable=self.data_dir_var, style="App.TEntry").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(
            dir_row, text="浏览…", command=self.on_browse_data,
            style="Ghost.TButton", width=6,
        ).pack(side="left", padx=(6, 0))
        tk.Label(box, text="毁伤等级", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(12, 0))
        ttk.Combobox(
            box,
            textvariable=self.level_var,
            values=["F", "M", "P"],
            state="readonly",
            style="App.TCombobox",
        ).pack(fill="x", pady=(4, 0))

        # 模型类型：RBF 插值场 / POD-RBF 降阶模型
        tk.Label(box, text="模型类型", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(12, 0))
        ttk.Combobox(
            box,
            textvariable=self.model_type_var,
            values=[label for label, _ in MODEL_TYPE_CHOICES],
            state="readonly",
            style="App.TCombobox",
        ).pack(fill="x", pady=(4, 0))

        # POD 主成分数（仅 POD-RBF 生效）
        pod_row = tk.Frame(box, bg=bg)
        pod_row.pack(fill="x", pady=(8, 0))
        tk.Label(pod_row, text="POD 主成分数 K", bg=bg, fg=CONFIG.ui_muted,
                 font=("Microsoft YaHei", 9)).pack(side="left")
        ttk.Spinbox(
            pod_row, textvariable=self.pod_components_var,
            from_=2, to=200, increment=1, width=6,
            style="App.TSpinbox",
        ).pack(side="right")

        # 验证方式：随机留出 / 整层留出 / 角落留出
        tk.Label(box, text="验证方式", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(12, 0))
        ttk.Combobox(
            box,
            textvariable=self.validation_var,
            values=[label for label, _ in VALIDATION_CHOICES],
            state="readonly",
            style="App.TCombobox",
        ).pack(fill="x", pady=(4, 0))

        # 模型操作为低频配置操作，统一使用次要按钮样式（白底蓝边 / 浅灰底），
        # 视觉权重让位于高频核心操作"开始预测"（Accent 深蓝高亮）。
        buttons = tk.Frame(box, bg=bg)
        buttons.pack(fill="x", pady=(16, 0))
        buttons.columnconfigure((0, 1), weight=1)
        self.train_button = ttk.Button(buttons, text="训练模型", command=self.on_train, style="Ghost.TButton")
        self.train_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.cancel_button = ttk.Button(
            buttons, text="取消训练", command=self.on_cancel_training,
            style="Secondary.TButton", state="disabled",
        )
        self.cancel_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.save_button = ttk.Button(buttons, text="保存模型", command=self.on_save_model, style="Secondary.TButton")
        self.save_button.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(10, 0))
        self.load_button = ttk.Button(buttons, text="加载模型...", command=self.on_load_model, style="Secondary.TButton")
        self.load_button.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(10, 0))

        card2, box2, bg2 = self._make_card(left, "工况输入")
        card2.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        for icon, label, variable, key in (
            ("⛰", "高度 h (m)", self.h_var, "h"),
            ("➤", "速度 v (m/s)", self.v_var, "v"),
            ("∠", "角度 deg (°)", self.deg_var, "deg"),
        ):
            lo, hi, step = self.CONDITION_LIMITS[key]
            self._build_condition_field(box2, bg2, icon, label, variable, lo, hi, step)

        self.predict_button = ttk.Button(box2, text="开始预测", command=self.on_predict, style="Accent.TButton")
        self.predict_button.pack(fill="x", pady=(14, 0))
        export_row = tk.Frame(box2, bg=bg2)
        export_row.pack(fill="x", pady=(10, 0))
        export_row.columnconfigure((0, 1), weight=1)
        ttk.Button(export_row, text="导出 CSV", command=self.on_export_csv, style="Ghost.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(export_row, text="导出 PNG", command=self.on_export_png, style="Ghost.TButton").grid(row=0, column=1, sticky="ew", padx=(6, 0))

        # 瞄准优化卡片
        card3, box3, bg3 = self._make_card(left, "瞄准优化")
        card3.grid(row=2, column=0, sticky="ew", pady=(14, 0))

        tk.Label(box3, text="散布模式", bg=bg3, fg=CONFIG.ui_muted,
                 font=("Microsoft YaHei", 9)).pack(anchor="w")
        mode_row = tk.Frame(box3, bg=bg3)
        mode_row.pack(fill="x", pady=(4, 0))

        def _on_spread_mode_change(*_args):
            mode = self.spread_mode_var.get()
            if mode == "CEP":
                self._aim_cep_frame.pack(fill="x", pady=(10, 0))
                self._aim_rep_dep_frame.pack_forget()
            else:
                self._aim_rep_dep_frame.pack(fill="x", pady=(10, 0))
                self._aim_cep_frame.pack_forget()

        ttk.Combobox(
            mode_row, textvariable=self.spread_mode_var,
            values=["CEP", "REP_DEP"], state="readonly",
            style="App.TCombobox",
        ).pack(fill="x")
        self.spread_mode_var.trace_add("write", _on_spread_mode_change)

        # CEP 输入
        self._aim_cep_frame = tk.Frame(box3, bg=bg3)
        self._aim_cep_frame.pack(fill="x", pady=(10, 0))
        tk.Label(self._aim_cep_frame, text="CEP (m)", bg=bg3, fg=CONFIG.ui_muted,
                 font=("Microsoft YaHei", 9)).pack(anchor="w")
        ttk.Entry(self._aim_cep_frame, textvariable=self.cep_var,
                  style="App.TEntry").pack(fill="x", pady=(4, 0))

        # REP/DEP 输入（含相关散布扩展：ρ 与旋转角 θ）
        self._aim_rep_dep_frame = tk.Frame(box3, bg=bg3)
        tk.Label(self._aim_rep_dep_frame, text="REP (m)", bg=bg3, fg=CONFIG.ui_muted,
                 font=("Microsoft YaHei", 9)).pack(anchor="w")
        ttk.Entry(self._aim_rep_dep_frame, textvariable=self.rep_var,
                  style="App.TEntry").pack(fill="x", pady=(4, 0))
        tk.Label(self._aim_rep_dep_frame, text="DEP (m)", bg=bg3, fg=CONFIG.ui_muted,
                 font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(8, 0))
        ttk.Entry(self._aim_rep_dep_frame, textvariable=self.dep_var,
                  style="App.TEntry").pack(fill="x", pady=(4, 0))
        # ρ 与 θ 并排输入：ρ ∈ (−1,1)；θ 留空 = 轴对齐（给出时 REP 沿 θ 主轴旋转）
        corr_row = tk.Frame(self._aim_rep_dep_frame, bg=bg3)
        corr_row.pack(fill="x", pady=(8, 0))
        corr_left = tk.Frame(corr_row, bg=bg3)
        corr_left.pack(side="left", fill="x", expand=True)
        tk.Label(corr_left, text="相关系数 ρ", bg=bg3, fg=CONFIG.ui_muted,
                 font=("Microsoft YaHei", 9)).pack(anchor="w")
        ttk.Entry(corr_left, textvariable=self.aim_rho_var,
                  style="App.TEntry").pack(fill="x", pady=(4, 0))
        corr_right = tk.Frame(corr_row, bg=bg3)
        corr_right.pack(side="left", fill="x", expand=True, padx=(8, 0))
        tk.Label(corr_right, text="旋转角 θ (°, 可空)", bg=bg3, fg=CONFIG.ui_muted,
                 font=("Microsoft YaHei", 9)).pack(anchor="w")
        ttk.Entry(corr_right, textvariable=self.aim_theta_var,
                  style="App.TEntry").pack(fill="x", pady=(4, 0))

        self.optimize_button = ttk.Button(
            box3, text="计算最佳瞄准点", command=self.on_optimize_aim,
            style="Accent.TButton",
        )
        self.optimize_button.pack(fill="x", pady=(14, 0))

    def _build_condition_field(
        self,
        parent: tk.Frame,
        bg: str,
        icon: str,
        label: str,
        variable: tk.StringVar,
        from_: float,
        to: float,
        increment: float,
    ) -> None:
        """带小图标的现代化输入字段（Spinbox 微调器，限制数值范围防误输入）。"""
        field = tk.Frame(parent, bg=bg)
        field.pack(fill="x", pady=(0, 12))
        head = tk.Frame(field, bg=bg)
        head.pack(fill="x")
        tk.Label(head, text=icon, bg=bg, fg=CONFIG.ui_primary, font=("Microsoft YaHei", 10)).pack(side="left")
        tk.Label(head, text=f" {label}", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9)).pack(side="left")
        ttk.Spinbox(
            field,
            textvariable=variable,
            from_=from_,
            to=to,
            increment=increment,
            style="App.TSpinbox",
            font=("Microsoft YaHei", 11),
        ).pack(fill="x", pady=(5, 0))

    # ---------- 右侧：核心展示区 ----------

    def _build_right_panel(self, body: ttk.Frame) -> None:
        right = ttk.Frame(body, style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        tk.Label(
            right,
            text="流程：选择数据目录与等级 → 选择模型类型与验证方式 → 训练或加载模型 → 输入工况开始预测 → 查看热力图、指标与可信度 → 导出结果",
            bg=CONFIG.ui_bg,
            fg=CONFIG.ui_muted,
            font=("Microsoft YaHei", 9),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.result_tabs = ttk.Notebook(right, style="App.TNotebook")
        self.result_tabs.grid(row=1, column=0, sticky="nsew")
        self.tab_frames: dict[str, tk.Frame] = {}
        for key, label in (("triple", "对比三联图"), ("full", "全视图预测图"), ("aim", "瞄准优化")):
            frame = tk.Frame(self.result_tabs, bg=CONFIG.ui_bg)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            self.result_tabs.add(frame, text=f"  {label}  ")
            self.tab_frames[key] = frame
            tk.Label(
                frame,
                text="训练模型并执行预测后，此处显示毁伤热力图",
                bg=CONFIG.ui_bg,
                fg=CONFIG.ui_muted,
                font=("Microsoft YaHei", 10),
            ).grid(row=0, column=0)
        # 画布在隐藏标签页里创建时拿不到真实尺寸，切换显示会残留错误布局
        # （单张大图向右偏移）；切换标签页时按当前尺寸强制重排并重绘。
        self.result_tabs.bind("<<NotebookTabChanged>>", self._on_result_tab_changed)

        report = ttk.Frame(right, style="App.TFrame")
        report.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        report.columnconfigure((0, 1, 2, 3, 4), weight=1, uniform="report")

        # 运行状态卡（与指标卡并排的微型仪表盘）：核心状态字居中放大突出
        card0, box0, bg0 = self._make_card(report, "运行状态")
        card0.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        state_row = tk.Frame(box0, bg=bg0)
        state_row.pack(pady=(2, 0))
        self.status_dot = tk.Label(state_row, text="●", bg=bg0, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 11))
        self.status_dot.pack(side="left", padx=(0, 6))
        self.state_label = tk.Label(state_row, text="就绪", bg=bg0, fg=CONFIG.ui_text, font=("Microsoft YaHei", 18, "bold"))
        self.state_label.pack(side="left")
        progress_row = tk.Frame(box0, bg=bg0)
        progress_row.pack(fill="x", pady=(8, 0))
        self.progress_percent = tk.Label(progress_row, text="0%", bg=bg0, fg=CONFIG.ui_primary, font=("Microsoft YaHei", 9), width=4, anchor="e")
        self.progress_percent.pack(side="right", padx=(4, 0))
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            progress_row,
            variable=self.progress_var,
            maximum=100.0,
            style="App.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(side="left", fill="x", expand=True, pady=3)
        self.stage_label = tk.Label(
            box0, text="等待任务...", bg=bg0, fg=CONFIG.ui_muted,
            font=("Microsoft YaHei", 9), anchor="w", justify="left",
        )
        self.stage_label.pack(anchor="w", pady=(4, 0), fill="x")
        bind_autowrap(self.stage_label)
        self.status_message = tk.Label(
            box0, text="请选择数据目录并训练模型。", bg=bg0, fg=CONFIG.ui_muted,
            font=("Microsoft YaHei", 9), anchor="w", justify="left",
        )
        self.status_message.pack(anchor="w", pady=(4, 0), fill="x")
        bind_autowrap(self.status_message)

        # 关键指标卡：核心大字指标在卡片正中放大突出
        card, box, bg = self._make_card(report, "关键指标报告")
        card.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        self.p95_value = tk.Label(box, text="--", bg=bg, fg=CONFIG.ui_text, font=("Microsoft YaHei", 22, "bold"))
        self.p95_value.pack(pady=(2, 0))
        self.p95_status = tk.Label(box, text="P95 混合误差", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9))
        self.p95_status.pack()
        self.meanre_value = tk.Label(box, text="--", bg=bg, fg=CONFIG.ui_text, font=("Microsoft YaHei", 14, "bold"))
        self.meanre_value.pack(pady=(10, 0))
        self.meanre_status = tk.Label(box, text="平均相对误差", bg=bg, fg=CONFIG.ui_muted, font=("Microsoft YaHei", 9))
        self.meanre_status.pack()

        card2, box2, bg2 = self._make_card(report, "输入配置摘要")
        card2.grid(row=0, column=2, sticky="nsew", padx=(0, 10))
        self.summary_label = tk.Label(
            box2, text="--", bg=bg2, fg=CONFIG.ui_text, font=("Microsoft YaHei", 9),
            justify="left", anchor="nw",
        )
        self.summary_label.pack(anchor="w", fill="both", expand=True)
        bind_autowrap(self.summary_label)

        card3, box3, bg3 = self._make_card(report, "模型细节")
        card3.grid(row=0, column=3, sticky="nsew", padx=(0, 10))
        self.detail_label = tk.Label(
            box3, text="--", bg=bg3, fg=CONFIG.ui_text, font=("Microsoft YaHei", 9),
            justify="left", anchor="nw",
        )
        self.detail_label.pack(anchor="w", fill="both", expand=True)
        bind_autowrap(self.detail_label)

        card4, box4, bg4 = self._make_card(report, "建议")
        card4.grid(row=0, column=4, sticky="nsew")
        self.advice_label = tk.Label(
            box4, text="--", bg=bg4, fg=CONFIG.ui_text, font=("Microsoft YaHei", 9),
            justify="left", anchor="nw",
        )
        self.advice_label.pack(anchor="w", fill="both", expand=True)
        bind_autowrap(self.advice_label)

    def _selected_result_tab_key(self) -> str:
        """返回当前选中的结果标签页 key（triple / full / aim）。"""
        selected = self.result_tabs.select()
        for key, frame in self.tab_frames.items():
            if selected == str(frame):
                return key
        return "triple"

    def _on_result_tab_changed(self, _event: object = None) -> None:
        """切换结果标签页时按当前真实尺寸重绘画布，修复隐藏期创建导致的偏移。"""
        which = self._selected_result_tab_key()
        canvas = self.canvases.get(which)
        if canvas is None:
            return
        self.root.update_idletasks()
        widget = canvas.get_tk_widget()
        width, height = widget.winfo_width(), widget.winfo_height()
        if width > 1 and height > 1:
            # 与 FigureCanvasTkAgg.resize 相同的逻辑：把画布尺寸同步给 Figure
            dpi = canvas.figure.dpi
            canvas.figure.set_size_inches(width / dpi, height / dpi, forward=False)
        canvas.draw_idle()

    def _set_status(self, text: str, kind: str = "info") -> None:
        self.status_var.set(text)
        if hasattr(self, "status_message"):
            self.status_message.configure(text=text)
        colors = {
            "info": CONFIG.ui_muted,
            "busy": CONFIG.ui_busy,
            "ok": CONFIG.ui_success,
            "error": CONFIG.ui_danger,
        }
        states = {"info": "就绪", "busy": "运行中", "ok": "已完成", "error": "出错"}
        if hasattr(self, "status_dot"):
            self.status_dot.configure(fg=colors.get(kind, CONFIG.ui_muted))
        if hasattr(self, "state_label"):
            self.state_label.configure(
                text=states.get(kind, "就绪"), fg=colors.get(kind, CONFIG.ui_text)
            )
        self._set_animating(kind == "busy")
        self.root.update_idletasks()

    def _set_animating(self, active: bool) -> None:
        """运行状态点的呼吸灯效果：busy 时启动，其余状态自动停止。"""
        if active and not self._busy_animating:
            self._busy_animating = True
            self._animate_status_dot()
        elif not active:
            self._busy_animating = False

    def _animate_status_dot(self) -> None:
        if not self._busy_animating:
            return
        pulse_colors = ("#e8b45a", CONFIG.ui_busy, "#c98f2f", CONFIG.ui_busy)
        self._anim_phase = (self._anim_phase + 1) % len(pulse_colors)
        try:
            self.status_dot.configure(fg=pulse_colors[self._anim_phase])
            self.root.after(300, self._animate_status_dot)
        except tk.TclError:
            self._busy_animating = False

    def _set_progress(self, percent: float, stage: str) -> None:
        self.progress_var.set(percent)
        self.progress_percent.configure(text=f"{percent:.0f}%")
        self.stage_label.configure(text=stage)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for name in ("train_button", "predict_button", "save_button", "load_button", "optimize_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state=state)
        if hasattr(self, "cancel_button"):
            self.cancel_button.configure(state="normal" if busy else "disabled")

    def _set_data_dir(self, data_dir: str, config: Config | None = None) -> None:
        self.data_dir_var.set(data_dir)
        self.service = DamageModelService(DamageDataManager(data_dir), config=config)

    def _active_config(self) -> Config:
        """当前模型的训练配置；无模型时回退到服务或应用默认配置。"""
        if self.bundle is not None:
            return self.bundle.resolved_config()
        if self.service is not None:
            return self.service.config
        return CONFIG

    def _current_condition(self) -> Condition:
        try:
            values = {
                "h": float(self.h_var.get()),
                "v": float(self.v_var.get()),
                "deg": float(self.deg_var.get()),
            }
        except ValueError as exc:
            raise ValueError("h、v、deg 必须是数字") from exc

        for name, value in values.items():
            lo, hi, _step = self.CONDITION_LIMITS[name]
            if not (lo <= value <= hi):
                raise ValueError(f"{name} 超出合法范围 [{lo:g}, {hi:g}]，当前为 {value:g}")
        return Condition(**values)

    def _selected_model_type(self) -> str:
        return choice_value(MODEL_TYPE_CHOICES, self.model_type_var.get(), "rbf")

    def _selected_validation_mode(self) -> str:
        return choice_value(VALIDATION_CHOICES, self.validation_var.get(), "random")

    def _draw_figure(self, figure: Figure, which: str = "triple") -> None:
        self.figures[which] = figure
        self.current_figure = figure
        frame = self.tab_frames[which]
        old_canvas = self.canvases.get(which)
        if old_canvas is not None:
            old_canvas.get_tk_widget().destroy()
        for child in frame.winfo_children():
            if isinstance(child, tk.Label):
                child.destroy()
        canvas = FigureCanvasTkAgg(figure, master=frame)
        widget = canvas.get_tk_widget()
        widget.configure(bg=CONFIG.ui_bg, highlightthickness=0, bd=0)
        widget.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        canvas.draw()
        self.canvases[which] = canvas

    # ---------- 报告卡片更新 ----------

    def _update_key_metrics(
        self, mean_re: float | None, p95_hybrid: float | None
    ) -> None:
        target = self._active_config().relative_error_target
        value, value_color, status, status_color = metric_display(
            p95_hybrid, "P95 混合误差", target
        )
        self.p95_value.configure(text=value, fg=value_color)
        self.p95_status.configure(text=status, fg=status_color)
        value, value_color, status, status_color = metric_display(
            mean_re, "平均相对误差", target
        )
        self.meanre_value.configure(text=value, fg=value_color)
        self.meanre_status.configure(text=status, fg=status_color)

    @staticmethod
    def _short_path(path: str, limit: int = 36) -> str:
        return path if len(path) <= limit else "…" + path[-(limit - 1):]

    def _update_summary_card(self, condition: Condition | None) -> None:
        lines = [
            f"数据路径: {self._short_path(self.data_dir_var.get())}",
            f"毁伤等级: {self.level_var.get()}",
            f"模型类型: {self.model_type_var.get()}",
            f"验证方式: {self.validation_var.get()}",
        ]
        if condition is not None:
            lines.append(
                f"工况: h={condition.h:g} m, v={condition.v:g} m/s, deg={condition.deg:g}°"
            )
        else:
            lines.append("工况: 尚未预测")
        self.summary_label.configure(text="\n".join(lines))

    def _update_detail_card(self) -> None:
        if self.bundle is None:
            self.detail_label.configure(text="尚未训练或加载模型。")
            return
        bundle = self.bundle
        config = bundle.resolved_config()
        model = bundle.model
        lines = [
            f"模型: {getattr(model, 'model_name', type(model).__name__)}",
            f"训练集: {len(bundle.train_conditions)} 工况",
            f"测试集: {len(bundle.test_conditions)} 工况",
        ]
        if getattr(model, "explained_variance", 0.0):
            lines.append(
                f"POD 累计解释方差: {model.explained_variance:.2%} (K={model.n_components_used})"
            )
        lines.append(f"验证方式: {VALIDATION_LABELS.get(bundle.validation_mode, bundle.validation_mode)}")
        lines.append(f"RBF 核: {config.rbf_kernel}")
        lines.append(f"质心对齐: {'开启' if config.align_patterns else '关闭'}")
        lines.append(f"降噪: 双边滤波 σs={config.denoise_sigma_spatial:g}")
        lines.append(
            f"评估口径: Raw + Smoothed (σ={config.eval_smoothing_sigma:g}) 双口径"
        )
        if self._last_train_time is not None:
            lines.append(f"训练耗时: {self._last_train_time:.1f} s")
        if self._last_predict_time is not None:
            lines.append(f"预测耗时: {self._last_predict_time * 1000:.0f} ms")
        if self.last_ood_report is not None:
            report = self.last_ood_report
            lines.append(
                f"模型可信度: {report.level_label} (最近工况距离 {report.distance:.3f})"
            )
            if report.in_hull is False:
                lines.append("几何判定: 训练工况全局凸包外")
            elif getattr(report, "local_support", None) is False:
                lines.append("几何判定: 全局凸包内，但局部训练支撑不足")
        self.detail_label.configure(text="\n".join(lines))

    def _update_advice_card(
        self, mean_re: float | None, p95_hybrid: float | None, scope: str
    ) -> None:
        target = self._active_config().relative_error_target
        if mean_re is None or pd.isna(mean_re):
            text = "训练或预测完成后，此处将给出结论与建议。"
        elif mean_re < target and p95_hybrid is not None and p95_hybrid < target:
            text = (
                f"{scope}核心指标全部达标（目标 <{target:.0%}）。"
                "预测模型符合精度要求，可以用于后续毁伤效能评估，建议导出结果文件存档。"
            )
        elif mean_re < target:
            text = (
                f"{scope}平均精度达标，但 P95 混合误差超标，说明存在局部误差偏大的区域。"
                "建议切换到误差图定位偏差位置，或在该工况附近加密仿真数据后重新训练。"
            )
        else:
            text = (
                f"{scope}核心指标未达标。建议确认数据目录完整、"
                "加密训练工况网格（尤其大角度/低速角落区域）后重新训练。"
            )
        self.advice_label.configure(text=text)

    def on_browse_data(self) -> None:
        selected = filedialog.askdirectory(
            title="选择 data 文件夹",
            initialdir=self.data_dir_var.get(),
        )
        if not selected:
            return
        self._set_data_dir(selected)
        self._set_status(f"已选择数据目录: {selected}")

    # ---------- 训练（后台线程） ----------

    def on_train(self) -> None:
        try:
            if self.service is None:
                raise RuntimeError("数据服务未初始化")
            if self._train_thread is not None and self._train_thread.is_alive():
                raise RuntimeError("训练正在进行中，请先取消或等待完成")

            level = self.level_var.get().strip().upper()
            model_type = self._selected_model_type()
            validation_mode = self._selected_validation_mode()
            try:
                pod_components = int(self.pod_components_var.get())
            except ValueError as exc:
                raise ValueError("POD 主成分数必须是整数") from exc
            if pod_components < 2:
                raise ValueError("POD 主成分数至少为 2")

            self._cancel_requested = False
            self._set_busy(True)
            self._set_status(
                f"正在后台训练等级 {level} 模型（{self.model_type_var.get()}，"
                f"{self.validation_var.get()}），界面仍可操作，请稍候...",
                kind="busy",
            )

            train_queue: queue.Queue = queue.Queue()

            def report_progress(done: int, total: int, stage: str) -> None:
                train_queue.put(("progress", done, total, stage))

            def worker() -> None:
                try:
                    bundle = self.service.train_bundle(
                        level,
                        validation_mode=validation_mode,
                        model_type=model_type,
                        pod_n_components=pod_components,
                        progress=report_progress,
                        cancel_check=lambda: self._cancel_requested,
                    )
                    train_queue.put(("done", bundle))
                except Exception as exc:  # noqa: BLE001 —— 线程边界统一上报
                    train_queue.put(("error", exc))

            self._train_queue = train_queue
            self._train_thread = threading.Thread(target=worker, daemon=True)
            self._train_thread.start()
            self._poll_training()
        except Exception as exc:
            self._set_busy(False)
            self._handle_error("训练失败", exc)

    def on_cancel_training(self) -> None:
        if self._train_thread is None or not self._train_thread.is_alive():
            return
        self._cancel_requested = True
        self._set_status("正在取消训练...", kind="busy")

    def _poll_training(self) -> None:
        """主线程轮询训练队列：进度 / 完成 / 失败 / 取消。"""
        train_queue = self._train_queue
        if train_queue is None:
            return
        finished = False
        try:
            while True:
                message = train_queue.get_nowait()
                kind = message[0]
                if kind == "progress":
                    _kind, done, total, stage = message
                    percent = done / total * 100.0 if total > 0 else 0.0
                    self._set_progress(percent, stage)
                elif kind == "done":
                    self._finish_training(message[1])
                    finished = True
                elif kind == "error":
                    exc = message[1]
                    if isinstance(exc, TrainingCancelled):
                        self._set_status("训练已取消。", kind="info")
                    else:
                        self._handle_error("训练失败", exc)
                    finished = True
        except queue.Empty:
            pass

        if finished:
            self._train_queue = None
            self._train_thread = None
            self._set_busy(False)
            self._set_progress(0.0, "等待任务...")
            return
        self.root.after(80, self._poll_training)

    def _finish_training(self, bundle: ModelBundle) -> None:
        self.bundle = bundle
        self._last_train_time = bundle.train_time_seconds
        self.last_ood_report = None
        self._set_progress(100.0, "训练与评估完成")

        accuracy_path = app_base_dir() / f"gui_accuracy_report_{bundle.level}.csv"
        condition_path = app_base_dir() / f"gui_condition_report_{bundle.level}.csv"
        bundle.accuracy_report.to_csv(accuracy_path, index=False, encoding="utf-8-sig")
        bundle.condition_report.to_csv(condition_path, index=False, encoding="utf-8-sig")

        mean_re, p95_hybrid = extract_core_metrics(
            bundle.accuracy_report, bundle.resolved_config()
        )
        core_summary = ""
        if mean_re is not None:
            core_summary = (
                f"核心指标: 平均相对误差 {mean_re:.2%}, "
                f"P95混合误差 {p95_hybrid:.2%} "
                f"(目标 <{bundle.resolved_config().relative_error_target:.0%})。"
            )
        self._update_key_metrics(mean_re, p95_hybrid)
        self._update_summary_card(self.current_condition)
        self._update_detail_card()
        self._update_advice_card(mean_re, p95_hybrid, "测试集")

        validation_note = ""
        if bundle.validation_mode != "random":
            validation_note = (
                f" 验证方式: {VALIDATION_LABELS.get(bundle.validation_mode, bundle.validation_mode)}，"
                "指标来自未见工况的折外预测。"
            )
        self._set_status(
            f"训练完成: {bundle.level}（{getattr(bundle.model, 'model_name', 'RBF')}，"
            f"耗时 {bundle.train_time_seconds:.1f} s）。{core_summary}{validation_note}"
            f"评估结果已保存为 {accuracy_path.name} 和 {condition_path.name}",
            kind="ok",
        )

    def on_save_model(self) -> None:
        try:
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
            joblib.dump(self.bundle, output_path)
            self._set_status(f"模型已保存: {output_path}", kind="ok")
        except Exception as exc:
            self._handle_error("保存模型失败", exc)

    def on_load_model(self) -> None:
        try:
            model_path = filedialog.askopenfilename(
                title="加载模型",
                filetypes=[("Joblib Model", "*.joblib")],
            )
            if not model_path:
                return
            bundle = joblib.load(model_path)
            if not isinstance(bundle, ModelBundle):
                raise TypeError("模型文件格式不正确")
            self.bundle = bundle
            self.level_var.set(bundle.level)
            self._last_train_time = getattr(bundle, "train_time_seconds", None) or None
            self.last_ood_report = None
            if bundle.data_dir:
                self._set_data_dir(bundle.data_dir, bundle.resolved_config())

            mean_re, p95_hybrid = extract_core_metrics(
                bundle.accuracy_report, bundle.resolved_config()
            )
            self._update_key_metrics(mean_re, p95_hybrid)
            self._update_summary_card(self.current_condition)
            self._update_detail_card()
            self._update_advice_card(mean_re, p95_hybrid, "测试集")
            self._set_status(f"模型已加载: {model_path}", kind="ok")
        except Exception as exc:
            self._handle_error("加载模型失败", exc)

    # ---------- 预测 ----------

    def on_predict(self) -> None:
        try:
            if self.bundle is None:
                raise RuntimeError("请先训练或加载模型")
            if self.service is None:
                raise RuntimeError("数据服务未初始化")

            condition = self._current_condition()
            config = self._active_config()
            self.current_condition = condition
            self._set_status("正在预测并生成热力图...", kind="busy")
            started = time.perf_counter()
            self.current_prediction = self.service.predict_matrix(self.bundle, condition)
            self._last_predict_time = time.perf_counter() - started
            self.current_truth = None

            # OOD / 预测可信度检测
            detector = getattr(self.bundle, "ood_detector", None)
            self.last_ood_report = (
                detector.report(condition) if detector is not None and detector.is_fitted else None
            )

            # 新预测后清空旧瞄准优化结果
            self.current_aim_result = None
            self.current_value_field = None
            self._clear_aim_view()

            record = None
            try:
                record = self.service.data_manager.find_record(self.bundle.level, condition)
            except Exception:
                record = None

            if record is not None:
                self.current_truth = read_damage_matrix(record.path, config)

            triple_figure = render_heatmaps(
                self.current_truth,
                self.current_prediction,
                display_threshold=config.display_threshold,
                config=config,
            )
            self._draw_figure(triple_figure, which="triple")
            self._draw_figure(
                render_full_prediction(self.current_prediction, config), which="full"
            )
            self.result_tabs.select(
                self.tab_frames["triple" if self.current_truth is not None else "full"]
            )
            self.current_figure = triple_figure

            self._update_summary_card(condition)
            self._update_detail_card()

            ood_note = ""
            if self.last_ood_report is not None:
                report = self.last_ood_report
                ood_note = f" 模型可信度: {report.level_label} (d={report.distance:.3f})。"
                if report.in_hull is False:
                    ood_note += " 当前工况位于训练凸包外。"
                elif getattr(report, "local_support", None) is False:
                    ood_note += " 当前工况位于局部数据空洞。"

            if self.current_truth is not None:
                eval_true, eval_pred = evaluation_fields(
                    self.current_truth, self.current_prediction, config
                )
                focus_mask = eval_true.ravel() > config.relative_error_threshold
                if np.any(focus_mask):
                    focus_metrics = metric_row(
                        f"damage_gt_{config.relative_error_threshold:.2f}",
                        eval_true.ravel()[focus_mask],
                        eval_pred.ravel()[focus_mask],
                        config.relative_error_threshold,
                        config,
                    )
                    mean_re = float(focus_metrics["MeanRelativeError"])
                    p95_hybrid = float(focus_metrics["P95HybridError"])
                    self._update_key_metrics(mean_re, p95_hybrid)
                    self._update_advice_card(mean_re, p95_hybrid, "当前工况")
                else:
                    self._update_advice_card(None, None, "")
                    self.advice_label.configure(
                        text="当前工况无 damage>0.05 的毁伤区，相对误差指标不适用。"
                    )
                self._set_status(
                    f"预测完成（耗时 {self._last_predict_time * 1000:.0f} ms），"
                    "并已匹配到真实矩阵，当前显示对比三联图。" + ood_note,
                    kind=(
                        "ok"
                        if self.last_ood_report is None
                        or not self.last_ood_report.is_extrapolation
                        else "info"
                    ),
                )
            else:
                self.advice_label.configure(
                    text="当前工况在 data 中没有真实矩阵，展示全视图预测结果。"
                    "精度可参考关键指标卡片中训练时的测试集指标。"
                )
                self._set_status(
                    f"预测完成（耗时 {self._last_predict_time * 1000:.0f} ms），"
                    "当前工况没有真实矩阵，显示全视图预测热力图。" + ood_note,
                    kind=(
                        "ok"
                        if self.last_ood_report is None
                        or not self.last_ood_report.is_extrapolation
                        else "info"
                    ),
                )

            # 距离低可信、凸包外或局部空洞均给出显著提示
            if (
                self.last_ood_report is not None
                and self.last_ood_report.is_extrapolation
            ):
                geometry_reason = "训练数据覆盖边缘"
                if self.last_ood_report.in_hull is False:
                    geometry_reason = "训练工况全局凸包之外"
                elif getattr(self.last_ood_report, "local_support", None) is False:
                    geometry_reason = "全局凸包内的局部数据空洞"
                self.advice_label.configure(
                    text=(
                        f"⚠ 当前工况位于{geometry_reason}（最近训练工况距离 "
                        f"{self.last_ood_report.distance:.3f}），该预测可能存在较大的外推误差，"
                        "建议在该区域补充仿真数据后重新训练。"
                    )
                )
        except Exception as exc:
            self._handle_error("预测失败", exc)

    def on_export_csv(self) -> None:
        try:
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

            x_axis, y_axis = coordinate_axes(
                self.current_prediction.shape, self._active_config()
            )
            frame = pd.DataFrame(self.current_prediction, index=y_axis, columns=x_axis)
            frame.index.name = "y"
            frame.to_csv(output_path, encoding="utf-8-sig")
            self._set_status(f"预测矩阵已导出: {output_path}", kind="ok")
        except Exception as exc:
            self._handle_error("导出 CSV 失败", exc)

    def on_export_png(self) -> None:
        try:
            which = self._selected_result_tab_key()
            figure = self.figures.get(which) or self.current_figure
            if figure is None:
                raise RuntimeError("请先生成热力图")
            self.current_figure = figure
            output_path = filedialog.asksaveasfilename(
                title="导出热力图 PNG",
                defaultextension=".png",
                filetypes=[("PNG Image", "*.png")],
                initialfile="damage_heatmap.png",
            )
            if not output_path:
                return
            self.current_figure.savefig(
                output_path,
                dpi=self._active_config().export_dpi,
                bbox_inches="tight",
            )
            self._set_status(f"热力图已导出: {output_path}", kind="ok")
        except Exception as exc:
            self._handle_error("导出 PNG 失败", exc)

    # ---------- 瞄准优化 ----------

    def _clear_aim_view(self) -> None:
        """清空瞄准优化标签页内容。"""
        frame = self.tab_frames.get("aim")
        if frame is None:
            return
        old_canvas = self.canvases.get("aim")
        if old_canvas is not None:
            old_canvas.get_tk_widget().destroy()
            self.canvases["aim"] = None
        for child in frame.winfo_children():
            child.destroy()
        self.figures["aim"] = None
        tk.Label(
            frame, text="预测完成后，输入散布参数并点击「计算最佳瞄准点」",
            bg=CONFIG.ui_bg, fg=CONFIG.ui_muted,
            font=("Microsoft YaHei", 10),
        ).grid(row=0, column=0)

    def on_optimize_aim(self) -> None:
        """计算最佳瞄准点。"""
        try:
            if self.current_prediction is None:
                raise RuntimeError("请先执行毁伤场预测")

            x_axis, y_axis = coordinate_axes(
                self.current_prediction.shape, self._active_config()
            )

            mode = self.spread_mode_var.get()
            if mode == "CEP":
                cep_val = float(self.cep_var.get())
                if cep_val < 0:
                    raise ValueError("CEP 必须非负")
                result = optimize_aim(
                    self.current_prediction, x_axis, y_axis,
                    spread_mode="CEP", cep=cep_val, reliability=1.0,
                )
            else:
                rep_val = float(self.rep_var.get())
                dep_val = float(self.dep_var.get())
                rho_val = float(self.aim_rho_var.get())
                if not (-1.0 < rho_val < 1.0):
                    raise ValueError("相关系数 ρ 必须在 (−1, 1) 开区间内")
                theta_text = self.aim_theta_var.get().strip()
                theta_deg = float(theta_text) if theta_text else None
                if theta_deg is not None and not (-180.0 <= theta_deg <= 180.0):
                    raise ValueError("旋转角 θ 必须在 [−180, 180] 度范围内")
                result = optimize_aim(
                    self.current_prediction, x_axis, y_axis,
                    spread_mode="REP_DEP", rep=rep_val, dep=dep_val,
                    rho=rho_val, theta_deg=theta_deg, reliability=1.0,
                )

            self.current_aim_result = result
            self.current_value_field = result.value_field

            figure = render_aim_optimization(
                self.current_prediction, result, self._active_config()
            )
            self._draw_figure(figure, which="aim")
            self._update_aim_summary(result)

            self.result_tabs.select(self.tab_frames["aim"])

            if mode == "CEP":
                mode_label = f"CEP={self.cep_var.get()}m"
            else:
                mode_label = (
                    f"REP={self.rep_var.get()}/DEP={self.dep_var.get()}m"
                )
                rho_used = result.rho
                if rho_used:
                    mode_label += f", ρ={rho_used:.2f}"
            self._set_status(
                f"瞄准优化完成 ({mode_label}): 最佳瞄准点 ({result.best_x:.1f}, {result.best_y:.1f}) m, "
                f"Vmax={result.vmax:.4f}, 增益={result.gain_relative:.2%}",
                kind="ok",
            )
        except Exception as exc:
            self._handle_error("瞄准优化失败", exc)

    def _update_aim_summary(self, result: AimOptimizationResult) -> None:
        """在瞄准优化标签页底部显示结果摘要。"""
        frame = self.tab_frames.get("aim")
        if frame is None:
            return

        # 查找或创建摘要条
        summary_frame = getattr(self, "_aim_summary_frame", None)
        if summary_frame is not None:
            summary_frame.destroy()

        summary_frame = tk.Frame(frame, bg=CONFIG.ui_panel_bg, relief="flat",
                                 highlightbackground=CONFIG.ui_border,
                                 highlightthickness=1)
        summary_frame.grid(row=1, column=0, sticky="ew", padx=4, pady=(4, 2))
        self._aim_summary_frame = summary_frame

        rho = getattr(result, "rho", 0.0) or 0.0
        spread_text = f"σx={result.sigma_x:.1f}, σy={result.sigma_y:.1f}"
        if rho:
            spread_text += f", ρ={rho:.2f}"
        items = [
            ("最佳瞄准点", f"({result.best_x:.1f}, {result.best_y:.1f}) m"),
            ("Vmax", f"{result.vmax:.4f}"),
            ("相对直瞄增益", f"+{result.gain_relative:.2%}" if result.gain_relative >= 0
                            else f"{result.gain_relative:.2%}"),
            ("位移", f"{result.shift_distance:.1f} m"),
            ("散布参数 (m)", spread_text),
        ]
        for i, (label, value) in enumerate(items):
            cell = tk.Frame(summary_frame, bg=CONFIG.ui_panel_bg)
            cell.grid(row=0, column=i, sticky="ew", padx=8, pady=6)
            summary_frame.columnconfigure(i, weight=1)
            tk.Label(cell, text=label, bg=CONFIG.ui_panel_bg, fg=CONFIG.ui_muted,
                     font=("Microsoft YaHei", 9)).pack()
            tk.Label(cell, text=value, bg=CONFIG.ui_panel_bg, fg=CONFIG.ui_text,
                     font=("Microsoft YaHei", 11, "bold")).pack(pady=(2, 0))

    def _handle_error(self, title: str, exc: Exception) -> None:
        self._set_status(f"{title}: {exc}", kind="error")
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        messagebox.showerror(title, f"{exc}\n\n{detail}")


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    app = DamagePredictionGUI(root)
    root.mainloop()
