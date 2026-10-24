"""各模型后端的训练实现（训练端），**一种架构一个文件**，跟推断端 `sherpa/alpha/custom/ml/backends/` 一一对应：

| 后端名 | 训练 | 推断 | "轮数"指什么 |
| --- | --- | --- | --- |
| `lightgbm` | `lgb.py` | `backends/lgb.py` | 树的棵数 |
| `xgboost` | `xgb.py` | `backends/xgb.py` | 树的棵数 |
| `lstm` | `lstm.py` | `backends/lstm.py` | epoch 数 |

统一入口是上一级的 `trainer.train_fold`（按后端名分派到这里）。所有后端是同一个两步流程（早停找轮数 → 整窗按这个轮数
重训）、同一个 IC_IR 损失和早停指标（`objective.py`），产出同一个 `common.FoldResult`。每个文件在被分派到时才 import，
对应的 ML 库也是。
"""
