# 数据科学资源与接入选择

核对日期：2026-09-23。以下优先使用维护者文档、官方模型卡与论文。它们是可组合的能力资源，
不是通用排名。**本地基线已运行，不代表完整 benchmark 已跑完；模型模板可生成，不代表模型权重已安装。**

## 优先接入的资源

| 方向 | 资源与一手来源 | 适用场景 | 本次接入 |
|---|---|---|---|
| 基础机器学习 | [scikit-learn](https://scikit-learn.org/stable/) | 分类、回归、预处理、交叉验证 | 线性模型/随机森林模板已运行 |
| 类别特征表格 | [CatBoost](https://catboost.ai/docs/en/)，[论文](https://arxiv.org/abs/1706.09516) | 混合数值与类别列 | 模型模板已实际运行 |
| 梯度提升 | [LightGBM](https://lightgbm.readthedocs.io/en/stable/)、[XGBoost](https://xgboost.readthedocs.io/en/stable/) | 强表格候选、结构化特征 | 资源卡 |
| 自动建模 | [AutoGluon](https://auto.gluon.ai/stable/tutorials/tabular/index.html)，[论文](https://arxiv.org/abs/2003.06505) | 有时间预算的自动建模与组合 | 可选模板，限定 RF/XT |
| 表格基础模型 | [TabPFN](https://github.com/PriorLabs/TabPFN)，[Nature 论文](https://www.nature.com/articles/s41586-024-08328-6) | 根据 checkpoint 适用规模选择 | 可选本地权重模板 |
| 传统预测 | [StatsForecast](https://github.com/Nixtla/statsforecast) | 规则时间序列、季节性、AutoARIMA/ETS 等 | AutoARIMA 模板已实际运行 |
| 机器学习预测 | [MLForecast](https://github.com/Nixtla/mlforecast) | 滞后特征、外生变量、多序列 | 资源卡 |
| 时间序列基础模型 | [Chronos-2 模型卡](https://huggingface.co/amazon/chronos-2)，[论文](https://arxiv.org/abs/2510.15821) | 预训练预测；模型还支持协变量等能力 | 单变量本地权重模板 |
| 时间序列基础模型 | [TimesFM](https://github.com/google-research/timesfm)，[论文](https://arxiv.org/abs/2310.10688) | 另一类预训练预测候选 | 资源卡 |
| 数据探索 | [pandas](https://pandas.pydata.org/docs/) | 缺失、重复、类型、聚合 | 文件审计和季节基线已运行 |
| 统计推断 | [SciPy](https://docs.scipy.org/doc/scipy/reference/stats.html)、[statsmodels](https://www.statsmodels.org/stable/index.html) | 效应量、区间、检验、统计回归 | Welch 两组比较已运行；其他方法资源卡 |
| 解释与因果 | [SHAP](https://shap.readthedocs.io/en/latest/)、[DoWhy](https://www.pywhy.org/dowhy/v0.13/) | 模型解释；有研究设计支持的因果识别 | 资源卡 + 分析技能 |
| 文件与数据工程 | [SQLite](https://docs.python.org/3/library/sqlite3.html)、[DuckDB](https://duckdb.org/docs/stable/)、[Polars](https://docs.pola.rs/)、[Pandera](https://pandera.readthedocs.io/en/stable/) | 表发现、连接、转换、数据契约 | SQLite 审计已运行；其他资源卡 + 工程技能 |

TabPFN 必须区分代码和权重许可：官方仓库说明较新系列权重有非商业条件，v2 另有许可。
因此工具不自动选择或下载默认权重。不同 checkpoint 的规模限制也不同，不把某篇早期论文的数据规模限制
当作整个模型系列永远不变的限制。详见 [官方仓库](https://github.com/PriorLabs/TabPFN)。

## 已存在的 skills 资源库

| 资源库 | 可以借鉴什么 | 这次怎么使用 |
|---|---|---|
| [Hugging Face 官方 Skills](https://github.com/huggingface/skills) | Hub、数据集、模型训练和评测工作流 | 建立可检索资源卡；未整体安装 |
| [Kaggle 官方 CLI Skills](https://github.com/Kaggle/kaggle-cli/tree/main/skills) | Kaggle 资源操作的官方技能资料 | 资源卡；实际搜索用限制为只读的 CLI 适配器 |
| [K-Dense Scientific Agent Skills](https://github.com/K-Dense-AI/scientific-agent-skills) | 第三方科学分析与领域技能集合 | 作为按需扩展来源；未声称逐项审计或验证 |

当前 agent 加载的是本扩展六个精简技能。选择具体外部 skill 时，阅读它的实际脚本、依赖与许可，
再放进独立目录并在 profile 引用；无需把整个外部技能库复制到核心仓库。

## 与五个 benchmark 的联系

| Benchmark | 本次核对的信息 | 建议的能力组合 |
|---|---|---|
| DARE-Bench | 官方 `scripts/reference_solution.py` 使用 sklearn 的预处理、线性/树/邻居等模型；区分任务指定方法与自由优化 | `tabular-modeling` / `time-series-forecasting`，严格服从任务方法约束 |
| Ambig-DS | 目标与目标函数歧义会影响后续方法选择 | 先明确公开目标和评价要求，再选表格模型；不能读取私有 metric/target metadata 来消除歧义 |
| CoDA-Bench | 需要找到并理解相关数据，部分问题涉及建模 | 文件发现、schema 检查、统计/建模、输出格式核验 |
| DDR-Bench | 以实体为单位探索数据并给出发现 | 开放式分析、证据记录、统计、报告 |
| DAComp | 分析任务、数据工程任务与架构任务有不同交付物 | 文件与 SQL 分析、变换校验、证据报告；按题目输出实际代码或数据库 |

这些对应关系属于集成设计。仅 DARE 的具体 sklearn 使用来自本地固定版本源码核对；不声称其他四项
benchmark 的论文采用了本表列出的全部模型。benchmark 原始来源与版本见
[upstream.lock.json](../benchmarks/upstream.lock.json)，原始资源为
[DARE](https://github.com/Snowflake-Labs/dare-bench)、
[CoDA](https://github.com/ruc-datalab/CoDA-Bench)、
[DDR](https://github.com/thinkwee/DDR_Bench)、
[DAComp](https://github.com/ByteDance-Seed/DAComp)、
[Ambig-DS Target](https://huggingface.co/datasets/anonymous222bit/Ambig-DS-T) 与
[Ambig-DS Objective](https://huggingface.co/datasets/anonymous222bit/Ambig-DS-M)。

## 在线资源发现

[Hugging Face Hub API](https://huggingface.co/docs/hub/api) 适合查询模型/数据集卡的标识、版本、标签、下载数
和许可信息；这些元数据不构成性能保证。搜索工具仅返回必要字段。

[Kaggle 官方 CLI](https://github.com/Kaggle/kaggle-cli) 支持模型和数据集检索。本扩展只用
`datasets list` / `models list`，限制输出数量，不提供 notebook 检索或竞赛提交。
后续若要复用竞赛解法，应该单独确定外部资料政策；在 benchmark 测试中直接检索题目解法会改变测试条件。

## 复现实验时固定什么

固定 task/variant、输入版本、特征与划分、方法预算、依赖版本、模型 checkpoint、模板哈希和外部资源政策。
训练数据内部验证与官方测试结果分开保存。任何看到官方反馈后的重试都作为新 attempt，避免把调试过程
当作一次独立测试。数据划分与预处理隔离遵循 [scikit-learn 的数据泄漏说明](https://scikit-learn.org/stable/common_pitfalls.html)。
