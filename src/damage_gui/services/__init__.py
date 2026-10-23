"""Application services shared by the desktop GUI and command-line tools.

The service layer coordinates existing data, model, evaluation, and storage
components.  It deliberately contains no Tkinter or other presentation code.
"""

__all__ = [
    "AdviceDecision",
    "AimService",
    "AimServiceResult",
    "BatchService",
    "PredictionResult",
    "PredictionService",
    "TrainingResult",
    "TrainingService",
    "export_rows_csv",
    "export_figure_png",
    "export_matrix_csv",
    "matrix_to_frame",
    "parse_batch_input",
    "run_batch_service",
    "validate_condition",
]


def __getattr__(name: str):
    """Lazily expose service APIs without introducing package import cycles."""
    from importlib import import_module

    modules = {
        "AdviceDecision": "damage_gui.services.prediction_service",
        "AimService": "damage_gui.services.aim_service",
        "AimServiceResult": "damage_gui.services.aim_service",
        "BatchService": "damage_gui.services.batch_service",
        "PredictionResult": "damage_gui.services.prediction_service",
        "PredictionService": "damage_gui.services.prediction_service",
        "TrainingResult": "damage_gui.services.training_service",
        "TrainingService": "damage_gui.services.training_service",
        # 数据层导出助手（自 services 下沉至 data，此处保留兼容 facade）
        "export_rows_csv": "damage_gui.data.export",
        "export_figure_png": "damage_gui.data.export",
        "export_matrix_csv": "damage_gui.data.export",
        "matrix_to_frame": "damage_gui.data.export",
        "parse_batch_input": "damage_gui.services.batch_service",
        "run_batch_service": "damage_gui.services.batch_service",
        "validate_condition": "damage_gui.data.conditions",
    }
    module_name = modules.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(module_name), name)
