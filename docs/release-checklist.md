# DamageLab Release Checklist

每次发布前逐项核对。不能测试的平台明确写 **NOT TESTED**，不推断通过。

## Tests

- [ ] `pytest tests/ -q` 全部通过（当前 259 passed）
- [ ] `PYTHONPATH=src python -m unittest discover -s tests` 通过（CI 口径）
- [ ] `git diff --check` 无空白错误
- [ ] `ruff check .` 通过

## Desktop launch

- [ ] macOS 启动（源码 + 发布包 DamageLab.app）
- [ ] Windows 启动（发布包 DamageLab.exe）— 未实机时标注 NOT TESTED
- [ ] Linux 启动（发布包）— 未实机时标注 NOT TESTED
- [ ] 冷启动：全新环境（无 DB / 无模型 / 空用户目录）不崩溃
- [ ] 首次运行显示合理 empty state（No model loaded）
- [ ] 中英文切换正常，无 key 名、无丢字符串

## Core workflows（每平台）

- [ ] model load（含中文/空格路径）
- [ ] prediction
- [ ] batch
- [ ] validation
- [ ] training
- [ ] registry（注册 / 激活）
- [ ] history（查询 / 详情 / 回填）
- [ ] export（PNG / CSV / JSON，含 Unicode 路径）

## Robustness

- [ ] 损坏输入：垃圾 joblib / 损坏 sidecar JSON / 无效 CSV → 错误回 UI，不崩溃
- [ ] 只读目录导出 → 显示无法写入，不崩溃
- [ ] 任务运行中关闭 → 显示确认对话框
- [ ] 无任务关闭 → 立即退出
- [ ] 日志文件可写（用户数据目录），记录 startup / version / platform

## Packaging

- [ ] `scripts/build_qt_release.sh`（或 .bat）构建成功
- [ ] 产物命名 `DamageLab-<版本>-<平台>`
- [ ] clean-machine 测试：把产物复制到无源码目录运行正常
- [ ] 图标完整（工具栏 / 窗口 / app 图标），无 emoji 替代
- [ ] 数据写入用户数据目录，不写安装目录

## HiDPI / 窗口

- [ ] 100% / 200%（devicePixelRatio=2）截图无模糊、无截字
- [ ] 1100×700 / 1280×720 / 1440×900 / 1600×1000 + maximized 布局完整

## Regression（不破坏既有用户）

- [ ] CLI（damage-gui-cli info / predict / batch）正常
- [ ] FastAPI Web 启动正常
- [ ] legacy Tkinter 桌面（damage-gui）可启动（如保留）
