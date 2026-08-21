"""Matplotlib 绘图：热力图、误差场与瞄准优化结果渲染。"""
from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib import font_manager, ticker
from matplotlib.figure import Figure

from damage_gui.config import Config, CONFIG, DAMAGE_CMAP, ERROR_CMAP
from damage_gui.data.preprocessing import coordinate_axes

matplotlib.use("TkAgg")


def configure_matplotlib_fonts() -> None:
    candidate_fonts = [
        (Path(r"C:\Windows\Fonts\msyh.ttc"), "Microsoft YaHei"),
        (Path(r"C:\Windows\Fonts\msyh.ttf"), "Microsoft YaHei"),
        (Path(r"C:\Windows\Fonts\simhei.ttf"), "SimHei"),
        (Path(r"C:\Windows\Fonts\simsun.ttc"), "SimSun"),
    ]

    selected_fonts: list[str] = []
    for font_path, font_name in candidate_fonts:
        if font_path.exists():
            try:
                font_manager.fontManager.addfont(str(font_path))
                selected_fonts.append(font_name)
            except Exception:
                continue

    if not selected_fonts:
        selected_fonts = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]

    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = selected_fonts + [
        "SimHei",
        "Microsoft YaHei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
    warnings.filterwarnings(
        "ignore",
        message=r".*Glyph .* missing from font\(s\) DejaVu Sans.*",
        category=UserWarning,
    )


configure_matplotlib_fonts()


def find_crop_bounds(
    matrices: list[np.ndarray],
    threshold: float,
    margin: int,
) -> tuple[int, int, int, int]:
    combined = np.zeros_like(matrices[0], dtype=bool)
    for matrix in matrices:
        combined |= np.asarray(matrix) > threshold

    if not np.any(combined):
        return 0, matrices[0].shape[0], 0, matrices[0].shape[1]

    rows, cols = np.where(combined)
    row_min = max(0, int(rows.min()) - margin)
    row_max = min(matrices[0].shape[0], int(rows.max()) + margin + 1)
    col_min = max(0, int(cols.min()) - margin)
    col_max = min(matrices[0].shape[1], int(cols.max()) + margin + 1)
    return row_min, row_max, col_min, col_max


def crop_matrix_and_extent(
    matrix: np.ndarray,
    bounds: tuple[int, int, int, int],
    config: Config | None = None,
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    row_min, row_max, col_min, col_max = bounds
    x_axis, y_axis = coordinate_axes(matrix.shape, config)
    cropped = matrix[row_min:row_max, col_min:col_max]
    extent = (
        float(x_axis[col_min]),
        float(x_axis[col_max - 1]),
        float(y_axis[row_min]),
        float(y_axis[row_max - 1]),
    )
    return cropped, extent


def _style_heatmap_axis(axis, title: str, show_y_axis: bool = True) -> None:
    """极简坐标轴：只在最左图保留 y 轴，刻度稀疏、无网格、细边框。"""
    axis.set_facecolor(CONFIG.ui_bg)
    axis.set_title(title, fontsize=10.5, color=CONFIG.ui_text, pad=8)
    axis.set_xlabel("x (m)", fontsize=8.5, color=CONFIG.ui_muted)
    axis.xaxis.set_major_locator(ticker.MaxNLocator(nbins=5, steps=[1, 2, 4, 5, 10]))
    axis.grid(False)

    if show_y_axis:
        axis.set_ylabel("y (m)", fontsize=8.5, color=CONFIG.ui_muted)
        axis.yaxis.set_major_locator(ticker.MaxNLocator(nbins=5, steps=[1, 2, 4, 5, 10]))
    else:
        axis.get_yaxis().set_visible(False)

    axis.tick_params(colors=CONFIG.ui_muted, labelsize=8, length=3, width=0.6)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(CONFIG.ui_border)
        axis.spines[side].set_linewidth(0.7)


def _add_percent_colorbar(figure, image, axis, label: str, zero_center: bool = False) -> None:
    """纤细、留白充分的颜色条。

    zero_center=True 用于双向发散色带（误差图）：刻度取对称等分，保证 0% 一定
    落在刻度上，并在零点处画一条指示线，方便辨识"绝对无误差"区域。
    """
    colorbar = figure.colorbar(image, ax=axis, shrink=0.8, aspect=30, pad=0.06)
    colorbar.ax.set_ylabel(label, rotation=90, fontsize=8.5, color=CONFIG.ui_muted)
    colorbar.outline.set_visible(False)
    colorbar.ax.tick_params(labelsize=7.5, colors=CONFIG.ui_muted, length=2, width=0.5)
    if zero_center:
        vmin, vmax = image.get_clim()
        ticks = np.linspace(vmin, vmax, 5)
        colorbar.set_ticks(ticks)
        colorbar.set_ticklabels(
            ["0%" if abs(t) < 1e-12 else f"{t * 100:+.0f}%" for t in ticks]
        )
        colorbar.ax.axhline(0.0, color=CONFIG.ui_text, linewidth=1.0)
    else:
        ticks = colorbar.get_ticks()
        colorbar.set_ticks(ticks)
        colorbar.set_ticklabels([f"{tick * 100:.0f}%" for tick in ticks])


def render_heatmaps(
    true_matrix: np.ndarray | None,
    pred_matrix: np.ndarray,
    display_threshold: float,
    config: Config | None = None,
) -> Figure:
    """三联图：真实毁伤场 / 预测毁伤场（YlGnBu 单色调）/ 带符号误差场（RdBu_r 发散）。"""
    config = config or CONFIG
    matrices_for_bounds = [pred_matrix]
    if true_matrix is not None:
        matrices_for_bounds.append(true_matrix)

    bounds = find_crop_bounds(
        matrices_for_bounds,
        threshold=display_threshold,
        margin=config.crop_margin,
    )

    if true_matrix is None:
        figure = Figure(figsize=(8.8, 6.4), dpi=100, constrained_layout=True)
        figure.patch.set_facecolor(CONFIG.ui_bg)
        axis = figure.add_subplot(1, 1, 1)
        axis.set_anchor("C")
        cropped, extent = crop_matrix_and_extent(pred_matrix, bounds, config)
        image = axis.imshow(
            cropped, extent=extent, origin="lower", cmap=DAMAGE_CMAP,
            vmin=0.0, vmax=1.0, aspect="equal",
        )
        _style_heatmap_axis(axis, "预测毁伤场 Predicted")
        _add_percent_colorbar(figure, image, axis, "毁伤强度")
        return figure

    figure = Figure(figsize=(12.8, 4.6), dpi=100, constrained_layout=True)
    figure.patch.set_facecolor(CONFIG.ui_bg)
    axes = [figure.add_subplot(1, 3, i + 1) for i in range(3)]

    for index, (axis, (title, matrix)) in enumerate(zip(
        axes[:2],
        [("真实毁伤场 True", true_matrix), ("预测毁伤场 Predicted", pred_matrix)],
    )):
        cropped, extent = crop_matrix_and_extent(matrix, bounds, config)
        image = axis.imshow(
            cropped, extent=extent, origin="lower", cmap=DAMAGE_CMAP,
            vmin=0.0, vmax=1.0, aspect="equal",
        )
        _style_heatmap_axis(axis, title, show_y_axis=(index == 0))
        _add_percent_colorbar(figure, image, axis, "毁伤强度")

    signed_error = pred_matrix.astype(np.float32) - true_matrix.astype(np.float32)
    cropped_err, extent = crop_matrix_and_extent(signed_error, bounds, config)
    err_limit = max(float(np.nanmax(np.abs(cropped_err))), 0.10)
    image = axes[2].imshow(
        cropped_err, extent=extent, origin="lower", cmap=ERROR_CMAP,
        vmin=-err_limit, vmax=err_limit, aspect="equal",
    )
    _style_heatmap_axis(axes[2], "误差 (预测 − 真实)", show_y_axis=False)
    _add_percent_colorbar(figure, image, axes[2], "误差", zero_center=True)

    return figure


def render_full_prediction(
    pred_matrix: np.ndarray,
    config: Config | None = None,
) -> Figure:
    """全视图预测图：显示整个 ROI 范围内的预测毁伤场。"""
    from damage_gui.data.preprocessing import roi_mask_for_shape

    config = config or CONFIG
    roi = roi_mask_for_shape(pred_matrix.shape, config)
    rows = np.flatnonzero(roi.any(axis=1))
    cols = np.flatnonzero(roi.any(axis=0))
    bounds = (int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1)

    figure = Figure(figsize=(7.6, 6.6), dpi=100, constrained_layout=True)
    figure.patch.set_facecolor(CONFIG.ui_bg)
    axis = figure.add_subplot(1, 1, 1)
    # 单张大图水平居中：固定纵横比的图像在画布拉伸时锚定中心而非左侧
    axis.set_anchor("C")
    cropped, extent = crop_matrix_and_extent(pred_matrix, bounds, config)
    image = axis.imshow(
        cropped, extent=extent, origin="lower", cmap=DAMAGE_CMAP,
        vmin=0.0, vmax=1.0, aspect="equal",
    )
    _style_heatmap_axis(axis, "全视图预测毁伤场（完整 ROI）")
    _add_percent_colorbar(figure, image, axis, "毁伤强度")
    return figure


def render_aim_optimization(
    damage_matrix: np.ndarray,
    result,
    config: Config | None = None,
) -> Figure:
    """渲染瞄准优化 D + V 双图：左图毁伤场，右图价值场。

    在两幅图上同时标记 D 峰值（红色 ×）与最佳瞄准点（金色 ★），
    右图附带数值标注。相关散布（rho != 0）时在标题注明协方差参数。

    result: AimOptimizationResult（避免循环导入用鸭子类型）。
    """
    config = config or CONFIG
    bounds = find_crop_bounds(
        [damage_matrix], threshold=config.display_threshold,
        margin=config.crop_margin,
    )

    figure = Figure(figsize=(12.8, 5.2), dpi=100, constrained_layout=True)
    figure.patch.set_facecolor(CONFIG.ui_bg)

    # 左图: 毁伤场 D
    ax0 = figure.add_subplot(1, 2, 1)
    cropped_d, extent_d = crop_matrix_and_extent(damage_matrix, bounds, config)
    im0 = ax0.imshow(
        cropped_d, extent=extent_d, origin="lower", cmap=DAMAGE_CMAP,
        vmin=0.0, vmax=1.0, aspect="equal",
    )
    _style_heatmap_axis(ax0, "毁伤场 D")
    _add_percent_colorbar(figure, im0, ax0, "毁伤值")

    # 右图: 价值场 V（相关散布时标注协方差参数）
    ax1 = figure.add_subplot(1, 2, 2)
    cropped_v, extent_v = crop_matrix_and_extent(result.value_field, bounds, config)
    vmax = max(float(result.value_field.max()), 1e-10)
    im1 = ax1.imshow(
        cropped_v, extent=extent_v, origin="lower", cmap="viridis",
        vmin=0.0, vmax=vmax, aspect="equal",
    )
    v_title = "期望毁伤效能 V"
    rho = getattr(result, "rho", 0.0) or 0.0
    if rho != 0.0:
        v_title += (
            f"\n(σx={result.sigma_x:.1f}, σy={result.sigma_y:.1f}, ρ={rho:.2f})"
        )
    _style_heatmap_axis(ax1, v_title, show_y_axis=False)
    _add_percent_colorbar(figure, im1, ax1, "期望毁伤效能")

    # 标记 D 峰值和最佳瞄准点（在两幅图上都标）
    for ax in (ax0, ax1):
        # D 峰值: 红色 ×
        ax.plot(result.d_peak_x, result.d_peak_y, marker="x", ms=14,
                mew=2.5, color="#DC2626", zorder=10)
        # 最佳瞄准点: 金色 ★
        ax.plot(result.best_x, result.best_y, marker="*", ms=16,
                mec="white", mew=1.2, mfc="#F59E0B", zorder=11)

    # 在右图上添加标注
    ax1.annotate(
        f"★ 最佳瞄准点\n({result.best_x:.1f}, {result.best_y:.1f}) m\n"
        f"Vmax={result.vmax:.4f}",
        xy=(result.best_x, result.best_y), xytext=(12, 12),
        textcoords="offset points", fontsize=8, color="#F59E0B",
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#F59E0B", alpha=0.9),
    )
    ax1.annotate(
        f"× D 峰值\n({result.d_peak_x:.1f}, {result.d_peak_y:.1f}) m",
        xy=(result.d_peak_x, result.d_peak_y), xytext=(-12, -25),
        textcoords="offset points", fontsize=8, color="#DC2626",
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#DC2626", alpha=0.9),
    )

    return figure
