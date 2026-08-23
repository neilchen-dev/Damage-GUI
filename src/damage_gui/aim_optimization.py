"""兼容 shim：瞄准优化模块已迁移至 `damage_gui.optimization.aim`。

保留此文件以兼容历史导入路径（旧脚本 / 旧测试 / 旧文档）。
"""
from damage_gui.optimization.aim import (  # noqa: F401
    AimOptimizationResult,
    MonteCarloResult,
    build_rectangular_binary_target,
    cep_to_sigma,
    compute_aim_value_field,
    compute_aim_value_field_from_sigmas,
    correlated_gaussian_kernel,
    find_best_aim_point,
    gaussian_cell_probability_kernel,
    gaussian_kernel_from_cep,
    gaussian_sampled_probability_kernel,
    index_to_xy,
    monte_carlo_expected_damage,
    normal_cdf,
    optimize_aim,
    rectangular_hit_probability_analytic,
    rep_dep_to_sigma,
    rotation_to_covariance,
    value_at_physical_aim,
    xy_to_index,
)
