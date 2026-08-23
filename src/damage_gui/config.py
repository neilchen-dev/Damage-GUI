"""全局配置：模型、预处理、评估与 UI 参数集中管理。"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any, Mapping

ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class Config:
    coord_min: float = -236.0
    coord_max: float = 236.0
    target_shape: tuple[int, int] = (473, 473)

    # 有效建模区域 ROI：只在该矩形区域内插值和预测，ROI 外置 0。
    use_roi: bool = True
    roi_x_min: float = -30.0
    roi_x_max: float = 30.0
    roi_y_min: float = -60.0
    roi_y_max: float = 60.0

    random_state: int = 42
    test_size: float = 0.2

    # 结构化验证方式：
    #   random       —— 随机 80/20 留出（插值口径，偏乐观）
    #   leave_h_out  —— 按高度整层留出（对每个高度值做留一层交叉验证）
    #   leave_v_out  —— 按速度整层留出
    #   leave_deg_out—— 按角度整层留出
    #   corner       —— 角落区域留出（高速 + 大角度整块外推测试）
    validation_mode: str = "random"
    # 真实数据速度范围为 150~300；以最高两档 (250/300) 与最大两档角度
    # (40/45) 的组合定义角落外推区，共留出 20/120 个工况。
    corner_v_min: float = 250.0
    corner_deg_min: float = 40.0

    # 模型类型："rbf"（逐像素 RBF 插值场）或 "pod_rbf"（POD 降阶 + 模态系数 RBF 插值）
    model_type: str = "rbf"
    # POD 保留的主成分（模态）数量，K=10~30 通常已能覆盖主要空间结构
    pod_n_components: int = 20

    # OOD / 预测可信度检测阈值（归一化工况空间中的最近训练工况距离）：
    #   d < ood_high_max    → High Confidence（插值区域）
    #   d < ood_medium_max  → Medium Confidence
    #   其余                → Low Confidence（外推区域，误差可能偏大）
    ood_high_max: float = 0.15
    ood_medium_max: float = 0.3
    # 全局凸包使用 SVD 自动识别任意方向的内在维度；局部邻域凸包用于识别
    # 全局凸包内部的凹形缺口/稀疏空洞。local_neighbors=0 表示按维度自动取值。
    ood_use_hull: bool = True
    ood_use_local_support: bool = True
    ood_local_neighbors: int = 0
    ood_max_1d_gap_ratio: float = 2.5

    # 蒙特卡洛降噪（双边滤波）：原始毁伤矩阵带有像素级仿真噪声（实测单幅矩阵
    # 做 1 像素平滑自身就变化 18%，相邻工况逐点差异 P95 达 50%）。
    # 双边滤波只平滑数值相近的邻域，遇到真实的强度突变（如接近 1.0 的毁伤核心
    # 边缘）会保留而不是抹平——实测峰值保留约 100%（高斯 sigma=3 会把峰值
    # 0.999 压到 0.377）。训练与展示统一使用双边滤波后的场。
    denoise_sigma_spatial: float = 3.0
    denoise_sigma_range: float = 0.15
    denoise_radius: int = 6
    # 场级评估口径：即使双边滤波后，真值仍残留像素级噪声（P95 约 40%），
    # 拿完美预测对比带噪真值也会"测出"同量级假误差，故逐点指标在
    # "局部平均场"上计算：真值与预测先做同样的高斯低通（eval_smoothing_sigma）
    # 再逐点比较。这衡量毁伤概率场的真实一致性；热力图展示不受影响（保真）。
    # 评估报告同时保留 Raw / Smoothed 双口径结果，避免"平滑刷指标"的质疑。
    eval_smoothing_sigma: float = 3.0

    # RBF 插值场参数：kernel 为 scipy.interpolate.RBFInterpolator 的核函数，
    # smoothing=0 表示精确插值（训练工况上零误差）。
    rbf_kernel: str = "thin_plate_spline"
    rbf_smoothing: float = 0.0
    # 质心对齐插值：毁伤图案随工况平移时，逐像素直接插值会产生"重影"
    # （新旧位置各留一个变淡的影子，图案该在的位置反而预测为 0）。
    # 开启后先把每幅矩阵平移到质心居中的标准位置再插值形状，
    # 质心位置单独用 RBF 插值，预测时把形状平移回去。
    align_patterns: bool = True
    align_window_margin: int = 16

    display_threshold: float = 0.08
    crop_margin: int = 10
    export_dpi: int = 120
    eval_area_threshold: float = 0.01
    eval_focus_thresholds: tuple[float, float] = (0.01, 0.05)
    # 相对误差只在主要毁伤区域 damage > relative_error_threshold 内统计；
    # 核心指标为平均相对误差与 P95 混合误差，目标 < relative_error_target。
    relative_error_threshold: float = 0.05
    relative_error_target: float = 0.20
    # 混合误差 = |pred - true| / max(true, hybrid_error_floor)。
    # 毁伤区边缘 true 刚过 0.05 的点，边界偏移 1 像素就会让纯相对误差爆到 100%+，
    # 但其绝对误差可忽略；分母加下限后等价于"相对误差 < 20% 或绝对误差 < 0.05 即达标"，
    # 使指标反映毁伤强度预测能力而非亚像素级边界定位能力。
    hybrid_error_floor: float = 0.25

    # 现代轻量化配色：浅冷灰底 + 唯一主题色（深科技蓝），状态色柔和不刺眼
    ui_bg: str = "#F5F7FA"
    ui_panel_bg: str = "#FFFFFF"
    ui_soft_bg: str = "#EEF2F7"
    ui_border: str = "#E2E8F0"
    ui_shadow: str = "#E3E8F0"
    ui_primary: str = "#1E3A8A"
    ui_primary_dark: str = "#172E6E"
    ui_accent: str = "#1E3A8A"
    ui_text: str = "#1E293B"
    ui_muted: str = "#64748B"
    ui_header_bg: str = "#1E3A8A"
    ui_header_fg: str = "#FFFFFF"
    ui_header_muted: str = "#B6C3E4"
    ui_success: str = "#15803D"
    ui_danger: str = "#B91C1C"
    ui_busy: str = "#B45309"

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "Config":
        """从模型包等外部映射恢复配置，忽略未来或旧版本的未知字段。"""
        if not values:
            return cls()
        known = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in values.items() if key in known})


CONFIG = Config()
VERSION = "2.0.0"
APP_TITLE = "基于数据驱动的毁伤效能快速评估方法研究"

# 毁伤强度：单色调科学渐变，浅色=未毁伤，深蓝=完全毁伤（对色弱友好，无廉价感）
DAMAGE_CMAP = "YlGnBu"
# 误差场：发散色带，0 误差为白色，正负误差用柔和的红/蓝区分
ERROR_CMAP = "RdBu_r"
