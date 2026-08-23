"""结构化交叉验证切分。

随机 80/20 留出对规则工况网格偏乐观（测试点常被训练点包围，本质是简单
插值）。本模块提供更严格的验证切分：

- random       ：随机留出（基线，插值口径）
- leave_h_out  ：按高度整层留出（每个高度值轮流作为测试层）
- leave_v_out  ：按速度整层留出
- leave_deg_out：按角度整层留出
- corner       ：角落区域留出（高速 + 大角度整块区域外推测试）

整层留出会返回多个切分（每层一个），由调用方聚合折外预测得到
"真正未见过的工况区域"上的诚实指标。
"""
from __future__ import annotations

from dataclasses import dataclass

from damage_gui.config import Config
from damage_gui.data.loader import DamageRecord

VALIDATION_MODES = (
    "random",
    "leave_h_out",
    "leave_v_out",
    "leave_deg_out",
    "corner",
)

VALIDATION_LABELS = {
    "random": "随机留出 Random Holdout",
    "leave_h_out": "按高度整层留出 Leave-h-out",
    "leave_v_out": "按速度整层留出 Leave-v-out",
    "leave_deg_out": "按角度整层留出 Leave-deg-out",
    "corner": "角落区域留出 Corner Holdout",
}

# 整层留出模式对应的工况字段
_LEAVE_FIELD = {
    "leave_h_out": "h",
    "leave_v_out": "v",
    "leave_deg_out": "deg",
}


@dataclass
class ValidationSplit:
    """一次验证切分：train 上训练，test 上评估。"""

    mode: str
    label: str
    train: list[DamageRecord]
    test: list[DamageRecord]


def _random_split(
    records: list[DamageRecord], config: Config
) -> list[ValidationSplit]:
    import numpy as np
    from sklearn.model_selection import train_test_split

    if len(records) <= 6:
        shuffled = list(records)
        rng = np.random.default_rng(config.random_state)
        rng.shuffle(shuffled)
        train, test = shuffled[:-1], shuffled[-1:]
    else:
        train, test = train_test_split(
            records,
            test_size=config.test_size,
            random_state=config.random_state,
            shuffle=True,
        )
    return [
        ValidationSplit(
            mode="random",
            label=VALIDATION_LABELS["random"],
            train=list(train),
            test=list(test),
        )
    ]


def _leave_field_out(
    records: list[DamageRecord], mode: str
) -> list[ValidationSplit]:
    field = _LEAVE_FIELD[mode]
    values = sorted({getattr(record.condition, field) for record in records})
    if len(values) < 2:
        raise ValueError(
            f"{VALIDATION_LABELS[mode]} 至少需要 2 个不同的{field}取值，"
            f"当前只有 {len(values)} 个"
        )
    splits: list[ValidationSplit] = []
    for value in values:
        test = [r for r in records if getattr(r.condition, field) == value]
        train = [r for r in records if getattr(r.condition, field) != value]
        if not train:
            continue
        splits.append(
            ValidationSplit(
                mode=mode,
                label=f"{VALIDATION_LABELS[mode]} ({field}={value:g})",
                train=train,
                test=test,
            )
        )
    return splits


def _corner_split(
    records: list[DamageRecord], config: Config
) -> list[ValidationSplit]:
    test = [
        record
        for record in records
        if record.condition.v >= config.corner_v_min
        and record.condition.deg >= config.corner_deg_min
    ]
    if not test:
        raise ValueError(
            "数据目录中没有满足角落区域条件的工况 "
            f"(v >= {config.corner_v_min:g}, deg >= {config.corner_deg_min:g})，"
            "无法进行角落留出验证"
        )
    train = [record for record in records if record not in test]
    if not train:
        raise ValueError(
            "角落区域条件覆盖了全部工况，没有剩余训练样本；"
            "请提高 corner_v_min / corner_deg_min"
        )
    return [
        ValidationSplit(
            mode="corner",
            label=VALIDATION_LABELS["corner"],
            train=train,
            test=test,
        )
    ]


def make_splits(
    records: list[DamageRecord],
    mode: str,
    config: Config,
) -> list[ValidationSplit]:
    """按验证模式生成切分列表。

    random / corner 返回单个切分；整层留出模式返回每层一个切分，
    聚合所有折的测试预测即可得到覆盖全部工况的诚实指标。
    """
    if mode == "random":
        splits = _random_split(records, config)
    elif mode in _LEAVE_FIELD:
        splits = _leave_field_out(records, mode)
    elif mode == "corner":
        splits = _corner_split(records, config)
    else:
        raise ValueError(f"未知验证模式: {mode}")

    for split in splits:
        if not split.train or not split.test:
            raise ValueError(f"{split.label} 产生了空训练集或空测试集")
        if len(split.train) < 4:
            raise ValueError(
                f"{split.label} 仅剩 {len(split.train)} 个训练工况；"
                "三维 RBF 至少需要 4 个且几何上独立的工况"
            )
    return splits
