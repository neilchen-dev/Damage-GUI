# 架构优化审计报告 — Damage-GUI（未提交工作区变更）

**审计日期**: 2026-10-20 · **变更规模**: 58 文件，+775 / −4307 行 · **测试**: 291 passed (71s) · **Ruff**: All checks passed

---

## 一、本轮优化内容（已确认）

| 优化项 | 实现 | 评价 |
|---|---|---|
| Tk GUI 整体退役 | 删除 `damage_gui/gui/` 子树（2847 行），`desktop.py` 指向 Qt 唯一实现 | ✅ 干净彻底，全仓零残留引用 |
| pandas 移出核心依赖 | 自研 `data/table.py`（Table/Column/Mask/Index/read_csv，595 行） | ⚠️ 见问题 3 |
| sklearn 移出核心依赖 | `_PODBasis`（numpy 全 SVD）、metrics 自实现、validation 降级路径 | ✅ 实现正确，⚠️ 见问题 2 |
| `app.py` PEP 562 惰性兼容层 | 旧 joblib re-export 按需解析 | ✅ 实测冷导入 0.007s，32 个符号全覆盖 |
| i18n 上移中立层 | `damage_gui.i18n`，Qt 不再依赖 Tk 层 | ✅ |
| 图标迁 runtime | `runtime/icons.py` + assets 迁移，spec 同步 | ✅ |
| extras 重组 | core / desktop / web / full / data-science / legacy | ⚠️ 见问题 1 |
| 打包瘦身 | spec 排除 sklearn+pandas（约 −104MB） | ✅ 注释清晰 |

**验证通过项**：无 pandas/sklearn 环境下核心链路（含 webapp、experiments 包）全部可导入；`test_headless_imports` 守卫同步更新；旧 RBF 模型加载正常。

## 二、发现的问题（按严重度）

### 🔴 P1-1：CI workflow 未同步，必挂

`.github/workflows/test.yml:49,88` 仍引用 `.[desktop-qt,web,test]`：

- `desktop-qt` extra 已改名为 `desktop` → pip 告警跳过 → **PySide6 不会安装** → Qt 测试全挂
- `test` extra 不含 pandas，而 `tests/test_batch.py:10`、`tests/test_phase1_services.py:13`、`tests/test_experiments.py`、`tests/test_benchmark.py` 均无条件 `import pandas` → **核心测试挂**

**修复**：CI 改为 `pip install -e ".[desktop,web,test,data-science]"`（或给 pandas 相关测试加 importorskip）。

### 🔴 P1-2：v2.2.0 旧 POD-RBF 模型预测断裂（已实测确认）

`pod.py` 将属性 `pca` 改名为 `pod` 且无 `__setstate__` 迁移。v2.2.0 保存的 POD 模型 unpickle 后只有 `pca`，调用 `_reconstruct_window`（pod.py:186）时：

```
AttributeError: 'PODRBFDamageField' object has no attribute 'pod'
```

仓库内现有模型均为 RBF 类型不受影响，但用户用 2.2.0 训练的 POD-RBF 模型会"能加载、预测即崩"。

另外：旧 bundle 的 `accuracy_report` 是 pandas DataFrame，unpickle 需要 pandas，但 `registry.py:115` 的错误提示只引导安装 `[legacy]`（仅 sklearn）→ 用户装完仍缺 pandas。

**修复**：`PODRBFDamageField` 加 `__setstate__` 做 `pod = state.pop("pca")` 迁移；`legacy` extra 补 pandas（或错误信息按缺失模块名分别引导）。

### 🟡 P2：`read_csv` 空字段语义偏离 pandas（已实测对比确认）

`table.py` 的 `read_csv` 将空字段保留为 `""`（pandas 转为 NaN），`isna("")` 为 False。后果链：

```
行尾多余 \t 的 GBK 数据文件（Windows 导出常见）
→ pandas: 尾列全 NaN → dropna(axis=1,how="all") 丢弃 → 正常
→ Table:  尾列全 ""  → 不丢弃 → to_numpy(float32) 抛 ValueError
```

影响 `data/loader.py:100` 的 `read_source_matrix`。`tests/test_table.py:222` 只覆盖了无尾 tab 的干净场景。

**修复**：`read_csv` 在 `dtype is not str` 时将 `""` 转为 `float("nan")`；并补一个带行尾 tab 的测试用例。

### 🟢 P3：次要项

1. `validation.py` numpy 降级路径在当前测试环境（装有 sklearn）**永远走不到**，golden 一致性无测试覆盖 —— 建议加 monkeypatch 屏蔽 sklearn 的用例
2. `requirements.txt` 仍列 pandas+sklearn，与 pyproject 新依赖哲学不一致（Dockerfile 用 web.lock 不受影响）
3. `desktop.py` docstring 错字 "`dxdesktop-tk``"（应为 `damage-gui-tk`）；`qt/__init__.py` docstring 仍写 "Phase 1"
4. `Table.__bool__` 注释称"pandas 对非空帧返回 True"——实际 pandas 会 raise（实现选择合理，注释不准）
5. `Table.__init__` 索引长度不匹配静默替换为 range、`insert` 允许重复列名静默覆盖（pandas 均 raise）—— 属有意的语义子集，建议文档注明
6. `_PODBasis.fit_transform` 全相同样本时 `total==0` → ratio 为 NaN（与 sklearn 行为一致，无防护）

## 三、亮点（值得肯定）

- **`_PODBasis` 实现严谨**：符号约定与 sklearn PCA 默认 `u_based_decision=True` 的 `svd_flip` 等价；`explained_variance_ratio_` 分母用全奇异值和，语义正确；改用确定性全 SVD 消除 randomized SVD 的跨版本漂移，契合"可追溯交付"承诺
- **`validation.py` 降级路径精确复现** ShuffleSplit：`RandomState(MT19937).permutation` + `ceil(n*test_size)`，代码审查确认与 sklearn 数值一致
- 注释/文档质量高：每个设计决策都有动机说明（体积、确定性、分层约束）
- `pyproject.toml` 为 `app.py`/`experiments` 的 F401 与 table.py 的 B905 配置了精确的 per-file-ignores 并附理由

## 四、结论

**方向正确、执行质量高**，但**不建议直接提交**：P1-1（CI 必挂）与 P1-2（旧 POD 模型预测断裂）是必须修复的阻断项；P2（read_csv 空列）建议在数据文件格式不可控前修复。P3 可随后续迭代处理。
