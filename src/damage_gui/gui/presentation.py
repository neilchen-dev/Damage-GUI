"""GUI 展示层的纯函数：选项映射与指标状态文案。"""
from __future__ import annotations

from damage_gui.gui.theme import THEME
from damage_gui.model.validation import VALIDATION_LABELS

MODEL_TYPE_CHOICES = (
    ("RBF 插值场", "rbf"),
    ("POD-RBF 降阶模型", "pod_rbf"),
)

VALIDATION_CHOICES = (
    (VALIDATION_LABELS["random"], "random"),
    (VALIDATION_LABELS["leave_h_out"], "leave_h_out"),
    (VALIDATION_LABELS["leave_v_out"], "leave_v_out"),
    (VALIDATION_LABELS["leave_deg_out"], "leave_deg_out"),
    (VALIDATION_LABELS["corner"], "corner"),
)


def choice_value(
    choices: tuple[tuple[str, str], ...],
    selected_label: str,
    default: str,
) -> str:
    return next((value for label, value in choices if label == selected_label), default)


def metric_display(
    value: float | None,
    label: str,
    target: float,
) -> tuple[str, str, str, str]:
    import pandas as pd

    if value is None or pd.isna(value):
        return "--", THEME.text, f"{label} · 目标 < {target:.0%}", THEME.muted
    if value < target:
        return (
            f"{value:.2%}",
            THEME.success,
            f"{label} · 通过目标 < {target:.0%} ✔",
            THEME.success,
        )
    return (
        f"{value:.2%}",
        THEME.danger,
        f"{label} · 未达目标 < {target:.0%} ✘",
        THEME.danger,
    )
