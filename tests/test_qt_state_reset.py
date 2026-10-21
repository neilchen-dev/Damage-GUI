"""Qt workspaces must not show results belonging to a previous selection."""
from PySide6.QtWidgets import QApplication

from damage_gui.config import Config
from damage_gui.qt.i18n import Translator
from damage_gui.qt.panels.batch import BatchWorkspace
from damage_gui.qt.panels.history import HistoryWorkspace
from damage_gui.qt.panels.validation import ValidationWorkspace
from damage_gui.qt.task_adapter import TaskAdapter
from damage_gui.qt.validation_workflow import ValidationWorkflow
from damage_gui.qt.workflow import Workflow
from damage_gui.services.validation_service import ValidationResult


def test_validation_result_clears_when_model_changes(tmp_path):
    QApplication.instance() or QApplication([])
    adapter = TaskAdapter()
    workflow = Workflow(adapter, db_path=tmp_path / 'trace.sqlite')
    controller = ValidationWorkflow(workflow)
    workflow.validation = controller
    view = ValidationWorkspace(Translator(), controller)

    class Bundle:
        level = 'F'
        model_type = 'rbf'
        metadata = None
        data_dir = ''
        model = type('Model', (), {'model_name': 'RBF'})()

        def resolved_config(self):
            return Config()

    first, second = Bundle(), Bundle()
    view.set_bundle(first)
    view.result = ValidationResult([], [], [], [])
    view.config = Config()
    view.selected_sample = {'sample_id': 0}
    view.sample_model.replace([{'h': 1}])
    view.export_button.setEnabled(True)
    view.set_bundle(second)
    assert view.result is None
    assert view.config is None
    assert not hasattr(view, 'selected_sample')
    assert view.sample_model.rowCount() == 0
    assert not view.export_button.isEnabled()
    adapter.stop()


def test_history_refresh_clears_old_restorable_detail(tmp_path):
    QApplication.instance() or QApplication([])
    adapter = TaskAdapter()
    workflow = Workflow(adapter, db_path=tmp_path / 'trace.sqlite')
    view = HistoryWorkspace(Translator(), workflow)
    job = {'id': 'old', 'kind': 'prediction', 'status': 'SUCCESS',
           'created_at': '', 'duration_ms': 1,
           'details_json': '{"level":"F","h":1,"v":100,"deg":10}'}
    view.selected_id = 'old'
    view._detail_data = (job, None, [])
    view._render_detail()
    assert view.restore_button.isEnabled()
    workflow.load_history = lambda *args, **kwargs: None
    view.refresh()
    assert view.selected_id is None
    assert view._detail_data is None
    assert not view.restore_button.isEnabled()
    assert view.rows_model.rowCount() == 0
    adapter.stop()


def test_batch_output_clears_when_model_changes(tmp_path):
    QApplication.instance() or QApplication([])
    adapter = TaskAdapter()
    workflow = Workflow(adapter, db_path=tmp_path / 'trace.sqlite')
    view = BatchWorkspace(Translator(), workflow)

    class Bundle:
        level = 'F'
        metadata = None
        model = type('Model', (), {'model_name': 'RBF'})()

    view.set_bundle(Bundle())
    workflow.report = object()
    view.output = str(tmp_path / 'old.csv')
    view.output_label.setText('old.csv')
    view.open_button.setEnabled(True)
    view.set_bundle(Bundle())
    assert workflow.report is None
    assert view.output == ''
    assert not view.output_label.text()
    assert not view.open_button.isEnabled()
    adapter.stop()
