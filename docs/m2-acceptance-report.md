# M2 验收报告 — ruff / 数值回归 / 双平台 CI / Windows PyInstaller 构建

日期：2026-08-23 ｜ 版本：2.1.0 ｜ 前置：M1 已冻结，本轮零业务功能、零算法修改、未启动 P2

---

## 1. ruff 静态检查

**配置**（`pyproject.toml [tool.ruff]`）：line-length 100，target py310，规则集
`E/W/F/I/UP/B`（pycodestyle + pyflakes + 导入排序 + pyupgrade + bugbear）；
`scripts/`、`tests/` 因需先注入 `sys.path` 而豁免 E402；排除 build/dist/release。

**存量清理**（66 → 0）：

| 类别 | 数量 | 处理 |
|---|---|---|
| I001 导入排序 / UP037 / UP035 | 21 | `ruff --fix` 自动修复（28 处含隐藏修复） |
| E501 超长行 | 29 | 手工换行（main_window 25、scripts 4、aim.py 1） |
| B023 闭包延迟绑定循环变量 | 2 | `bundle.py` `accumulate` 改默认参数绑定当前迭代值（原实现因同迭代调用而无实际 bug，属防御性加固） |
| B905 zip 无 strict | 6 | 全部加 `strict=True`（两端序列均同构造等长，增加真实不变量校验，行为不变） |
| F401 / F841 / B007 | 8 | 删除未用导入/变量；`__init__.py` 加 `__all__`；`app` 未用赋值移除 |

**结果**：`ruff check .` 全绿；139 个测试通过（ruff 修复后零回归）。

---

## 2. 数值回归测试

**新增**：`tests/test_numerical_regression.py`（4 用例）、`tests/regression_tools.py`
（共享数据集/快照构建）、`tests/data/regression_golden.json`（黄金值）、
`scripts/regen_regression_golden.py`（受控再生成）。

**确定性设计**（不改模型算法）：发现 `pod.py` 的 `PCA(svd_solver='auto')` 在特征数
>500 时走 randomized SVD（`random_state=None`，跨运行不确定）。回归数据集设计为
20×20（对齐窗口 400 特征 ≤ 500），强制 auto 选择 full SVD（LAPACK 确定性路径），
27 工况 × 固定种子 PCG64 噪声（`default_rng(20260823)`，跨平台流稳定）。

**覆盖**：RBF 与 POD-RBF 双模型 × 3 探针工况的预测场摘要（max/mean/sum + 11 个采样像素）、
POD 累计解释方差与实际模态数、OOD 分级与最近工况距离、核心指标 MeanRE / P95 Hybrid。

**再生成纪律**：脚本 docstring 与测试 docstring 均注明——禁止为变绿而随手再生成或放宽
容差；需先解释偏差来源；黄金值变更必须随代码提交理由。

---

## 3. 跨平台数值漂移与最终容差

**实测程序**（先记录实际差异，再决定容差）：两个**独立进程**各完整构建一次快照
（数据生成 → RBF 训练 → POD 训练 → 预测 → OOD → 指标），对全部 95 个数值条目求绝对差。

| 测量 | 结果 |
|---|---|
| Windows 本机，进程 A vs 进程 B | **最大绝对差 = 0.0**（95 条目全部精确相等） |
| Windows vs Linux（本机不可测） | 由 CI 双平台首次运行给出权威数据（见 §4 约定） |

**最终采用的容差**（依据上述实测设定，未盲目放宽）：

| 常量 | 值 | 适用 | 依据 |
|---|---|---|---|
| `FIELD_TOL` | **1e-6** | 预测场摘要/采样像素（值域 O(1)） | 实测 0.0；跨平台唯一预期差异源为 OpenBLAS/LAPACK 内核选择的浮点舍入（典型 1e-12~1e-8），容差高约 2 个数量级，仍远低于真实算法回归（≥1e-3 量级） |
| `METRIC_TOL` | **1e-6** | MeanRE / P95 Hybrid | 同上 |
| `EV_TOL` | **1e-9** | POD 累计解释方差（≈1.0 的比值和） | SVD 奇异值比值，抖动更小，收得更紧 |
| `OOD_TOL` | **1e-9** | OOD 最近工况距离 | 纯算术归一化距离，无 BLAS 参与 |
| 分级/模态数 | 精确相等 | OOD level、`n_components_used` | 类别量，任何变化即事件 |

**示例说明**：若 CI 实测 Linux 最大漂移为 2e-6，则将 `FIELD_TOL` 调至 5e-6 并在报告
记录实测值——而不是直接放宽到 1e-3。失败信息会打印实际偏差与所在条目，容差常量集中
在测试文件顶部，一处修改。

---

## 4. 测试结果（Windows / Linux）

