"""Presentation-independent export helpers used by GUI, CLI, and batch code."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from damage_gui.config import Config
from damage_gui.data.preprocessing import coordinate_axes


def matrix_to_frame(matrix: np.ndarray, config: Config) -> pd.DataFrame:
    """Build the established coordinate-labelled prediction DataFrame."""
    x_axis, y_axis = coordinate_axes(matrix.shape, config)
    frame = pd.DataFrame(matrix, index=y_axis, columns=x_axis)
    frame.index.name = "y"
    return frame


def export_matrix_csv(
    matrix: np.ndarray,
    path: str | Path,
    config: Config,
) -> Path:
    """Export a prediction matrix with the existing CSV semantics."""
    output_path = Path(path)
    matrix_to_frame(matrix, config).to_csv(output_path, encoding="utf-8-sig")
    return output_path


def export_figure_png(
    figure: Any,
    path: str | Path,
    *,
    dpi: int,
    bbox_inches: str = "tight",
) -> Path:
    """Save a figure without opening dialogs or displaying UI messages."""
    output_path = Path(path)
    figure.savefig(output_path, dpi=dpi, bbox_inches=bbox_inches)
    return output_path


def export_rows_csv(
    rows: Iterable[Mapping[str, Any]],
    columns: Sequence[str],
    path: str | Path,
) -> Path:
    """Export structured rows for batch/report consumers."""
    output_path = Path(path)
    frame = pd.DataFrame(list(rows), columns=list(columns))
    frame.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path
