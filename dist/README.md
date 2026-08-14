# DamageEfficiencyApp v1.0.0

## 毁伤效率评估与瞄准优化系统

### 快速开始

1. 双击 `DamageEfficiencyApp.exe` 启动程序
2. 确认左侧"数据目录"指向 `data/` 文件夹
3. 选择毁伤等级 (F/M/P)
4. 点击"训练模型"或"加载模型"
5. 设置工况参数 (h/v/deg)
6. 点击"预测"生成毁伤场
7. 在"瞄准优化"卡片中设置 CEP 或 REP/DEP
8. 点击"计算最佳瞄准点"

### 目录结构

```
DamageEfficiencyApp/
├── DamageEfficiencyApp.exe    # 主程序
├── data/                      # 毁伤矩阵数据
├── _internal/                 # PyInstaller 依赖
└── README.md
```

### 功能

- **RBF 毁伤场预测**: 基于径向基函数插值的毁伤场重建
- **瞄准优化**: 基于 CEP/REP/DEP 散布参数的最优瞄准点搜索
- **可视化**: 毁伤场热力图、价值场、最佳瞄准点标记
- **导出**: CSV 指标表、PNG 图表

### 版本

v1.0.0 - 首次正式发布
