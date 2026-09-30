"""Structured validation adapter over the existing train/evaluate pipeline."""
from dataclasses import dataclass, field

import numpy as np

from damage_gui.data.loader import DamageDataManager
from damage_gui.errors import OperationCancelled
from damage_gui.model.bundle import DamageModelService


@dataclass
class ValidationResult:
    accuracy: list
    samples: list
    folds: list
    fields: list = field(repr=False)
    cancelled: bool = False

class ValidationService:
    def run(self, bundle, data_dir, config, mode, *,
            held_out_value=None, progress=None, cancel_check=None):
        service = DamageModelService(DamageDataManager(data_dir),config=config)
        pairs, supports, folds = [], [], []
        def observe(split, evaluated):
            detector = service.make_ood_detector(
                np.array([row.condition.as_array() for row in split.train]))
            pairs.extend(evaluated)
            supports.extend(detector.report(row.condition) for row,truth,prediction in evaluated)
            folds.append(dict(label=split.label, train=len(split.train), test=len(split.test),
                              held_out=[row.condition.as_dict() for row in split.test]))
        cancelled = False
        try:
            validated = service.train_bundle(bundle.level, validation_mode=mode,
                                             model_type=bundle.model_type,
                                             pod_n_components=config.pod_n_components,
                                             held_out_value=held_out_value,
                                             evaluation_observer=observe,
                                             progress=progress, cancel_check=cancel_check)
            accuracy, conditions = validated.accuracy_report, validated.condition_report
        except OperationCancelled:
            cancelled = True
            if pairs:
                accuracy, conditions = service._evaluate_pairs(bundle.level,pairs)
            else:
                return ValidationResult([],[],folds,[],True)
        rows = conditions.to_dict('records')
        for i,(row,ood) in enumerate(zip(rows,supports, strict=False)):
            row.update(sample_id=i, confidence=ood.level.upper(), ood_distance=ood.distance,
                       outside_global_support=ood.in_hull is False,
                       local_support_insufficient=ood.local_support is False)
        return ValidationResult(accuracy.to_dict('records'), rows, folds,
                                [(truth,prediction) for record,truth,prediction in pairs],
                                cancelled)

    @staticmethod
    def validate_configuration(records, config, mode, held_out_value=None):
        """Probe the actual split/RBF solver without reading field matrices."""
        from damage_gui.model.bundle import build_model
        from damage_gui.model.rbf import make_rbf_interpolator
        from damage_gui.model.validation import make_splits
        splits=make_splits(records,mode,config)
        field={'leave_h_out':'h','leave_v_out':'v','leave_deg_out':'deg'}.get(mode)
        if held_out_value is not None:
            splits=[split for split in splits
                    if field and getattr(split.test[0].condition,field)==held_out_value]
        if not splits:
            raise ValueError('Selected validation split is unavailable')
        for split in splits:
            conditions=np.array([record.condition.as_array() for record in split.train])
            model=build_model(config.model_type,config,config.pod_n_components)
            model.cond_lo=conditions.min(axis=0)
            span=conditions.max(axis=0)-model.cond_lo
            model.cond_span=np.where(span>0,span,1.)
            make_rbf_interpolator(model._normalize(conditions),np.zeros((len(conditions),1)),
                                  config.rbf_kernel,config.rbf_smoothing,
                                  config.rbf_epsilon,'Validation compatibility')
        return True
