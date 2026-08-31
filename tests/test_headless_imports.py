"""无头（headless）导入守卫测试：Web/无头运行时解耦的 Phase 0 验收。

以子进程 + 元路径拦截器模拟"没有 Tkinter"的运行环境：
- 拦截 tkinter 及 damage_gui.gui.main_window 的导入（一旦被导入即抛错）；
- 验证 storage / logging_setup / visualization.plots / app 及
  gui.resources 兼容 shim 均可在该环境下导入；
- 验证 damage_gui.app 不在模块导入期拉起 Tk GUI；
- 验证 plots 导入不绑定 matplotlib 后端、不加载 TkAgg backend 模块。
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

    BLOCKED = ("tkinter", "damage_gui.gui.main_window")


    class _Blocker(MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if any(fullname == b or fullname.startswith(b + ".") for b in BLOCKED):
                raise ImportError(f"headless guard: import of {fullname} blocked")
            return None


    sys.meta_path.insert(0, _Blocker())

    import damage_gui.storage.db  # noqa: E402
    import damage_gui.logging_setup  # noqa: E402
    import damage_gui.visualization.plots  # noqa: E402
    import damage_gui.gui.resources  # noqa: E402
    import damage_gui.app  # noqa: E402
    import damage_gui.webapp  # noqa: E402

    assert "tkinter" not in sys.modules, "tkinter 被无头导入链拉起"
    assert (
        "damage_gui.gui.main_window" not in sys.modules
    ), "damage_gui.app 在模块导入期拉起了 Tk GUI"

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
        """storage / logging_setup / plots / app 可在无 Tk 环境导入。"""
        result = _run_probe(_HEADLESS_PROBE)
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr[-2000:]}")
        self.assertIn("HEADLESS_IMPORT_OK", result.stdout)

    def test_app_import_alone_does_not_pull_tk_gui(self) -> None:
        """仅导入 damage_gui.app 不得触发 Tk GUI 模块加载。"""
        probe = textwrap.dedent(
            """
            import sys
            from importlib.abc import MetaPathFinder

            class _Blocker(MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == "damage_gui.gui.main_window" or fullname.startswith(
                        "damage_gui.gui.main_window."
                    ):
                        raise ImportError("blocked: " + fullname)
                    return None

            sys.meta_path.insert(0, _Blocker())

            import damage_gui.app  # noqa: E402

            assert "tkinter" not in sys.modules
            assert "damage_gui.gui.main_window" not in sys.modules
            print("APP_LAZY_OK")
            """
        )
        result = _run_probe(probe)
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr[-2000:]}")
        self.assertIn("APP_LAZY_OK", result.stdout)

    def test_webapp_import_does_not_load_desktop_or_plot_dependencies(self) -> None:
        probe = textwrap.dedent(
            """
            import sys

            import damage_gui.webapp  # noqa: E402

            assert "tkinter" not in sys.modules
            assert "damage_gui.gui.main_window" not in sys.modules
            assert "matplotlib" not in sys.modules
            print("WEBAPP_LAZY_OK")
            """
        )
        result = _run_probe(probe)
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr[-2000:]}")
        self.assertIn("WEBAPP_LAZY_OK", result.stdout)

    def test_plots_import_does_not_bind_backend(self) -> None:
        """导入 visualization.plots 不得改动已设定的 matplotlib 后端。

        说明：rcParams["backend"] 的读取本身会触发 auto 后端解析，因此
        用 MPLBACKEND=Agg 固定后端后再断言导入 plots 不改写它——这才
        是"后端无关"的可判定条件（TkAgg 模块是否被系统 auto 解析加载
        与本模块无关）。
        """
        probe = textwrap.dedent(
            """
            import matplotlib

            before = matplotlib.rcParams["backend"]
            assert before.lower() == "agg", f"预期 Agg，实际 {before!r}"

            import damage_gui.visualization.plots  # noqa: E402

            after = matplotlib.rcParams["backend"]
            assert after == before, (
                f"plots 导入改动了 backend rcParam: {before!r} -> {after!r}"
            )
            print("BACKEND_AGNOSTIC_OK")
            """
        )
        env = _headless_env()
        env["MPLBACKEND"] = "Agg"
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            env=env,
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr[-2000:]}")
        self.assertIn("BACKEND_AGNOSTIC_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
