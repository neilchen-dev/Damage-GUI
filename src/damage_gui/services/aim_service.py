"""Application orchestration for CEP / REP-DEP aim optimization."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from damage_gui.optimization.aim import AimOptimizationResult, optimize_aim


@dataclass(frozen=True)
class AimServiceResult:
    """Optimization output plus the resolved application input parameters.

    ``__getattr__`` keeps the result convenient for existing plot and desktop
    consumers while the full scientific result remains available as
    ``optimization``.
    """

    optimization: AimOptimizationResult
    spread_mode: str
    cep: float | None = None
    rep: float | None = None
    dep: float | None = None
    rho: float = 0.0
    theta_deg: float | None = None

    @property
    def result(self) -> AimOptimizationResult:
        """Compatibility alias for callers that use ``result`` terminology."""
        return self.optimization

    def __getattr__(self, name: str):
        return getattr(self.optimization, name)


def _float_value(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


class AimService:
    """Resolve/validate UI-independent AIM parameters and invoke the core."""

    def optimize(
        self,
        damage_matrix: np.ndarray,
        x_axis: np.ndarray,
        y_axis: np.ndarray,
        *,
        spread_mode: str = "CEP",
        cep: str | float | None = None,
        rep: str | float | None = None,
        dep: str | float | None = None,
        rho: str | float = 0.0,
        theta_deg: str | float | None = None,
        reliability: float = 1.0,
        kernel_method: str = "cell_integrated",
    ) -> AimServiceResult:
        """Validate application parameters and call ``optimize_aim`` unchanged."""
        if spread_mode == "CEP":
            cep_value = _float_value(cep)
            if cep_value is not None and cep_value < 0:
                raise ValueError("CEP 必须非负")
            resolved = optimize_aim(
                damage_matrix,
                x_axis,
                y_axis,
                spread_mode="CEP",
                cep=cep_value,
                reliability=reliability,
                kernel_method=kernel_method,
            )
            return AimServiceResult(
                optimization=resolved,
                spread_mode="CEP",
                cep=cep_value,
                rho=0.0,
            )

        rep_value = _float_value(rep)
        dep_value = _float_value(dep)
        rho_value = float(rho)
        if not (-1.0 < rho_value < 1.0):
            raise ValueError("相关系数 ρ 必须在 (−1, 1) 开区间内")
        theta_value = (
            float(theta_deg) if theta_deg is not None and str(theta_deg).strip() else None
        )
        if theta_value is not None and not (-180.0 <= theta_value <= 180.0):
            raise ValueError("旋转角 θ 必须在 [−180, 180] 度范围内")
        resolved = optimize_aim(
            damage_matrix,
            x_axis,
            y_axis,
            spread_mode="REP_DEP",
            rep=rep_value,
            dep=dep_value,
            rho=rho_value,
            theta_deg=theta_value,
            reliability=reliability,
            kernel_method=kernel_method,
        )
        return AimServiceResult(
            optimization=resolved,
            spread_mode="REP_DEP",
            rep=rep_value,
            dep=dep_value,
            rho=resolved.rho,
            theta_deg=theta_value,
        )
