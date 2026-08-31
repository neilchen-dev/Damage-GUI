"""Server-owned dependencies: model discovery/cache and bounded result state."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from damage_gui.webapp.errors import (
    InvalidIdentifierError,
    ModelNotFoundError,
    ModelUnavailableError,
    ResultNotFoundError,
)

logger = logging.getLogger("damage_gui.web")
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RUN_ID_RE = MODEL_ID_RE


@dataclass(frozen=True)
class ModelDescriptor:
    """Public model metadata plus an internal server-owned artifact path."""

    model_id: str
    path: Path | None
    metadata: dict[str, Any] | None

    @property
    def metadata_available(self) -> bool:
        return self.metadata is not None


@dataclass(frozen=True)
class StoredPrediction:
    run_id: str
    model_id: str
    result: Any
    config: Any
    created_at: str
    response: dict[str, Any] | None = None


def _safe_id(value: str, *, kind: str) -> str:
    if not isinstance(value, str) or RUN_ID_RE.fullmatch(value) is None:
        raise InvalidIdentifierError(f"{kind} 标识符格式无效")
    return value


class ModelManager:
    """Discover and lazily cache models from a server-configured directory.

    Client requests can select only a discovered identifier.  They can never
    provide an artifact path.  The optional ``initial_bundles`` hook is useful
    for embedding and tests; production callers should use ``model_dir``.
    """

    def __init__(
        self,
        model_dir: str | Path | None = None,
        *,
        default_model_id: str | None = None,
        loader: Callable[[Path], Any] | None = None,
        initial_bundles: Mapping[str, Any] | None = None,
    ) -> None:
        self.model_dir = Path(model_dir).resolve() if model_dir is not None else None
        self.default_model_id = (
            _safe_id(default_model_id, kind="model") if default_model_id else None
        )
        self._loader = loader
        self._initial_bundles = dict(initial_bundles or {})
        for model_id in self._initial_bundles:
            _safe_id(model_id, kind="model")
        self._cache: dict[str, Any] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _read_metadata(path: Path) -> dict[str, Any] | None:
        sidecar = path.with_suffix(".meta.json")
        if not sidecar.is_file():
            return None
        try:
            value = json.loads(sidecar.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return None
            return value
        except (OSError, ValueError, json.JSONDecodeError):
            logger.warning("Ignoring unreadable model metadata sidecar: %s", sidecar.name)
            return None

    def _discover(self) -> list[ModelDescriptor]:
        if self._initial_bundles:
            descriptors: list[ModelDescriptor] = []
            for model_id, bundle in sorted(self._initial_bundles.items()):
                metadata = getattr(bundle, "metadata", None)
                descriptors.append(
                    ModelDescriptor(
                        model_id=model_id,
                        path=None,
                        metadata=metadata.to_dict() if metadata is not None else None,
                    )
                )
            return descriptors

        if self.model_dir is None or not self.model_dir.is_dir():
            return []
        descriptors = []
        seen: set[str] = set()
        try:
            paths = sorted(self.model_dir.iterdir(), key=lambda item: item.name.lower())
        except OSError as exc:
            logger.warning("Unable to discover models: %s", exc)
            return []
        for path in paths:
            if (
                path.is_symlink()
                or not path.is_file()
                or path.suffix.lower() != ".joblib"
            ):
                continue
            try:
                if path.resolve().parent != self.model_dir:
                    logger.warning("Ignoring model outside configured directory: %s", path.name)
                    continue
            except OSError:
                continue
            metadata = self._read_metadata(path)
            candidate = str(metadata.get("model_id")) if metadata else path.stem
            if MODEL_ID_RE.fullmatch(candidate) is None or candidate in seen:
                logger.warning("Ignoring model with unsafe or duplicate id: %s", path.name)
                continue
            seen.add(candidate)
            descriptors.append(ModelDescriptor(candidate, path, metadata))
        return descriptors

    def list_models(self) -> list[ModelDescriptor]:
        with self._lock:
            return self._discover()

    def get_descriptor(self, model_id: str) -> ModelDescriptor:
        model_id = _safe_id(model_id, kind="model")
        for descriptor in self.list_models():
            if descriptor.model_id == model_id:
                return descriptor
        raise ModelNotFoundError(f"模型不存在: {model_id}")

    def active_model_id(self) -> str | None:
        descriptors = self.list_models()
        if not descriptors:
            return None
        if self.default_model_id is not None:
            if any(item.model_id == self.default_model_id for item in descriptors):
                return self.default_model_id
            logger.warning("Configured default model is not available: %s", self.default_model_id)
        return descriptors[0].model_id

    def get_bundle(self, model_id: str | None = None) -> tuple[str, Any, ModelDescriptor]:
        resolved_id = model_id or self.active_model_id()
        if resolved_id is None:
            raise ModelUnavailableError("没有可用模型")
        descriptor = self.get_descriptor(resolved_id)
        with self._lock:
            if resolved_id in self._cache:
                return resolved_id, self._cache[resolved_id], descriptor
            if resolved_id in self._initial_bundles:
                bundle = self._initial_bundles[resolved_id]
            elif descriptor.path is not None:
                try:
                    if self._loader is None:
                        from damage_gui.model.registry import load_model

                        loader = load_model
                    else:
                        loader = self._loader
                    bundle = loader(descriptor.path)
                except Exception as exc:  # noqa: BLE001 - public error is sanitized
                    logger.exception("Model load failed for %s", resolved_id)
                    raise ModelUnavailableError("模型加载失败") from exc
            else:
                raise ModelUnavailableError("模型当前不可用")
            self._cache[resolved_id] = bundle
            return resolved_id, bundle, descriptor


class ResultStore:
    """Bounded result cache with server-owned disk retention for reopen."""

    RETENTION_DAYS = 7

    def __init__(
        self,
        max_results: int = 128,
        result_dir: str | Path | None = None,
        retention_days: int = RETENTION_DAYS,
    ) -> None:
        self.max_results = max(1, int(max_results))
        self.result_dir = Path(result_dir).resolve() if result_dir is not None else None
        self.retention_days = max(1, int(retention_days))
        self._items: OrderedDict[str, StoredPrediction] = OrderedDict()
        self._lock = threading.RLock()
        self._render_lock = threading.Lock()
        self._cleanup_old_artifacts()

    def put(
        self,
        *,
        model_id: str,
        result: Any,
        config: Any,
        run_id: str | None = None,
    ) -> StoredPrediction:
        run_id = run_id or uuid.uuid4().hex
        item = StoredPrediction(
            run_id=run_id,
            model_id=model_id,
            result=result,
            config=config,
            created_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        )
        with self._lock:
            self._items[run_id] = item
            while len(self._items) > self.max_results:
                self._items.popitem(last=False)
        return item

    def get(self, run_id: str) -> StoredPrediction:
        _safe_id(run_id, kind="result")
        with self._lock:
            item = self._items.get(run_id)
        if item is None:
            item = self._load_persistent(run_id)
        if item is None:
            raise ResultNotFoundError()
        return item

    def persist(self, item: StoredPrediction, response: dict[str, Any]) -> StoredPrediction:
        """Persist trusted prediction data and return the response-aware cache item."""
        updated = replace(item, response=dict(response))
        with self._lock:
            self._items[item.run_id] = updated
            self._items.move_to_end(item.run_id)
            while len(self._items) > self.max_results:
                self._items.popitem(last=False)

        if self.result_dir is None:
            return updated
        artifact_dir = self._artifact_dir(item.run_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_json(artifact_dir / "response.json", response)
        self._atomic_json(artifact_dir / "config.json", self._config_dict(item.config))
        self._atomic_npy(artifact_dir / "prediction.npy", item.result.prediction)
        if item.result.truth is not None:
            self._atomic_npy(artifact_dir / "truth.npy", item.result.truth)
        else:
            (artifact_dir / "truth.npy").unlink(missing_ok=True)

        from damage_gui.webapp.render import prediction_csv

        self._atomic_bytes(artifact_dir / "result.csv", prediction_csv(item))
        return updated

    def ensure_png(self, item: StoredPrediction) -> bytes:
        """Render once, cache on disk, and serialize Matplotlib access."""
        if self.result_dir is not None:
            path = self._artifact_dir(item.run_id) / "result.png"
            if path.is_file():
                return path.read_bytes()
        with self._render_lock:
            if self.result_dir is not None:
                path = self._artifact_dir(item.run_id) / "result.png"
                if path.is_file():
                    return path.read_bytes()
            from damage_gui.webapp.render import prediction_png

            content = prediction_png(item)
            if self.result_dir is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                self._atomic_bytes(path, content)
            return content

    def csv_bytes(self, item: StoredPrediction) -> bytes:
        if self.result_dir is not None:
            path = self._artifact_dir(item.run_id) / "result.csv"
            if path.is_file():
                return path.read_bytes()
        from damage_gui.webapp.render import prediction_csv

        content = prediction_csv(item)
        if self.result_dir is not None:
            path = self._artifact_dir(item.run_id) / "result.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_bytes(path, content)
        return content

    def _artifact_dir(self, run_id: str) -> Path:
        _safe_id(run_id, kind="result")
        if self.result_dir is None:
            raise ResultNotFoundError()
        return self.result_dir / "predictions" / run_id

    def _load_persistent(self, run_id: str) -> StoredPrediction | None:
        if self.result_dir is None:
            return None
        artifact_dir = self._artifact_dir(run_id)
        response_path = artifact_dir / "response.json"
        matrix_path = artifact_dir / "prediction.npy"
        config_path = artifact_dir / "config.json"
        if not response_path.is_file() or not matrix_path.is_file() or not config_path.is_file():
            return None
        try:
            response = json.loads(response_path.read_text(encoding="utf-8"))
            config_data = json.loads(config_path.read_text(encoding="utf-8"))
            from types import SimpleNamespace

            import numpy as np

            prediction = np.load(matrix_path, allow_pickle=False)
            truth_path = artifact_dir / "truth.npy"
            truth = np.load(truth_path, allow_pickle=False) if truth_path.is_file() else None
            from damage_gui.config import Config

            item = StoredPrediction(
                run_id=run_id,
                model_id=str(response["model"]["model_id"]),
                result=SimpleNamespace(prediction=prediction, truth=truth),
                config=Config.from_mapping(config_data),
                created_at=str(response.get("created_at") or ""),
                response=response,
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            logger.warning("Ignoring incomplete web result artifact: %s", run_id)
            return None
        with self._lock:
            self._items[run_id] = item
            self._items.move_to_end(run_id)
            while len(self._items) > self.max_results:
                self._items.popitem(last=False)
        return item

    @staticmethod
    def _config_dict(config: Any) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(config)

    @staticmethod
    def _atomic_bytes(path: Path, content: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _atomic_json(cls, path: Path, content: Any) -> None:
        cls._atomic_bytes(path, json.dumps(content, ensure_ascii=False).encode("utf-8"))

    @classmethod
    def _atomic_npy(cls, path: Path, content: Any) -> None:
        import io

        import numpy as np

        buffer = io.BytesIO()
        np.save(buffer, content, allow_pickle=False)
        cls._atomic_bytes(path, buffer.getvalue())

    def _cleanup_old_artifacts(self) -> None:
        if self.result_dir is None:
            return
        root = self.result_dir / "predictions"
        if not root.is_dir():
            return
        cutoff = datetime.now(timezone.utc).timestamp() - self.retention_days * 86400
        try:
            for child in root.iterdir():
                if child.is_dir() and child.stat().st_mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
        except OSError:
            logger.warning("Unable to clean old web result artifacts")


@dataclass
class WebContext:
    model_manager: ModelManager
    result_store: ResultStore
    db_path: Path
    data_dir: Path | None = None
    result_dir: Path | None = None
    retention_days: int = ResultStore.RETENTION_DAYS
