"""GUI 展示层的纯函数：选项映射与指标状态文案。"""

from __future__ import annotations

from damage_gui.gui.i18n import Translator
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

MODEL_TYPE_KEYS = (
    ("choice.rbf", "rbf"),
    ("choice.pod_rbf", "pod_rbf"),
)

VALIDATION_CHOICE_KEYS = (
    ("choice.validation.random", "random"),
    ("choice.validation.leave_h_out", "leave_h_out"),
    ("choice.validation.leave_v_out", "leave_v_out"),
    ("choice.validation.leave_deg_out", "leave_deg_out"),
    ("choice.validation.corner", "corner"),
)


def model_type_choices(translator: Translator) -> tuple[tuple[str, str], ...]:
    """Return localized display labels while keeping stable internal values."""
    return tuple((translator.t(key), value) for key, value in MODEL_TYPE_KEYS)


def validation_choices(translator: Translator) -> tuple[tuple[str, str], ...]:
    """Return localized validation labels while keeping stable internal values."""
    return tuple((translator.t(key), value) for key, value in VALIDATION_CHOICE_KEYS)


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
