"""Keep generated model authentication keys inside the test runtime."""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def model_key_file(tmp_path_factory):
    old = os.environ.get("DAMAGE_GUI_MODEL_KEY_FILE")
    os.environ["DAMAGE_GUI_MODEL_KEY_FILE"] = str(tmp_path_factory.mktemp("model-keys") / "key")
    yield
    if old is None:
        os.environ.pop("DAMAGE_GUI_MODEL_KEY_FILE", None)
    else:
        os.environ["DAMAGE_GUI_MODEL_KEY_FILE"] = old
