"""Shared validation for single-condition application inputs."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from damage_gui.config import CONDITION_LIMITS
from damage_gui.errors import DataValidationError

if TYPE_CHECKING:
    from damage_gui.data.loader import Condition


def _range_error(name: str, value: float) -> DataValidationError:
    lo, hi, _step = CONDITION_LIMITS[name]
    error = DataValidationError(
        f"{name}={value:g} 超出合法范围 [{lo:g}, {hi:g}]"
    )
    # Adapters can preserve their historical presentation without repeating
    # the validation rule or importing the GUI.
    error.condition_field = name  # type: ignore[attr-defined]
    error.condition_value = value  # type: ignore[attr-defined]
    error.condition_lower = lo  # type: ignore[attr-defined]
    error.condition_upper = hi  # type: ignore[attr-defined]
    return error


def validate_condition(h: float, v: float, deg: float) -> Condition:
    """Validate and return a domain ``Condition``.

    The limits and comparison semantics intentionally match the former CLI
    validator and batch CSV validator.  ``DataValidationError`` is used so
    callers can choose their own user-facing formatting.
    """
    from damage_gui.data.loader import Condition

    values: dict[str, Any] = {"h": h, "v": v, "deg": deg}
    for name, value in values.items():
        lo, hi, _step = CONDITION_LIMITS[name]
        if not (lo <= value <= hi):
            raise _range_error(name, value)
    return Condition(h=h, v=v, deg=deg)
