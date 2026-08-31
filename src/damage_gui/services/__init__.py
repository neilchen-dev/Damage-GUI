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
        "AdviceDecision": "prediction_service",
        "AimService": "aim_service",
        "AimServiceResult": "aim_service",
        "BatchService": "batch_service",
        "PredictionResult": "prediction_service",
        "PredictionService": "prediction_service",
        "TrainingResult": "training_service",
        "TrainingService": "training_service",
        "export_rows_csv": "export_service",
        "export_figure_png": "export_service",
        "export_matrix_csv": "export_service",
        "matrix_to_frame": "export_service",
        "parse_batch_input": "batch_service",
        "run_batch_service": "batch_service",
        "validate_condition": "conditions",
    }
    module_name = modules.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(f"{__name__}.{module_name}"), name)
