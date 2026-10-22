"""无头（headless）导入守卫测试：Web/无头运行时解耦的 Phase 0 验收。

以子进程 + 元路径拦截器模拟"没有 Tkinter"的运行环境：

- 拦截 ``tkinter`` 导入（一旦被导入即抛错）
- 验证 ``storage`` / ``logging_setup`` / ``visualization.plots`` /
  ``app`` / ``webapp`` 均可在该环境下导入
- 验证 ``damage_gui.app`` 不在模块导入期拉起 matplotlib
- 验证 ``webapp`` 导入不绑定 matplotlib 后端

（2026-10 退役 Tk 桌面：``damage_gui.gui`` 子树整体删除，因此原守卫
对象 ``damage_gui.gui.main_window`` 相应移除；matplotlib 的 TkAgg
后端仍然会在 ``import matplotlib`` 时被探测，因此保留对 ``tkinter``
的拦截以避免无头服务器进程意外拉起 GUI 模块。）
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))


def _headless_env() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing if existing else "")
    return env


def _run_probe(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=_headless_env(),
        timeout=180,
    )


_HEADLESS_PROBE = textwrap.dedent(
    """
    import sys
    from importlib.abc import MetaPathFinder

    BLOCKED = ("tkinter",)

    class _Blocker(MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if any(fullname == b or fullname.startswith(b + ".") for b in BLOCKED):
                raise ImportError(f"headless guard: import of {fullname} blocked")
            return None

    sys.meta_path.insert(0, _Blocker())

    import damage_gui.storage.db  # noqa: E402
    import damage_gui.logging_setup  # noqa: E402
    import damage_gui.visualization.plots  # noqa: E402
    import damage_gui.app  # noqa: E402
    import damage_gui.webapp  # noqa: E402

    assert "tkinter" not in sys.modules, "tkinter 被无头导入链拉起"

    # 关键符号可用性：兼容 re-export 不因延迟导入而丢失
    assert damage_gui.app.DamageModelService is not None
    assert damage_gui.app.render_heatmaps is not None
    assert damage_gui.storage.db.app_base_dir is not None
    assert "damage_gui.webapp" in sys.modules
    print("HEADLESS_IMPORT_OK")
    """
)


class HeadlessImportGuardTests(unittest.TestCase):
    def test_infrastructure_modules_import_without_tk(self) -> None:
        """storage / logging_setup / plots / app / webapp 可在无 Tk 环境导入。"""
        result = _run_probe(_HEADLESS_PROBE)
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr[-2000:]}")
        self.assertIn("HEADLESS_IMPORT_OK", result.stdout)

    def test_app_import_alone_does_not_pull_tk(self) -> None:
        """仅导入 damage_gui.app 不得触发 Tk 模块加载。"""
        probe = textwrap.dedent(
            """
            import sys
            from importlib.abc import MetaPathFinder

            class _Blocker(MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == "tkinter" or fullname.startswith("tkinter."):
                        raise ImportError("blocked: " + fullname)
                    return None

            sys.meta_path.insert(0, _Blocker())

            import damage_gui.app  # noqa: E402

            assert "tkinter" not in sys.modules
            print("APP_LAZY_OK")
            """
        )
        result = _run_probe(probe)
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr[-2000:]}")
        self.assertIn("APP_LAZY_OK", result.stdout)

    def test_webapp_import_does_not_load_matplotlib(self) -> None:
        probe = textwrap.dedent(
            """
            import sys

            import damage_gui.webapp  # noqa: E402

            assert "tkinter" not in sys.modules
            assert "matplotlib" not in sys.modules
            print("WEBAPP_LAZY_OK")
            """
        )
        result = _run_probe(probe)
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr[-2000:]}")
        self.assertIn("WEBAPP_LAZY_OK", result.stdout)

    def test_plots_import_does_not_bind_backend(self) -> None:
        """导入 visualization.plots 不得改动已设定的 matplotlib 后端。

        tests/conftest.py 在 pytest 启动时设过 ``Agg``；若 plots 又把它切
        回 TkAgg 等 GUI 后端，web/headless 环境会出现假死与日志无响应。
        """
        import matplotlib

        matplotlib.use("Agg", force=True)
        before = matplotlib.get_backend()
        from damage_gui import visualization  # noqa: F401
        from damage_gui.visualization import plots  # noqa: F401
        after = matplotlib.get_backend()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
