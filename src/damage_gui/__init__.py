"""Damage field prediction desktop application.

包结构（关注点分离）：
- config            全局配置（模型 / 预处理 / 评估 / UI）
- data              数据读取与场预处理（双边滤波、ROI、坐标网格）
- model             RBF 插值场、POD-RBF 降阶模型、结构化验证、OOD 检测、模型服务
- evaluation        数值与空间场评价指标
- optimization      瞄准点优化（CEP / REP-DEP 散布模型）
- visualization     Matplotlib 热力图与误差场渲染
- gui               Tkinter 主窗口与小部件
- app               应用入口（瘦启动器 + 向后兼容 re-export）
"""

from damage_gui.config import VERSION as __version__
