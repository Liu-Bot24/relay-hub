# Relay Hub

Relay Hub 是一套把 `OpenClaw`、本地网页入口、以及外部编码对象连接起来的分支式对话桥。

它解决的是这类场景：

- 用户仍然在 `OpenClaw` 已连接的消息渠道里交互，例如飞书 / 微信
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

如果你想知道“下载仓库以后应该跟 Claude Code 说什么、跟 OpenClaw 说什么”，直接看：

- 安装章程：`docs/INSTALL_PLAYBOOK.md`
- 通用性审计：`docs/COMPATIBILITY.md`

## 仓库结构

```text
relay-hub/
  README.md
  install.py
  RELAY_PROTOCOL.md
  docs/
    INSTALL_PLAYBOOK.md
    COMPATIBILITY.md
    RUNBOOK.md
    AGENT_ENTRY_RULE.md
    AGENT_WORKFLOW.md
    CODEX_WORKFLOW.md
    OPENCLAW_INTEGRATION.md
    OPENCLAW_RULE.md
  scripts/
    relay_openclaw_bridge.py
    relay_agent_worker.py
    agent_relay.py
    codex_relay.py
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
  - 当前仓库自带的常驻 worker 后端是 `Claude Code`
  - 其他对象仍然可以按协议接入，但默认不附带现成后台 worker
- 你知道至少一个 OpenClaw 消息渠道的目标信息
  - 可以是飞书、微信
  - 也可以是任意 `openclaw message send` 支持的渠道
  - 某些渠道如果要求 `accountId`，也一并准备好

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
  --delivery-channel feishu=ou_xxx \
  --delivery-channel openclaw-weixin=xxx@im.wechat \
  --delivery-account openclaw-weixin=your-account-id \
  --worker-agent claude-code \
  --worker-backend claude-code \
  --load-services
```

说明：

- `--web-base-url` 必须是你的消息客户端能打开的地址，通常是局域网 IP
- `--load-services` 会把 Web 和 Worker 直接装进 `launchd`
- 如果你暂时只想装 OpenClaw 侧，不启服务，可以去掉 `--load-services`
- 如果你只需要一个渠道，只传一个 `--delivery-channel` 即可
- 如果某个渠道需要额外账号参数，用 `--delivery-account channel=accountId`

飞书 / 微信也保留了快捷参数，和上面的通用参数等价：

```bash
python3 install.py full \
  --web-base-url http://YOUR_LAN_IP:4317 \
  --feishu-target ou_xxx \
  --weixin-target xxx@im.wechat \
  --weixin-account-id your-account-id \
  --worker-agent claude-code \
  --worker-backend claude-code \
  --load-services
```

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
6. 外部对象回包后，OpenClaw 自动发回消息渠道

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
  --delivery-channel feishu=ou_xxx \
  --delivery-channel openclaw-weixin=xxx@im.wechat \
  --delivery-account openclaw-weixin=your-account-id
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
- 安装章程：`docs/INSTALL_PLAYBOOK.md`
- 通用性审计：`docs/COMPATIBILITY.md`
- OpenClaw 接入映射：`docs/OPENCLAW_INTEGRATION.md`
- OpenClaw 最小规则：`docs/OPENCLAW_RULE.md`
- 外部对象最小入口：`docs/AGENT_ENTRY_RULE.md`
- 外部对象工作流：`docs/AGENT_WORKFLOW.md`
- Codex 主窗口工作流：`docs/CODEX_WORKFLOW.md`
- 日常运维：`docs/RUNBOOK.md`

## 边界说明

- Relay Hub 的协议层是通用的，但仓库自带的“常驻自动 worker”目前只打包了 `Claude Code`
- Relay Hub 的渠道层不是只支持飞书 / 微信；凡是 `OpenClaw` 能通过 `openclaw message send` 发出的渠道都可以接
- 飞书 / 微信参数只是安装器里的快捷写法，不是协议限制
- 当前仓库的现成后台服务托管是 `macOS + launchd`
- Relay Hub 依赖 `OpenClaw` 做消息网关，不直接对接别的渠道网关
- Relay Hub 的网页 branch 不是主对话本身，而是主线分支
- 当前主对话窗口仍然是主线
- OpenClaw 不负责主线快照和 merge-back
- 外部对象不应直接读取飞书 / 微信原始渠道
- OpenClaw 也不应自己翻 `routes.json`、`messages/*.md`

所有渠道读写都应该通过固定桥接 CLI 完成。
