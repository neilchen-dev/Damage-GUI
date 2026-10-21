"""Qt aim page uses the shared optimization service and clears stale results."""
from types import SimpleNamespace

import numpy as np
from PySide6.QtWidgets import QApplication

from damage_gui.qt.main_window import DamageQtMainWindow


def test_aim_page_modes_and_lifecycle():
    QApplication.instance() or QApplication([])
    window = DamageQtMainWindow()
    aim = window.aim_workspace
    try:
        window._navigate("aim")
        assert window.inspector.currentWidget() is aim.inspector
        assert not aim.run_button.isEnabled()

        axis = np.linspace(-1, 1, 41)
        field = np.exp(-12 * (axis[None, :] ** 2 + axis[:, None] ** 2))
        prediction = SimpleNamespace(
            prediction=field, truth=None,
            condition=SimpleNamespace(h=1, v=100, deg=10),
            peak_intensity=float(field.max()), damage_area_ratio=0.1,
            ood_report=None, truth_comparison_metrics={}, elapsed_ms=1,
        )
        window._prediction_panel.prediction_completed.emit(prediction)
        assert aim.prediction is field
        window._navigate("aim")
        assert aim.run_button.isEnabled()
        window._act_run.trigger()
        assert aim.result is not None
        assert aim.result.spread_mode == "CEP"
        assert aim.view._has_result
        assert window._activity.result_kind == "aim"
        assert len([axis for axis in aim.view.figure.axes if axis.images]) == 2
        assert window._act_current_export.isEnabled()
        assert window._act_export.isEnabled()
        window._act_pan.trigger()
        assert aim.view.buttons["Pan"].isChecked()
        assert not window._field_view.buttons["Pan"].isChecked()
        window._act_pan.trigger()

        aim.mode.setCurrentIndex(1)
        aim.rep.setValue(12)
        aim.dep.setValue(5)
        aim.rho.setValue(0.4)
        aim.run_button.click()
        assert abs(aim.result.rho - 0.4) < 1e-12
        aim.rotation.setChecked(True)
        aim.theta.setValue(30)
        aim.run_button.click()
        assert abs(aim.result.rho) > 0.01

        window.translator.set_language("en")
        assert "Best aim point" in aim.summary.text()
        assert aim.view.figure.axes[0].get_title() == "Damage Field D"

        aim.set_prediction(None, None)
        assert aim.result is None
        assert not aim.run_button.isEnabled()
        assert not aim.view._has_result
    finally:
        window.close()
