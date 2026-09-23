# General Agent OS

**自己写 agent profile，一条命令部署。**

基于 Agno AgentOS 3.0.10。用 YAML 定义模型、提示词、MCP 工具、skills、会话历史和多个 agent，
不用为每个 agent 重写服务代码。

## 一键安装

需要 Linux 和 Python 3.10+：

```bash
curl -fsSL https://raw.githubusercontent.com/Ancientshi/GeneralAgentOS/v1.0.2/install.sh | bash
```

下载源码后也可直接 `bash install.sh`。安装到独立环境，不需要 sudo，不改系统 Python。
在线安装命令需要 GitHub v1.0.2 Release 已发布。

## 编写并部署

```bash
gaos init my-agent
# 在 my-agent/.env 中填写 OPENAI_API_KEY
# 编辑 my-agent/profile.yaml 中的 model、instructions、mcp_list、skill_list
gaos validate -p my-agent/profile.yaml
gaos deploy -p my-agent/profile.yaml --name my-agent
gaos status my-agent
gaos logs my-agent
gaos stop my-agent
```

`init` 自动生成服务访问密钥，保存在 `.env` 的 `GAOS_API_KEY` 中。
客户端用 `Authorization: Bearer <密钥>` 调用 API。`/health` 可直接检查是否启动。
前台运行使用 `gaos serve`。修改 profile 后停止并重新部署即可应用。
如需连接 Agno 官网控制台，可在官网开启 **Token-Based Authorization（JWT）**，
并在 AgentOS 配置公钥验签；它与默认的 `GAOS_API_KEY` 是两种认证模式，
同时保留旧网页时应使用不同端口的两个实例。配置见 [profile 说明](docs/profiles.md)。

## 保留原有灵活性

新增可选的 [Benchmark Lab](extensions/benchmarks/README.md)：通过 skill 和 MCP 选择
benchmark、具体题目与变体，执行后自动路由到对应官方 evaluator 并保存反馈。
扩展独立安装，数据和评分依赖按 benchmark 配置，不修改核心运行逻辑。详见接入文档中的覆盖范围和准备条件。

[Data Science Lab](extensions/data-science/README.md) 进一步提供 24 张资源卡、六个分析技能和十个模型/分析模板，
覆盖表格预测、时间序列、统计分析、数据工程以及 Hugging Face/Kaggle 资源发现。
组合配置 `extensions/data-science/profile.yaml` 将方法选择、沙箱执行与官方评价接通；
轻量模板已运行验证，大模型入口的依赖与验证状态单独列明。

- 多份配置叠加：`gaos serve -p main.yaml -p history.yaml`。
- vLLM 等兼容 OpenAI 的接口：在 profile 中设置 `provider`、`base_url` 和 `api_key_env`。
- MCP 注册表也在 profile 内，支持 stdio、SSE、streamable HTTP。
- 本地技能通过 `skill_list` 加载；相对路径以第一份 profile 所在目录为准。
- 同一个 `agents` 字典可以定义多个 agent，并引用独立 reasoning agent。
- profile 校验会报告无效参数、找不到的 MCP/skills 和缺少的环境变量。

本地 `gaos deploy` 支持退出终端后继续运行，但不负责重启后的恢复。
需要开机自启和崩溃重启时使用 `docker compose up -d --build`。
Docker 部署会持久化数据，默认仅开放本机端口。原本安装在宿主机上的 stdio MCP 程序
需另行加入镜像，或使用原生部署。

## 验证范围与当前限制

以下为 **2026-09-23 云端部署验收**，不表示五套 benchmark 全部完成实验：

| 验证项 | 实测结果及范围 |
|---|---|
| 代码 | 认证、profile、运行时的 29 项定向测试，以及 benchmark 引擎的 20 项测试通过；Ruff 检查通过。这不是完整的五套 benchmark 实验。 |
| 在线服务 | 云端 API、Agent UI、Agno 官网 JWT 入口及无 root 执行沙盒已运行。校正服务器时钟后，用户确认官网 Chat 可以打开。 |
| 模型链路 | 当前部署通过 SSH 反向转发使用用户电脑上的 Proxy LLM `gpt-6-luna`。真实 AgentOS 对话调用了 benchmark 工具并完成回复；这只验证连接和工具调用，未证明模型能自主解题。电脑上的代理与转发断开后，聊天将无法生成回复。 |
| 官方评分 | DARE-Bench 的 Pokemon Unite 分类题 `v2`（训练 66 行、预测 8 行）经上游评分器评分：多数类基线 macro F1 为 `0.181818`；**提供随机森林解题代码后**，执行、提交并查询反馈所得 macro F1 为 `0.629630`。后者是工具链验收，**不是 agent 自主解题成绩**。 |
| 自主解题 | 切换模型前，Qwen3-8B 的一次独立尝试未产生有效提交或官方分数；`gpt-6-luna` 尚未完成自主 benchmark 全流程验证。 |

示例服务器只安装了上述 DARE 题目的数据。其他 benchmark 的适配器和 DARE 题目索引已接入，
但数据、评测依赖或 judge 权限需要逐题准备。Data Science Lab 的 10 个模板中，7 个 CPU 模板
已在合成数据上实际运行；另 3 个可选模型模板只完成接口和编译检查，服务器未安装其重量级依赖与权重。
详见 [benchmark 准备条件与协议边界](extensions/benchmarks/README.md) 和
[模板验证情况](extensions/data-science/README.md)。

当前模型是**服务器部署配置**，不是仓库默认值。自行接入同类代理时，在 profile 中设置
`provider: proxyllm`、`model: gpt-6-luna`、`base_url: http://127.0.0.1:18080/v1`，
并按代理要求设置 `api_key_env`。本次代理调用工具还需要
`model_options.reasoning_effort: none`。云端的 `127.0.0.1` 指云服务器本身，
因此需先将本机代理反向转发至云端回环地址。

参见 [profile 配置说明](docs/profiles.md)、[旧项目迁移](docs/migration.md)、
[英文完整说明](README.md)。Release 包不包含个人密钥、私有 MCP 路径或会话数据库。
