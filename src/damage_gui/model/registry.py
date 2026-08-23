"""模型注册表：joblib 模型包 + JSON 元数据 sidecar 的保存/加载与校验。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib

from damage_gui.errors import ModelLoadError
from damage_gui.model.bundle import ModelBundle
from damage_gui.model.metadata import ModelMetadata, sidecar_path

logger = logging.getLogger("damage_gui.registry")


def save_model(bundle: ModelBundle, path: str | Path) -> Path:
    """保存模型：joblib 主文件 + *.meta.json 元数据 sidecar。"""
    path = Path(path)
    joblib.dump(bundle, path)
    metadata = getattr(bundle, "metadata", None)
    if metadata is None:
        logger.warning(
            "模型 %s 不含元数据（旧版训练产物），仅保存 joblib 主文件", path.name
        )
        return path
    sidecar = sidecar_path(path)
    sidecar.write_text(
        json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "模型已保存: %s (model_id=%s, app=%s)",
        path.name, metadata.model_id[:8], metadata.app_version,
    )
    return path


def _load_sidecar(model_path: Path) -> ModelMetadata | None:
    sidecar = sidecar_path(model_path)
    if not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelLoadError(
            f"元数据 sidecar 无法读取或不是合法 JSON: {sidecar.name}"
        ) from exc
    return ModelMetadata.from_dict(data)


def load_model(path: str | Path) -> ModelBundle:
    """加载并校验模型。

    - 文件不存在 / 损坏 / 不是 ModelBundle → ModelLoadError（明确中文错误）
    - sidecar 与内嵌元数据 model_id 不一致 → ModelLoadError
    - 旧版模型（无元数据）：允许加载，日志提示无追溯信息
    """
    model_path = Path(path)
    if not model_path.is_file():
        raise ModelLoadError(f"模型文件不存在: {model_path.name}")
    try:
        bundle = joblib.load(model_path)
    except Exception as exc:  # noqa: BLE001 —— 反序列化失败统一转为可读错误
        raise ModelLoadError(
            f"模型文件损坏或与当前软件版本不兼容: {model_path.name}"
        ) from exc
    if not isinstance(bundle, ModelBundle):
        raise ModelLoadError(f"模型文件格式不正确（不是 ModelBundle）: {model_path.name}")

    metadata = _load_sidecar(model_path)
    embedded = getattr(bundle, "metadata", None)
    if metadata is None:
        if embedded is None:
            logger.warning(
                "模型 %s 为旧版格式（无元数据），已加载但不具备版本追溯信息",
                model_path.name,
            )
        else:
            metadata = embedded
    elif embedded is not None and embedded.model_id != metadata.model_id:
        raise ModelLoadError(
            f"模型文件与元数据 sidecar 不匹配（model_id 不一致）: {model_path.name}，"
            "两者可能来自不同的训练产物"
        )
    if metadata is not None:
        bundle.metadata = metadata
        logger.info(
            "模型已加载: %s (model_id=%s, app=%s)",
            model_path.name, metadata.model_id[:8], metadata.app_version,
        )
    return bundle
