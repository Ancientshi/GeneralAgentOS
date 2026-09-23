# General Agent OS

**自己写 agent profile，一条命令部署。**

基于 Agno AgentOS 3.0.10。用 YAML 定义模型、提示词、MCP 工具、skills、会话历史和多个 agent，
不用为每个 agent 重写服务代码。

## 一键安装

需要 Linux/macOS 和 Python 3.10+：

```bash
curl -fsSL https://raw.githubusercontent.com/Ancientshi/GeneralAgentOS/v1.0.1/install.sh | bash
```

下载源码后也可直接 `bash install.sh`。安装到独立环境，不需要 sudo，不改系统 Python。
在线安装命令需要 GitHub v1.0.1 Release 已发布。

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

## 保留原有灵活性

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

参见 [profile 配置说明](docs/profiles.md)、[旧项目迁移](docs/migration.md)、
[英文完整说明](README.md)。Release 包不包含个人密钥、私有 MCP 路径或会话数据库。
