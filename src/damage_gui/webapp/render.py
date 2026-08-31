"""Headless PNG/CSV rendering for trusted stored results."""
from __future__ import annotations

from io import BytesIO

from damage_gui.webapp.dependencies import StoredPrediction


def prediction_png(item: StoredPrediction) -> bytes:
    """Render with the shared plot functions using Matplotlib's Agg backend."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    from damage_gui.visualization.plots import render_heatmaps

    result = item.result
    figure = render_heatmaps(
        result.truth,
        result.prediction,
        display_threshold=item.config.display_threshold,
        config=item.config,
    )
    try:
        buffer = BytesIO()
        figure.savefig(buffer, format="png", dpi=item.config.export_dpi, bbox_inches="tight")
        return buffer.getvalue()
    finally:
        plt.close(figure)


def prediction_csv(item: StoredPrediction) -> bytes:
    """Reuse the established coordinate-labelled matrix export semantics."""
    from damage_gui.services.export_service import matrix_to_frame

    buffer = BytesIO()
    matrix_to_frame(item.result.prediction, item.config).to_csv(
        buffer, encoding="utf-8-sig"
    )
    return buffer.getvalue()
