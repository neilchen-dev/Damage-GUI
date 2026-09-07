"""模型生命周期管理（M3.6）：DRAFT → VALIDATED → ACTIVE → ARCHIVED。

- 家族（family）= 毁伤等级（F/M/P），**同一等级至多一个 ACTIVE**：
  晋升新模型时，同等级原 ACTIVE 在同一事务内自动归档；
- 登记只读元数据 sidecar（*.meta.json），不加载 joblib 主文件；
  无元数据的旧格式模型没有可追溯身份，拒绝登记并说明原因；
- 存储为单文件 SQLite，不依赖外部服务。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from damage_gui.errors import LifecycleError, ModelLoadError
from damage_gui.model.metadata import ModelMetadata, sidecar_path

MODEL_STATES = ("DRAFT", "VALIDATED", "ACTIVE", "ARCHIVED")

#: 合法状态转移；任何状态都可直接归档，归档为终态
_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "DRAFT": ("VALIDATED", "ARCHIVED"),
    "VALIDATED": ("ACTIVE", "ARCHIVED"),
    "ACTIVE": ("ARCHIVED",),
    "ARCHIVED": (),
}

#: 相对仓库根目录的默认生命周期库路径（CLI 使用）
DEFAULT_LIFECYCLE_DB = Path("examples") / "results" / "model_lifecycle.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL UNIQUE,
    level TEXT NOT NULL,
    model_type TEXT NOT NULL,
    model_path TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    registered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_LIST_COLUMNS = (
    "id", "status", "level", "model_type", "model_id", "model_path",
    "notes", "registered_at", "updated_at",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_sidecar_metadata(model_path: Path) -> ModelMetadata:
    sidecar = sidecar_path(model_path)
    if not sidecar.is_file():
        raise LifecycleError(
            f"模型缺少元数据 sidecar（{sidecar.name}），无法纳入生命周期管理；"
            "旧格式模型请先用当前版本重新训练"
        )
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"元数据 sidecar 无法读取或不是合法 JSON: {sidecar.name}") from exc
    try:
        return ModelMetadata.from_dict(data)
    except ModelLoadError as exc:
        raise LifecycleError(str(exc)) from exc


class ModelRegistry:
    """模型生命周期登记库（单文件 SQLite）；支持 with 语句。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ModelRegistry:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def register(self, model_path: str | Path, notes: str = "") -> int:
        """登记一个已保存的模型，初始状态 DRAFT，返回行 id。"""
        model_path = Path(model_path)
        if not model_path.is_file():
            raise LifecycleError(f"模型文件不存在: {model_path}")
        metadata = _read_sidecar_metadata(model_path)
        now = _utc_now_iso()
        try:
            cursor = self._conn.execute(
                "INSERT INTO models (model_id, level, model_type, model_path,"
                " status, notes, registered_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'DRAFT', ?, ?, ?)",
                (
                    metadata.model_id,
                    metadata.damage_level,
                    metadata.model_type,
                    str(model_path),
                    notes,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise LifecycleError(
                f"模型已登记（model_id={metadata.model_id[:8]}…），不能重复注册"
            ) from exc
        self._conn.commit()
        return int(cursor.lastrowid)

    def get(self, row_id: int) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM models WHERE id = ?", (row_id,)
        ).fetchone()
        if row is None:
            raise LifecycleError(f"模型登记记录不存在: id={row_id}")
        return dict(row)

    def transition(self, row_id: int, target: str, notes: str | None = None) -> dict[str, Any]:
        """按状态机转移；晋升 ACTIVE 时同事务归档同等级原 ACTIVE。"""
        if target not in MODEL_STATES:
            raise LifecycleError(
                f"未知状态: {target}（合法状态: {', '.join(MODEL_STATES)}）"
            )
        record = self.get(row_id)
        current = record["status"]
        if target == current:
            raise LifecycleError(f"模型 id={row_id} 已处于 {current} 状态")
        if target not in _TRANSITIONS[current]:
            allowed = ", ".join(_TRANSITIONS[current]) or "无（终态）"
            raise LifecycleError(
                f"非法状态转移: {current} → {target}"
                f"（id={row_id}，{current} 只允许转移到: {allowed}）"
            )
        now = _utc_now_iso()
        replaced: list[int] = []
        if target == "ACTIVE":
            actives = self._conn.execute(
                "SELECT id FROM models WHERE level = ? AND status = 'ACTIVE'",
                (record["level"],),
            ).fetchall()
            replaced = [int(row["id"]) for row in actives]
            for old_id in replaced:
                self._conn.execute(
                    "UPDATE models SET status = 'ARCHIVED',"
                    " notes = notes || ? , updated_at = ? WHERE id = ?",
                    (f"；被 id={row_id} 替换下线", now, old_id),
                )
        self._conn.execute(
            "UPDATE models SET status = ?, updated_at = ?,"
            " notes = CASE WHEN ? IS NULL THEN notes ELSE ? END WHERE id = ?",
            (target, now, notes, notes, row_id),
        )
        self._conn.commit()
        updated = self.get(row_id)
        updated["replaced"] = replaced
        return updated

    def active(self, level: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id FROM models WHERE level = ? AND status = 'ACTIVE'",
            (level,),
        ).fetchone()
        return None if row is None else self.get(int(row["id"]))

    def list_models(
        self, level: str | None = None, status: str | None = None
    ) -> pd.DataFrame:
        query = "SELECT * FROM models"
        clauses, params = [], []
        if level is not None:
            clauses.append("level = ?")
            params.append(level)
        if status is not None:
            if status not in MODEL_STATES:
                raise LifecycleError(f"未知状态: {status}")
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id"
        rows = self._conn.execute(query, params).fetchall()
        return pd.DataFrame([dict(row) for row in rows], columns=list(_LIST_COLUMNS))
