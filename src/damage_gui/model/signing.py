"""Authenticate model bytes before executable joblib deserialization.

The HMAC key is operator-owned and must never accompany untrusted artifacts.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from damage_gui.errors import ModelLoadError
from damage_gui.runtime.paths import _user_data_dir


def signature_path(path: Path) -> Path:
    return path.with_name(path.name + ".sig")


def signing_key(*, create: bool = False) -> bytes:
    configured = os.environ.get("DAMAGE_GUI_MODEL_KEY_FILE")
    path = Path(configured).expanduser() if configured else _user_data_dir() / "model-signing.key"
    if create and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as handle:
                handle.write(secrets.token_bytes(32))
                handle.flush()
                os.fsync(handle.fileno())
    try:
        key = path.read_bytes()
    except OSError as exc:
        raise ModelLoadError("模型验证密钥不可用，请配置 DAMAGE_GUI_MODEL_KEY_FILE") from exc
    if len(key) != 32:
        raise ModelLoadError("模型验证密钥必须为 32 字节")
    return key


def digest(content: bytes, *, create_key: bool = False) -> str:
    return hmac.new(signing_key(create=create_key), content, hashlib.sha256).hexdigest()


def verify_model(path: Path, content: bytes) -> None:
    try:
        signature = signature_path(path).read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise ModelLoadError("模型缺少可信签名；请由管理员核验来源后签名") from exc
    if not hmac.compare_digest(signature, digest(content)):
        raise ModelLoadError("模型签名不匹配，文件可能损坏或来自不可信来源")


def sign_existing_model(path: str | Path) -> Path:
    """Operator-only migration: approve trusted bytes without loading the model."""
    path = Path(path)
    signature = signature_path(path)
    signature.write_text(digest(path.read_bytes(), create_key=True), encoding="ascii")
    return signature
