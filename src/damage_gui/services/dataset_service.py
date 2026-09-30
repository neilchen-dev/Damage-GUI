"""Dataset inspection through the same scanner/parser used for training."""
import time
from collections import Counter

import numpy as np

from damage_gui.data.loader import DamageDataManager, read_source_matrix
from damage_gui.errors import OperationCancelled


def inspect_dataset(directory, cancel_check=None):
    started = time.perf_counter()
    records = DamageDataManager(directory).scan_records()
    levels = {}
    for level in ('F', 'M', 'P'):
        selected = [record for record in records if record.level == level]
        if not selected:
            continue
        keys = Counter(record.condition.as_key() for record in selected)
        axes = [sorted({key[i] for key in keys}) for i in range(3)]
        shapes, errors = Counter(), []
        for record in selected:
            if cancel_check and cancel_check():
                raise OperationCancelled('Dataset inspection cancelled')
            try:
                matrix = read_source_matrix(record.path)
                if matrix.ndim != 2 or not matrix.size or not np.isfinite(matrix).all():
                    raise ValueError('Empty or nonfinite field')
                shapes[matrix.shape] += 1
            except (OSError, ValueError, UnicodeError) as exc:
                errors.append(f'{record.path.name}: {exc}')
        levels[level] = dict(samples=len(selected), valid=len(selected)-len(errors),
                             errors=errors, duplicates=sum(count-1 for count in keys.values()),
                             grid_gaps=int(np.prod([len(axis) for axis in axes]))-len(keys),
                             axes=axes,
                             shapes={f'{shape[0]} × {shape[1]}': count
                                     for shape, count in shapes.items()})
    return dict(directory=str(directory), levels=levels, samples=len(records),
                elapsed_seconds=time.perf_counter()-started)
