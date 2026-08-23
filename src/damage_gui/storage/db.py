"""SQLite 追溯数据库：路径解析、短连接与幂等 schema。

只保存 metadata、索引和摘要；473×473 大型结果继续留在文件系统。
"""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from damage_gui.gui.resources import app_base_dir

logger = logging.getLogger("damage_gui.storage")

DB_FILE_NAME = "damage_gui.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS models (
    id                 TEXT PRIMARY KEY,
    created_at         TEXT NOT NULL,
    app_version        TEXT NOT NULL,
    model_type         TEXT NOT NULL,
    damage_level       TEXT NOT NULL,
    training_samples   INTEGER NOT NULL,
    training_data_hash TEXT NOT NULL,
    code_commit        TEXT,
    parameters_json    TEXT NOT NULL,
    validation_json    TEXT NOT NULL,
    artifact_path      TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('training', 'batch_prediction')),
    status        TEXT NOT NULL CHECK (status IN
        ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED')),
    model_id      TEXT REFERENCES models(id),
    input_source  TEXT,
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT,
    duration_ms   INTEGER,
    error_summary TEXT,
    details_json  TEXT
);

CREATE TABLE IF NOT EXISTS prediction_results (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id               TEXT NOT NULL REFERENCES jobs(id),
    row_job_id           TEXT,
    level                TEXT,
    h                    REAL,
    v                    REAL,
    deg                  REAL,
    status               TEXT NOT NULL,
    ood_level            TEXT,
    ood_distance         REAL,
    peak_intensity       REAL,
    damage_area_ratio    REAL,
    mean_relative_error  REAL,
    p95_hybrid_error     REAL,
    duration_ms          INTEGER,
    error_summary        TEXT,
    output_path          TEXT,
    created_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_kind_status ON jobs(kind, status);
CREATE INDEX IF NOT EXISTS idx_jobs_created     ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_results_job      ON prediction_results(job_id);
CREATE INDEX IF NOT EXISTS idx_models_level     ON models(damage_level);
"""


def resolve_db_path(explicit: str | Path | None = None) -> Path:
    """数据库路径：显式参数 > 环境变量 DAMAGE_GUI_DB > 应用根目录。"""
    if explicit is not None:
        return Path(explicit)
    env_value = os.environ.get("DAMAGE_GUI_DB")
    if env_value:
        return Path(env_value)
    return app_base_dir() / DB_FILE_NAME


def connect(db_path: str | Path) -> sqlite3.Connection:
    """打开短连接（每次操作独立连接，避免跨线程共享）。"""
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database(db_path: str | Path) -> bool:
    """建库建表（幂等）。失败时记录 ERROR 日志并返回 False，不抛出。"""
    try:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(connect(path)) as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        return True
    except sqlite3.Error:
        logger.exception(
            "SQLite 数据库初始化失败（%s）：追溯记录将不可用，但不影响计算功能",
            Path(db_path).name,
        )
        return False


def ensure_schema(conn: sqlite3.Connection) -> None:
    """写入操作前确保表结构存在（CREATE IF NOT EXISTS，幂等）。"""
    conn.executescript(SCHEMA_SQL)
