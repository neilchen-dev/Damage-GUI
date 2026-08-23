"""统一日志：控制台 + 轮转文件（logs/damage_gui.log）。

GUI / CLI / 批量脚本启动时调用 setup_logging()；业务模块统一使用
logging.getLogger("damage_gui.xxx")。日志只记录文件名等必要信息，
不打印用户数据内容。
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from damage_gui.gui.resources import app_base_dir

LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "damage_gui.log"
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_MAX_BYTES = 1024 * 1024
_BACKUP_COUNT = 5

_configured = False


def default_log_dir() -> Path:
    return app_base_dir() / LOG_DIR_NAME


def setup_logging(
    level: int = logging.INFO, log_dir: Path | None = None
) -> logging.Logger:
    """初始化 damage_gui 根 logger（幂等，重复调用直接返回）。"""
    global _configured
    logger = logging.getLogger("damage_gui")
    if _configured:
        return logger

    logger.setLevel(level)
    logger.propagate = False
    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    directory = Path(log_dir) if log_dir is not None else default_log_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            directory / LOG_FILE_NAME,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # 日志目录不可写（如只读安装目录）不应阻断主程序，仅用控制台日志
        logger.warning("无法创建日志目录 %s，仅使用控制台日志", directory)

    _configured = True
    return logger
