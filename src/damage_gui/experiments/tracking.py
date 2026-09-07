"""SQLite 实验追踪（M3.5）：ExperimentResult 的持久化与查询。

不引入 MLflow 等外部依赖：单文件 SQLite 库，一张 ``experiments`` 表。
标量列（suite/level/model_type/status 等）用于检索，完整记录
（含配置快照与全部指标）存为 ``payload_json``，与
:meth:`ExperimentResult.to_dict` 的 CSV/JSON 输出同构。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from damage_gui.experiments.runner import ExperimentResult

#: 相对仓库根目录的默认数据库路径（CLI 与 run_experiments 共用）
DEFAULT_DB = Path("examples") / "results" / "experiments" / "experiments.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inserted_at TEXT NOT NULL,
    experiment TEXT NOT NULL,
    suite TEXT NOT NULL,
    level TEXT NOT NULL,
    model_type TEXT NOT NULL,
    validation_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""

#: list 视图精选列（指标取自 payload）
_LIST_COLUMNS = (
    "id", "inserted_at", "suite", "experiment", "level", "model_type",
    "validation_mode", "status", "mean_relative_error", "p95_hybrid_error",
    "r2", "dice", "centroid_error_m", "train_time_seconds",
)


class ExperimentStore:
    """单文件 SQLite 实验库；支持 with 语句。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ExperimentStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def record(
        self, results: list[ExperimentResult], suite: str = ""
    ) -> list[int]:
        """写入一批实验结果，返回分配的自增 id 列表。"""
        inserted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ids: list[int] = []
        for result in results:
            payload = json.dumps(result.to_dict(), ensure_ascii=False)
            cursor = self._conn.execute(
                "INSERT INTO experiments (inserted_at, experiment, suite, level,"
                " model_type, validation_mode, status, payload_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    inserted_at,
                    result.experiment,
                    result.suite or suite,
                    result.level,
                    result.model_type,
                    result.validation_mode,
                    result.status,
                    payload,
                ),
            )
            ids.append(int(cursor.lastrowid))
        self._conn.commit()
        return ids

    def list_runs(self, limit: int = 50) -> pd.DataFrame:
        """按 id 倒序返回摘要视图（新记录在前）。"""
        rows = self._conn.execute(
            "SELECT id, inserted_at, payload_json FROM experiments"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        records = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            item = {key: payload.get(key) for key in _LIST_COLUMNS}
            item["id"] = row["id"]
            item["inserted_at"] = row["inserted_at"]
            records.append(item)
        return pd.DataFrame(records, columns=list(_LIST_COLUMNS))

    def get_run(self, run_id: int) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT id, inserted_at, payload_json FROM experiments WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"实验记录不存在: id={run_id}")
        payload = json.loads(row["payload_json"])
        payload["id"] = row["id"]
        payload["inserted_at"] = row["inserted_at"]
        return payload


def compare_runs(store: ExperimentStore, run_ids: list[int]) -> pd.DataFrame:
    """并排对比若干记录的配置与指标；行=字段，列=记录。"""
    payloads = [store.get_run(run_id) for run_id in run_ids]
    columns = [f"#{p['id']} {p['experiment']}" for p in payloads]

    keys: list[str] = []
    for payload in payloads:
        for key, value in payload.items():
            if key in keys or isinstance(value, (dict, list)):
                continue
            keys.append(key)
    rows = {key: [payload.get(key) for payload in payloads] for key in keys}
    return pd.DataFrame(rows, index=columns).T
