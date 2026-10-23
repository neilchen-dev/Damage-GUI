"""POD-RBF 降阶模型测试：模态重构、值域与解释方差。

补充覆盖 :class:`damage_gui.model.pod._PODBasis`（移除 scikit-learn 后的
自实现 POD 基底）：确定性、符号约定、正交归一、可逆性，
以及"无 sklearn 环境可训练"的子进程守卫。
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))

from damage_gui.config import CONFIG
from damage_gui.data.loader import Condition
from damage_gui.data.preprocessing import roi_mask_for_shape
from damage_gui.model.pod import PODRBFDamageField

SHAPE = (64, 64)


def _probe_env() -> dict[str, str]:
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
        env=_probe_env(),
        timeout=180,
    )


def amplitude_field(amplitude: float) -> np.ndarray:
    rows, cols = np.meshgrid(
        np.arange(SHAPE[0], dtype=float), np.arange(SHAPE[1], dtype=float), indexing="ij"
    )
    dr = rows - 31.5
    dc = cols - 31.5
    return (
        amplitude * np.exp(-(dr * dr + dc * dc) / (2.0 * 5.0 * 5.0))
    ).astype(np.float32)


def make_training_set(n=8):
    # v/deg 取 0/1 交错，保证工况在三个维度都有变化（避免 RBF 秩亏）
    conditions = np.array(
        [[float(i), float(i % 2), float((i // 2) % 2)] for i in range(n)],
        dtype=np.float64,
    )
    matrices = np.stack([amplitude_field(0.2 + 0.1 * i) for i in range(n)])
    return conditions, matrices


class PODRBFTests(unittest.TestCase):
    def test_pod_rbf_recovers_training_points(self) -> None:
        conditions, matrices = make_training_set()
        model = PODRBFDamageField(
            kernel=CONFIG.rbf_kernel,
            smoothing=CONFIG.rbf_smoothing,
            target_shape=SHAPE,
            align=True,
            n_components=5,
        )
        model.fit(conditions, matrices)
        # 幅值变化是秩 1 结构，少数模态即可完整重构
        self.assertAlmostEqual(model.explained_variance, 1.0, places=6)
        roi = roi_mask_for_shape(SHAPE)
        for i in range(len(conditions)):
            prediction = model.predict_matrix(Condition(*conditions[i]))
            np.testing.assert_allclose(
                prediction[roi], matrices[i][roi], atol=5e-3,
                err_msg=f"训练点 {i} 未被 POD-RBF 恢复",
            )

    def test_prediction_range_0_1(self) -> None:
        conditions, matrices = make_training_set()
        model = PODRBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=CONFIG.rbf_smoothing,
            target_shape=SHAPE, align=True, n_components=5,
        )
        model.fit(conditions, matrices)
        prediction = model.predict_matrix(Condition(3.3, 0.0, 0.0))
        self.assertGreaterEqual(float(prediction.min()), 0.0)
        self.assertLessEqual(float(prediction.max()), 1.0)

    def test_components_clamped_to_sample_count(self) -> None:
        conditions, matrices = make_training_set(n=6)
        model = PODRBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=CONFIG.rbf_smoothing,
            target_shape=SHAPE, align=True, n_components=50,
        )
        model.fit(conditions, matrices)
        self.assertEqual(model.n_components_used, 6)
        self.assertLessEqual(model.explained_variance, 1.0 + 1e-9)

    def test_model_name_reflects_components(self) -> None:
        conditions, matrices = make_training_set(n=6)
        model = PODRBFDamageField(
            kernel=CONFIG.rbf_kernel, smoothing=CONFIG.rbf_smoothing,
            target_shape=SHAPE, align=True, n_components=3,
        )
        model.fit(conditions, matrices)
        self.assertIn("K=3", model.model_name)

    def test_legacy_pca_state_migrates_to_pod(self) -> None:
        """v2.2 旧版 joblib（sklearn PCA，属性名 pca）unpickle 后可直接预测。

        回归守卫：pca→pod 改名曾导致旧模型"能加载、预测即 AttributeError"。
        ``__setstate__`` 负责把旧状态字典里的 ``pca`` 迁移为 ``pod``。
        """
        conditions, matrices = make_training_set()
        model = PODRBFDamageField(
            kernel=CONFIG.rbf_kernel,
            smoothing=CONFIG.rbf_smoothing,
            target_shape=SHAPE,
            align=True,
            n_components=5,
        )
        model.fit(conditions, matrices)
        query = Condition(*conditions[0])
        expected = model.predict_matrix(query)

        # 模拟 unpickle：不走 __init__，状态字典里只有旧名 pca
        state = dict(model.__dict__)
        state["pca"] = state.pop("pod")
        restored = PODRBFDamageField.__new__(PODRBFDamageField)
        restored.__setstate__(state)

        self.assertFalse(hasattr(restored, "pca"), "迁移后不应残留旧属性名")
        self.assertIsNotNone(restored.pod)
        np.testing.assert_allclose(restored.predict_matrix(query), expected)

    def test_unfitted_predict_raises(self) -> None:
        model = PODRBFDamageField("thin_plate_spline", 0.0, SHAPE)
        with self.assertRaises(RuntimeError):
            model.predict_matrix(Condition(0.0, 0.0, 0.0))


class PODBasisTests(unittest.TestCase):
    """_PODBasis 自身契约：确定性、符号约定、可逆性与无 sklearn 可用性。

    这些用例是"移除 scikit-learn 依赖"的安全网——保证核心算法层
    不再依赖第三方 ML 全栈，且 POD 数值跨版本确定。
    """

    def _rank_deficient_data(self) -> np.ndarray:
        rng = np.random.default_rng(7)
        base = rng.normal(size=(9, 40))
        # 秩 3 的构造：后 6 个样本是前 3 个的线性组合
        for i in range(3, 9):
            base[i] = 0.5 * base[i % 3] + 0.5 * base[(i + 1) % 3]
        return base

    def test_fit_transform_is_deterministic(self) -> None:
        """同一输入两次 fit 得到完全一致的系数与基向量。"""
        from damage_gui.model.pod import _PODBasis

        X = self._rank_deficient_data()
        a = _PODBasis(n_components=3)
        b = _PODBasis(n_components=3)
        ya = a.fit_transform(X)
        yb = b.fit_transform(X)
        np.testing.assert_array_equal(ya, yb)
        np.testing.assert_array_equal(a.components_, b.components_)
        np.testing.assert_array_equal(
            a.explained_variance_ratio_, b.explained_variance_ratio_
        )

    def test_sign_convention_is_stable(self) -> None:
        """符号约定：每列绝对值最大的训练系数为正（sklearn svd_flip 约定）。"""
        from damage_gui.model.pod import _PODBasis

        X = self._rank_deficient_data()
        basis = _PODBasis(n_components=3)
        Y = basis.fit_transform(X)
        for col in range(Y.shape[1]):
            column = Y[:, col]
            self.assertEqual(
                np.sign(column[np.argmax(np.abs(column))]),
                1.0,
                msg=f"第 {col} 列未采用 svd_flip 正号约定",
            )

    def test_roundtrip_recovers_input_at_full_rank(self) -> None:
        """k 取满秩时 fit_transform → inverse_transform 精确复原输入。"""
        from damage_gui.model.pod import _PODBasis

        X = self._rank_deficient_data()
        basis = _PODBasis(n_components=X.shape[1])
        Y = basis.fit_transform(X)
        np.testing.assert_allclose(basis.inverse_transform(Y), X, atol=1e-9)

    def test_explained_variance_ratio_sums_to_one_at_full_rank(self) -> None:
        """k 取满秩时累计解释方差为 1。"""
        from damage_gui.model.pod import _PODBasis

        X = self._rank_deficient_data()
        basis = _PODBasis(n_components=X.shape[1])
        basis.fit_transform(X)
        self.assertAlmostEqual(float(np.sum(basis.explained_variance_ratio_)), 1.0, places=9)

    def test_components_are_orthonormal(self) -> None:
        """POD 基底正交归一（POD 定义要求）。"""
        from damage_gui.model.pod import _PODBasis

        X = self._rank_deficient_data()
        basis = _PODBasis(n_components=3)
        basis.fit_transform(X)
        gram = basis.components_ @ basis.components_.T
        np.testing.assert_allclose(gram, np.eye(3), atol=1e-9)

    def test_unfitted_inverse_transform_raises(self) -> None:
        from damage_gui.model.pod import _PODBasis

        with self.assertRaises(RuntimeError):
            _PODBasis(n_components=2).inverse_transform(np.zeros((1, 2)))


class PODBasisWithoutSklearnTests(unittest.TestCase):
    """核心算法层不得依赖 scikit-learn（否则 [core] 安装会训练失败）。"""

    def test_pod_pipeline_runs_with_sklearn_blocked(self) -> None:
        probe = textwrap.dedent(
            """
            import sys

            class _Blocker:
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == "sklearn" or fullname.startswith("sklearn."):
                        raise ImportError("blocked: " + fullname)
                    return None

            sys.meta_path.insert(0, _Blocker())

            import numpy as np
            from damage_gui.config import CONFIG
            from damage_gui.model.pod import PODRBFDamageField

            shape = (32, 32)
            rng = np.random.default_rng(11)
            rows, cols = np.meshgrid(
                np.arange(shape[0], dtype=float),
                np.arange(shape[1], dtype=float),
                indexing="ij",
            )
            dr, dc = rows - 15.5, cols - 15.5
            matrices = np.stack(
                [
                    (amp * np.exp(-(dr * dr + dc * dc) / 50.0)).astype(np.float32)
                    for amp in (0.3, 0.5, 0.7, 0.9, 0.4, 0.6)
                ]
            )
            # 三个工况维度都必须变化，否则 RBF 增广矩阵秩亏（与
            # make_training_set 保持同样的规避方式）
            conditions = np.array(
                [
                    [float(i), float(i % 2), float((i // 2) % 2)]
                    for i in range(len(matrices))
                ]
            )
            model = PODRBFDamageField(
                kernel=CONFIG.rbf_kernel,
                smoothing=CONFIG.rbf_smoothing,
                target_shape=shape,
                align=True,
                n_components=3,
            )
            model.fit(conditions, matrices)
            assert model.explained_variance > 0.99, model.explained_variance
            assert not any(m.startswith("sklearn") for m in sys.modules)
            print("NO_SKLEARN_OK")
            """
        )
        result = _run_probe(probe)
        self.assertEqual(result.returncode, 0, msg=f"stderr: {result.stderr[-2000:]}")
        self.assertIn("NO_SKLEARN_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