| 环境 | 命令 | 结果 |
|---|---|---|
| 本机 Windows（Python 3.12.10） | `python -m unittest discover -s tests` | **139 tests, OK（5.3s）**：原 83 + M1 新增 52 + M2 数值回归 4 |
| 本机 Windows | `ruff check .` | All checks passed |
| CI Windows（windows-latest，Python 3.11） | workflow `test` job | **成功**（首次运行，含数值回归黄金值对比） |
| CI Linux（ubuntu-latest，Python 3.11） | workflow `test` job | **成功**（首次运行，**原始容差 1e-6 / 1e-9 未调整即通过**——跨平台实测漂移在容差内，无需放宽） |

**首次 CI 运行结果**（commit `07aa7f7`，run `32617285181`，2026-08-23）：

```text
✓ Lint (ruff)                       8s
✓ Tests (ubuntu-latest, Py3.11)     31s
✓ Tests (windows-latest, Py3.11)   1m6s
✓ Windows PyInstaller build        2m6s   （exe 校验通过，artifact 已上传）
- Attach release (tags only)       skipped（无 tag，符合设计）
artifact: Damage-GUI-win64（zip，约 87.5 MB）
```

至此双平台验收闭环：§3 的容差假设（Windows/Linux 漂移在 1e-6 内）已被 CI Linux
实跑证实，未发生任何容差调整。

---

## 5. Windows PyInstaller 构建（真跑验证）

**本地实跑**（不是 dry-run）：

```text
$ scripts\build_release.bat
...
226301 INFO: Building EXE from EXE-00.toc completed successfully.
236726 INFO: Building COLLECT COLLECT-00.toc completed successfully.
Build complete! The results are available in: G:\Damage GUI\release
```

| 检查 | 结果 |
|---|---|
| 产物 | `release/Damage-GUI-v2.1.0-win64/Damage-GUI-v2.1.0-win64.exe`（onedir，含 `_internal/` 与 README.md） |
| 包体积 | 303 MB（matplotlib/pandas/scipy/sklearn 全量依赖） |
| 构建时长 | 约 4 分钟（本地 PyInstaller 6.16.0） |

**CI 侧**（`build` job）：`needs: [lint, test]` 全绿后才构建 → 真跑同一
`scripts/build_release.bat` → PowerShell 校验产物中存在 `.exe`（否则 fail）→
`upload-artifact@v4` 上传 `release/`（`if-no-files-found: error`）。
"unit tests passed" 与 "Windows 可执行产物真的能构建出来" 在 CI 中是两个独立 gate。

---

## 6. CI workflow 变更（`.github/workflows/test.yml`）

原单 job（Win+Ubuntu 矩阵跑 unittest）→ 四段流水线，失败可明确定位阶段：

```text
push / PR
  ├─ lint   (ubuntu)  ruff check .
  ├─ test   (windows + ubuntu, Py3.11)  unittest 全量（含数值回归）
  └─ build  (windows, needs lint+test)  真跑 build_release.bat
              ├─ 校验 exe 产物存在
              └─ upload-artifact: Damage-GUI-win64
  └─ release (ubuntu, 仅 refs/tags/*)   下载 artifact → zip → GitHub Release
```

- 固定 Python 3.11；`fail-fast: false` 保留双平台完整结果；
- release job 带 `permissions: contents: write` 且仅在 tag 上运行——普通 push/PR
  只留 artifact，不自动发布；
- 逐 job 命名（Lint / Tests / Windows PyInstaller build / Attach release），
  失败时从 job 名即可定位是 lint / test / build 哪一步。

---

## 7. Diff 概览（M2 增量，相对 M1 冻结点）

- 新增：`tests/test_numerical_regression.py`、`tests/regression_tools.py`、
  `tests/data/regression_golden.json`、`scripts/regen_regression_golden.py`
- 重写：`.github/workflows/test.yml`（单 job → 四 job）
- 修改：`pyproject.toml`（[tool.ruff] 配置）；以及 ruff 存量清理触及的
  25 个文件（导入排序 14、长行换行、B023/B905/F401/F841/B007 语义修复）——
  其中数值语义零变化（139 测试通过佐证，含 83 个原用例）
- 构建产物 `release/`、`build/` 均在 .gitignore 内，不入库

## 8. 已知限制与后续

1. ~~Linux 侧数值回归与构建结果以 CI 首次运行为准~~ → **已闭环**：首次 CI（§4）Windows/Linux 双平台测试与 Windows 构建全部通过，数值回归原始容差未被调整；
2. CI 未锁定依赖小版本（requirements 为范围约束）——sklearn/numpy 小版本升级若引起
   randomized 路径外的小漂移，按 §3 流程以实测数据调整容差；
3. PyInstaller onedir 体积 303MB 未做裁剪优化（属可选优化，非 M2 目标）；
4. `release/` 本地产物已生成但未提交（gitignore 覆盖）；
5. P2（最小 CLI info/predict/batch + README/简历文档）未开始，按约定留待下轮。
