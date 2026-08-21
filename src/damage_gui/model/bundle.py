"""模型服务：训练编排（含结构化验证）、评估与模型包管理。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from damage_gui.config import Config, CONFIG, ProgressCallback
from damage_gui.data.loader import (
    Condition,
    DamageDataManager,
    DamageRecord,
    read_damage_matrix,
)
from damage_gui.data.preprocessing import evaluation_fields, roi_description, roi_mask_for_shape
from damage_gui.evaluation.metrics import SPATIAL_KEYS, metric_row, spatial_metrics
from damage_gui.model.ood import OODDetector
from damage_gui.model.pod import PODRBFDamageField
from damage_gui.model.rbf import RBFDamageField
from damage_gui.model.validation import make_splits

DamageFieldModel = RBFDamageField | PODRBFDamageField


class TrainingCancelled(RuntimeError):
    """用户取消训练时抛出。"""


@dataclass
class ModelBundle:
    """可持久化（joblib）的完整模型包。"""

    level: str
    data_dir: str
    target_shape: tuple[int, int]
    config: dict
    model: DamageFieldModel
    train_conditions: list[dict[str, float]]
    test_conditions: list[dict[str, float]]
    accuracy_report: pd.DataFrame = field(default_factory=pd.DataFrame)
    condition_report: pd.DataFrame = field(default_factory=pd.DataFrame)
    ood_detector: OODDetector | None = None
    validation_mode: str = "random"
    model_type: str = "rbf"
    train_time_seconds: float = 0.0

    def resolved_config(self) -> Config:
        """恢复训练时配置；兼容字段增减以及早期模型包。"""
        return Config.from_mapping(getattr(self, "config", None))


def build_model(
    model_type: str,
    config: Config,
    pod_n_components: int | None = None,
) -> DamageFieldModel:
    """按类型构建毁伤场模型。"""
    if model_type == "pod_rbf":
        return PODRBFDamageField(
            kernel=config.rbf_kernel,
            smoothing=config.rbf_smoothing,
            target_shape=config.target_shape,
            align=config.align_patterns,
            n_components=pod_n_components or config.pod_n_components,
            config=config,
        )
    if model_type == "rbf":
        return RBFDamageField(
            kernel=config.rbf_kernel,
            smoothing=config.rbf_smoothing,
            target_shape=config.target_shape,
            align=config.align_patterns,
            config=config,
        )
    raise ValueError(f"未知模型类型: {model_type}")


class DamageModelService:
    def __init__(self, data_manager: DamageDataManager, config: Config | None = None):
        self.data_manager = data_manager
        self.config = config or CONFIG

    # ---------- 训练 ----------

    def train_bundle(
        self,
        level: str,
        validation_mode: str | None = None,
        model_type: str | None = None,
        pod_n_components: int | None = None,
        progress: ProgressCallback | None = None,
        cancel_check=None,
    ) -> ModelBundle:
        """训练并评估模型。

        验证模式：
        - random / corner：单次切分，交付模型在训练部分上训练；
        - 整层留出（leave_*_out）：对每层训练一个模型并聚合折外预测得到
          诚实指标，交付模型最终在全部工况上重新训练（折外指标衡量方法
          的泛化能力，交付模型使用全部可用数据）。

        cancel_check：无参可调用对象，返回 True 时抛出 TrainingCancelled。
        """
        config = self.config
        validation_mode = validation_mode or config.validation_mode
        model_type = model_type or config.model_type
        started = time.perf_counter()

        def check_cancel() -> None:
            if cancel_check is not None and cancel_check():
                raise TrainingCancelled("用户取消训练")

        records = self.data_manager.get_level_records(level)
        if len(records) < 5:
            raise ValueError("可训练工况过少，至少需要 5 个工况")

        splits = make_splits(records, validation_mode, config)
        is_loo = validation_mode in ("leave_h_out", "leave_v_out", "leave_deg_out")

        # 矩阵读取缓存：整层留出会多次访问同一条记录，避免重复解析文件
        matrix_cache: dict[Path, np.ndarray] = {}

        def load_matrix(record: DamageRecord) -> np.ndarray:
            if record.path not in matrix_cache:
                matrix_cache[record.path] = read_damage_matrix(record.path, config)
            return matrix_cache[record.path]

        total_units = sum(len(s.train) for s in splits) + sum(len(s.test) for s in splits)
        if is_loo:
            total_units += len(records)  # 最终全量重训练的读取
        done = 0

        def report(msg: str) -> None:
            if progress is not None:
                progress(done, total_units, msg)

        pairs: list[tuple[DamageRecord, np.ndarray, np.ndarray]] = []
        deliverable_model: DamageFieldModel | None = None
        deliverable_train_records: list[DamageRecord] = []

        for split_index, split in enumerate(splits):
            prefix = (
                f"[{split_index + 1}/{len(splits)}] " if len(splits) > 1 else ""
            )
            conditions = np.zeros((len(split.train), 3), dtype=np.float64)
            matrices = np.zeros(
                (len(split.train), *config.target_shape), dtype=np.float32
            )
            for i, record in enumerate(split.train):
                matrices[i] = load_matrix(record)
                conditions[i] = record.condition.as_array()
                done += 1
                report(f"{prefix}读取训练矩阵 {i + 1}/{len(split.train)}")
            check_cancel()

            model_name = "POD-RBF" if model_type == "pod_rbf" else "RBF"
            report(f"{prefix}拟合 {model_name} 插值场...")
            model = build_model(model_type, config, pod_n_components)
            model.fit(conditions, matrices)
            check_cancel()

            for i, record in enumerate(split.test):
                true_matrix = load_matrix(record)
                pred_matrix = model.predict_matrix(record.condition)
                pairs.append((record, true_matrix, pred_matrix))
                done += 1
                report(f"{prefix}评估测试工况 {i + 1}/{len(split.test)}")
            check_cancel()

            if not is_loo:
                deliverable_model = model
                deliverable_train_records = list(split.train)

        if is_loo:
            # 折外指标已聚合完毕；交付模型使用全部工况重新训练
            conditions = np.zeros((len(records), 3), dtype=np.float64)
            matrices = np.zeros((len(records), *config.target_shape), dtype=np.float32)
            for i, record in enumerate(records):
                matrices[i] = load_matrix(record)
                conditions[i] = record.condition.as_array()
                done += 1
                report(f"读取全量矩阵 {i + 1}/{len(records)}")
            check_cancel()
            report("在全部工况上拟合交付模型...")
            deliverable_model = build_model(model_type, config, pod_n_components)
            deliverable_model.fit(conditions, matrices)
            deliverable_train_records = list(records)

        assert deliverable_model is not None

        accuracy_report, condition_report = self._evaluate_pairs(level, pairs)

        ood_detector = OODDetector(
            high_max=config.ood_high_max,
            medium_max=config.ood_medium_max,
            use_hull=config.ood_use_hull,
            use_local_support=config.ood_use_local_support,
            local_neighbors=config.ood_local_neighbors,
            max_1d_gap_ratio=config.ood_max_1d_gap_ratio,
        )
        ood_detector.fit(
            np.array(
                [record.condition.as_array() for record in deliverable_train_records],
                dtype=np.float64,
            )
        )

        test_records = records if is_loo else splits[0].test

        return ModelBundle(
            level=level,
            data_dir=str(self.data_manager.data_dir),
            target_shape=config.target_shape,
            config=config.__dict__.copy(),
            model=deliverable_model,
            train_conditions=[r.condition.as_dict() for r in deliverable_train_records],
            test_conditions=[r.condition.as_dict() for r in test_records],
            accuracy_report=accuracy_report,
            condition_report=condition_report,
            ood_detector=ood_detector,
            validation_mode=validation_mode,
            model_type=model_type,
            train_time_seconds=time.perf_counter() - started,
        )

    def predict_matrix(self, bundle: ModelBundle, condition: Condition) -> np.ndarray:
        return bundle.model.predict_matrix(condition)

    # ---------- 评估 ----------

    def _evaluate_pairs(
        self,
        level: str,
        pairs: list[tuple[DamageRecord, np.ndarray, np.ndarray]],
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """对 (记录, 真值, 预测) 列表做 Raw / Smoothed 双口径 + 空间指标评估。

        预测已在训练循环中完成并计入进度，此处仅做指标汇总，不再上报进度。
        """
        config = self.config
        condition_rows: list[dict] = []
        # (field, scope) -> list of flattened arrays
        scope_true_parts: dict[tuple[str, str], list[np.ndarray]] = {}
        scope_pred_parts: dict[tuple[str, str], list[np.ndarray]] = {}
        spatial_parts: dict[str, list[float]] = {key: [] for key in SPATIAL_KEYS}

        scopes: list[tuple[str, float]] = [("overall", config.eval_area_threshold)]
        scopes += [
            (f"damage_gt_{threshold:.2f}", threshold)
            for threshold in config.eval_focus_thresholds
        ]
        scope_defs = [name for name, _ in scopes] + ["roi_overall"]

        for index, (record, true_matrix, pred_matrix) in enumerate(pairs):
            smoothed_true, smoothed_pred = evaluation_fields(
                true_matrix, pred_matrix, config
            )
            row: dict = {
                "level": level,
                "h": record.condition.h,
                "v": record.condition.v,
                "deg": record.condition.deg,
                "ROI": roi_description(config),
            }

            # 兼容列：与旧版一致在 Smoothed 场上计算
            y_true = smoothed_true.ravel()
            y_pred = smoothed_pred.ravel()
            roi_flat_mask = roi_mask_for_shape(true_matrix.shape, config).ravel()
            row.update(
                metric_row(
                    "overall", y_true, y_pred, config.eval_area_threshold, config
                )
            )
            roi_metrics = metric_row(
                "roi_overall",
                y_true[roi_flat_mask],
                y_pred[roi_flat_mask],
                config.eval_area_threshold,
                config,
            )
            row["ROI_MSE"] = roi_metrics["MSE"]
            row["ROI_RMSE"] = roi_metrics["RMSE"]
            row["ROI_MAE"] = roi_metrics["MAE"]
            row["ROI_R2"] = roi_metrics["R2"]
            row["ROI_MaxError"] = roi_metrics["MaxError"]
            row["ROI_TrueDamageAreaRatio"] = roi_metrics["TrueDamageAreaRatio"]
            row["ROI_PredDamageAreaRatio"] = roi_metrics["PredDamageAreaRatio"]
            row["ROI_AreaRatioGap"] = roi_metrics["AreaRatioGap"]

            for threshold in config.eval_focus_thresholds:
                mask = y_true > threshold
                scope_metrics = metric_row(
                    f"damage_gt_{threshold:.2f}",
                    y_true[mask],
                    y_pred[mask],
                    threshold,
                    config,
                )
                suffix = f"_gt_{threshold:.2f}"
                # 列名沿用旧版（TrueAreaRatio/PredAreaRatio），源键为 TrueDamageAreaRatio
                for key in (
                    "MSE", "RMSE", "MAE", "R2", "MaxError",
                    "MeanRelativeError", "P90RelativeError", "MaxRelativeError",
                    "P95HybridError", "MaxHybridError", "HybridAccuracyInTarget",
                ):
                    row[f"{key}{suffix}"] = scope_metrics[key]
                row[f"TrueAreaRatio{suffix}"] = scope_metrics["TrueDamageAreaRatio"]
                row[f"PredAreaRatio{suffix}"] = scope_metrics["PredDamageAreaRatio"]

            # Raw 口径主要毁伤区指标（逐像素一致性）
            raw_true = true_matrix.ravel()
            raw_pred = pred_matrix.ravel()
            for threshold in config.eval_focus_thresholds:
                mask = raw_true > threshold
                suffix = f"_gt_{threshold:.2f}"
                if np.any(mask):
                    raw_metrics = metric_row(
                        f"damage_gt_{threshold:.2f}",
                        raw_true[mask],
                        raw_pred[mask],
                        threshold,
                        config,
                    )
                    row[f"RawMeanRelativeError{suffix}"] = raw_metrics["MeanRelativeError"]
                    row[f"RawP95HybridError{suffix}"] = raw_metrics["P95HybridError"]
                else:
                    row[f"RawMeanRelativeError{suffix}"] = np.nan
                    row[f"RawP95HybridError{suffix}"] = np.nan

            # 空间场指标（Raw 场）
            cols = true_matrix.shape[1]
            rows_count = true_matrix.shape[0]
            pixel_x = (config.coord_max - config.coord_min) / max(cols - 1, 1)
            pixel_y = (config.coord_max - config.coord_min) / max(rows_count - 1, 1)
            spat = spatial_metrics(
                true_matrix,
                pred_matrix,
                config.relative_error_threshold,
                pixel_x,
                pixel_y,
            )
            for key, value in spat.items():
                row[f"Spat_{key}"] = value
                if not np.isnan(value):
                    spatial_parts[key].append(value)

            condition_rows.append(row)

            # 汇总累积（Raw / Smoothed 双口径）
            def accumulate(field_name: str, field_true: np.ndarray, field_pred: np.ndarray) -> None:
                scope_true_parts.setdefault((field_name, "overall"), []).append(field_true)
                scope_pred_parts.setdefault((field_name, "overall"), []).append(field_pred)
                scope_true_parts.setdefault((field_name, "roi_overall"), []).append(
                    field_true[roi_flat_mask]
                )
                scope_pred_parts.setdefault((field_name, "roi_overall"), []).append(
                    field_pred[roi_flat_mask]
                )
                for threshold in config.eval_focus_thresholds:
                    mask = field_true > threshold
                    scope_name = f"damage_gt_{threshold:.2f}"
                    scope_true_parts.setdefault((field_name, scope_name), []).append(
                        field_true[mask]
                    )
                    scope_pred_parts.setdefault((field_name, scope_name), []).append(
                        field_pred[mask]
                    )

            accumulate("raw", true_matrix.ravel(), pred_matrix.ravel())
            accumulate("smoothed", smoothed_true.ravel(), smoothed_pred.ravel())

        # 汇总 accuracy report：scope × field 双口径
        accuracy_rows: list[dict] = []
        for scope_name in scope_defs:
            for field_name in ("raw", "smoothed"):
                true_concat = np.concatenate(scope_true_parts[(field_name, scope_name)])
                pred_concat = np.concatenate(scope_pred_parts[(field_name, scope_name)])
                if scope_name.startswith("damage_gt_"):
                    threshold = float(scope_name.rsplit("_", 1)[1])
                else:
                    threshold = config.eval_area_threshold
                accuracy_rows.append(
                    {
                        **metric_row(
                            scope_name, true_concat, pred_concat, threshold, config
                        ),
                        "field": field_name,
                    }
                )

        # 空间指标汇总行
        spatial_row: dict = {key: np.nan for key in accuracy_rows[0]}
        spatial_row["scope"] = "spatial"
        spatial_row["field"] = "raw"
        spatial_row["points"] = len(pairs)
        for key in SPATIAL_KEYS:
            values = spatial_parts[key]
            spatial_row[key] = float(np.mean(values)) if values else np.nan
        accuracy_rows.append(spatial_row)

        accuracy_report = pd.DataFrame(accuracy_rows)
        accuracy_report.insert(0, "level", level)
        if "field" in accuracy_report.columns:
            field_col = accuracy_report.pop("field")
            accuracy_report.insert(1, "field", field_col)
        condition_report = pd.DataFrame(condition_rows)
        return accuracy_report, condition_report
