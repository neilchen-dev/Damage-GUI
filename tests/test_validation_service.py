import pandas as pd
import pytest

from damage_gui.errors import ModelFitError
from damage_gui.services.validation_service import ValidationService
from synthetic_data import make_service, write_synthetic_dataset


@pytest.fixture
def validation_bundle(tmp_path):
    write_synthetic_dataset(tmp_path,velocities=(100.,200.,300.),angles=(10.,20.,30.))
    return make_service(tmp_path).train_bundle('F'),tmp_path

def test_observer_preserves_existing_metrics(validation_bundle):
    bundle,path=validation_bundle
    config=bundle.resolved_config()
    result=ValidationService().run(bundle,str(path),config,'leave_h_out',held_out_value=3.)
    reference=make_service(path).train_bundle('F',validation_mode='leave_h_out',held_out_value=3.)
    pd.testing.assert_frame_equal(pd.DataFrame(result.accuracy),reference.accuracy_report)
    assert len(result.samples)==9
    assert all(row['outside_global_support'] for row in result.samples)

def test_cancel_retains_completed_fold(validation_bundle):
    bundle,path=validation_bundle
    cancelled=False
    def progress(done,total,stage):
        nonlocal cancelled
        if '[2/3]' in stage: cancelled=True
    result=ValidationService().run(bundle,str(path),bundle.resolved_config(),'leave_h_out',
                                   progress=progress,cancel_check=lambda:cancelled)
    assert result.cancelled and len(result.folds)==1 and len(result.samples)==9
    assert len(result.fields)==9 and result.accuracy

def test_degenerate_layer_disabled_by_original_solver(tmp_path):
    write_synthetic_dataset(tmp_path)
    service=make_service(tmp_path)
    with pytest.raises(ModelFitError):
        ValidationService.validate_configuration(service.data_manager.get_level_records('F'),service.config,'leave_v_out')
