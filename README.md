# Relay Hub

Relay Hub 是一套把 `OpenClaw`、本地网页入口、以及外部编码对象连接起来的分支式对话桥。

它解决的是这类场景：

- 用户仍然在飞书 / 微信里和 `OpenClaw` 交互
- 真正的录入入口放在本地网页
- 外部对象如 `Codex / Claude Code / Gemini CLI / Cursor CLI / Opencode` 只读写统一协议
- OpenClaw 只负责“开入口、收已录入、查状态、退出、发回包”
- 主对话窗口仍然是主线，网页 branch 只是分支记录

当前仓库已经包含：

- 通用协议与通用 CLI
- 本地网页入口
- OpenClaw 渠道桥接
- `launchd` 级别的 Web / Worker 安装能力
- 给外部对象和 OpenClaw 的最小规则文档
- 安装自检命令

## 仓库结构

```text
relay-hub/
  README.md
  RELAY_PROTOCOL.md
  RUNBOOK.md
  AGENT_ENTRY_RULE.md
  AGENT_WORKFLOW.md
  CODEX_WORKFLOW.md
  OPENCLAW_INTEGRATION.md
  OPENCLAW_RULE.md
  install.py
  relay_openclaw_bridge.py
  relay_agent_worker.py
  agent_relay.py
  openclaw_relay.py
  relayctl.py
  relay_web.py
  relay_hub/
    __init__.py
    store.py
    web.py
```

## 安装前提

- macOS
- `python3`
- 已安装并可用的 `OpenClaw`
- 至少一个可用外部对象
  - 例如 `claude`
  - 或以后接入别的对象
- 你知道自己的 OpenClaw 目标信息
  - 飞书直聊 target
  - 微信 target
  - 微信 accountId 如有需要

## 一条命令完成安装

建议先做一次自检：

```bash
cd /path/to/relay-hub
python3 install.py doctor --worker-backend claude-code
```

确认基础依赖没问题后，再执行安装。

最常见的安装方式是：

```bash
cd /path/to/relay-hub
python3 install.py full \
  --web-base-url http://YOUR_LAN_IP:4317 \
  --feishu-target ou_xxx \
  --weixin-target xxx@im.wechat \
  --weixin-account-id your-account-id \
  --worker-agent claude-code \
  --worker-backend claude-code \
  --load-services
```

说明：

- `--web-base-url` 必须是你的飞书/微信客户端能打开的地址，通常是局域网 IP
- `--load-services` 会把 Web 和 Worker 直接装进 `launchd`
- 如果你暂时只想装 OpenClaw 侧，不启服务，可以去掉 `--load-services`
- 如果你只有飞书，没有微信，可以省略微信参数

## 这条安装命令会做什么

`install.py full` 会完成以下事情：

1. 初始化或更新默认 runtime：
   - `~/Library/Application Support/RelayHub/runtime`
2. 把 OpenClaw 侧桥接脚本安装到：
   - `~/.openclaw/workspace/scripts/relay_openclaw_bridge.py`
3. 写入 OpenClaw 侧配置：
   - `~/.openclaw/workspace/data/relay_hub_openclaw.json`
4. 安装 OpenClaw skill：
   - `~/.openclaw/workspace/skills/relay-hub-openclaw/SKILL.md`
5. 给 `HEARTBEAT.md` 安装或更新 relay delivery pump 片段
6. 把可执行副本 stage 到：
   - `~/Library/Application Support/RelayHub/app`
7. 生成 `launchd` 服务：
   - `com.relayhub.web`
   - `com.relayhub.worker.<agent>`
8. 如带 `--load-services`，会直接加载并启动这些服务

之所以会多一步 stage，并把默认 runtime 也放到 `Application Support`，是为了避免直接从 `Desktop/Documents` 等受保护目录启动后台服务时撞上 macOS 权限限制。

## 安装后怎么用

装完以后，用户侧流程应该是：

1. 在 OpenClaw 里说：
   - `打开 claude 入口`
   - 或 `打开 codex 入口`
   - 或别的对象入口
2. OpenClaw 返回网页入口
3. 在网页里写 branch 内容
4. 回到 OpenClaw 说：
   - `已录入`
5. Worker 自动 claim 队列并处理
6. 外部对象回包后，OpenClaw 自动发回飞书 / 微信

支持的 OpenClaw 命令语义：

- `打开 codex 入口`
- `打开 claude 入口`
- `打开 gemini 入口`
- `打开 cursor 入口`
- `打开 opencode 入口`
- `已录入`
- `状态`
- `退出`

## 常用维护命令

查看当前安装状态：

```bash
cd /path/to/relay-hub
python3 install.py status
```

只重装 OpenClaw 侧桥接：

```bash
cd /path/to/relay-hub
python3 install.py install-openclaw \
  --web-base-url http://YOUR_LAN_IP:4317 \
  --feishu-target ou_xxx \
  --weixin-target xxx@im.wechat \
  --weixin-account-id your-account-id
```

只安装或更新 `launchd` 服务：

```bash
cd /path/to/relay-hub
python3 install.py install-launchd \
  --worker-agent claude-code \
  --worker-backend claude-code \
  --load-services
```

## 文档入口

- 通用协议：`RELAY_PROTOCOL.md`
- OpenClaw 接入映射：`OPENCLAW_INTEGRATION.md`
- OpenClaw 最小规则：`OPENCLAW_RULE.md`
- 外部对象最小入口：`AGENT_ENTRY_RULE.md`
- 外部对象工作流：`AGENT_WORKFLOW.md`
- Codex 主窗口工作流：`CODEX_WORKFLOW.md`
- 日常运维：`RUNBOOK.md`

## 边界说明

- Relay Hub 的网页 branch 不是主对话本身，而是主线分支
- 当前主对话窗口仍然是主线
- OpenClaw 不负责主线快照和 merge-back
- 外部对象不应直接读取飞书 / 微信原始渠道
- OpenClaw 也不应自己翻 `routes.json`、`messages/*.md`

所有渠道读写都应该通过固定桥接 CLI 完成。
