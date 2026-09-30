"""模型注册表：joblib 模型包 + JSON 元数据 sidecar 的保存/加载与校验。"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

import joblib

from damage_gui.errors import ModelLoadError
from damage_gui.model.bundle import ModelBundle
from damage_gui.model.metadata import ModelMetadata, sidecar_path

logger = logging.getLogger("damage_gui.registry")


def save_model(bundle: ModelBundle, path: str | Path, *, overwrite: bool = True) -> Path:
    """Serialize fully before publishing; registry callers reject existing files.

    Each file is atomic, but the pair is not a filesystem transaction. Metadata is
    published first. Default replacement preserves historical Save As behavior;
    registration uses atomic no-clobber hard links on the same filesystem.
    """
    path = Path(path)
    metadata = getattr(bundle, "metadata", None)
    sidecar = sidecar_path(path)
    if not overwrite and (path.exists() or sidecar.exists()):
        raise FileExistsError(f"Model artifact already exists: {path.name}")
    temporary, published = [], []
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        os.close(fd)
        model_tmp = Path(name)
        temporary.append(model_tmp)
        joblib.dump(bundle, model_tmp)
        # Windows 的 FlushFileBuffers 要求句柄有写权限，只读 fd 会报
        # Errno 9（POSIX 允许对只读 fd fsync，故仅在 Windows CI 暴露）。
        with model_tmp.open("rb+") as stream:
            os.fsync(stream.fileno())
        if metadata is not None:
            fd, name = tempfile.mkstemp(prefix=f".{sidecar.name}.", dir=path.parent)
            meta_tmp = Path(name)
            temporary.append(meta_tmp)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(metadata.to_dict(), stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            if overwrite:
                os.replace(meta_tmp, sidecar)
            else:
                os.link(meta_tmp, sidecar)
                published.append(sidecar)
        if overwrite:
            os.replace(model_tmp, path)
        else:
            os.link(model_tmp, path)
            published.append(path)
    except Exception:
        for artifact in published:
            artifact.unlink(missing_ok=True)
        raise
    finally:
        for artifact in temporary:
            artifact.unlink(missing_ok=True)
    logger.info("Model saved: %s", path.name)
    return path


def _load_sidecar(model_path: Path) -> ModelMetadata | None:
    sidecar = sidecar_path(model_path)
    if not sidecar.is_file():
        return None
    try:
        text = sidecar.read_text(encoding="utf-8")
    except OSError as exc:
        raise ModelLoadError(
            f"元数据 sidecar 无法读取: {sidecar.name}"
        ) from exc
    if not text.strip():
        # 空文件视为写入中断（等同缺失）：回退内嵌元数据 / 旧版模型路径，
        # 不阻断加载（Phase 2.5 §39 missing-metadata model）。
        logger.warning(
            "模型 %s 的元数据 sidecar 为空文件（可能写入中断），按无元数据处理",
            model_path.name,
        )
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelLoadError(
            f"元数据 sidecar 不是合法 JSON: {sidecar.name}"
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
