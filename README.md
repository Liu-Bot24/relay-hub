# Relay Hub

Relay Hub 是一套把 `OpenClaw`、本地网页入口、以及外部编码对象连接起来的分支式对话桥。

## 最短人类操作手册

如果你的目标是“把这个仓库交给 AI，让它自己部署到可用状态”，最低门槛的路径就是：

1. 把下面这整段“发给 AI 编程工具的话”直接发给它
2. 等它确认安装完成
3. 再把“发给 OpenClaw 的话”发给 `OpenClaw`

发给 AI 编程工具的话：

```text
你现在正在处理位于 [本包所在路径] 的 Relay Hub 仓库。请在该仓库根目录工作，并严格按下面流程执行，不要自行简化步骤。

先阅读这些文件：
1. README.md
2. RELAY_PROTOCOL.md
3. docs/INSTALL_PLAYBOOK.md
4. docs/COMPATIBILITY.md
5. docs/AGENT_ENTRY_RULE.md
6. docs/AGENT_WORKFLOW.md

先自己确定这一个值，不要先来问我：

1. 仓库路径
- 这个包本身的路径就是 relay-hub 仓库路径
- 如果你当前已经在仓库根目录，就直接使用当前目录
- 如果你不在仓库根目录，就自动定位到包含 README.md、install.py、RELAY_PROTOCOL.md 的那个目录

你的 agent_id 用你自己的标准名字：
- Claude Code -> claude-code
- Codex -> codex
- Gemini CLI -> gemini-cli
- Cursor CLI -> cursor-cli
- Opencode -> opencode

然后执行安装：
cd [本包所在路径]
python3 install.py full --load-services

说明：
- install.py 会自动探测本机局域网 IPv4，并生成 web_base_url；只有探测失败时，才回头问我
- 默认不要求你先配置额外渠道目标；如果安装时没有显式配置额外渠道，回包就默认走原始触发渠道
- 如果用户后面明确要求“除原始触发渠道外，还要额外镜像到别的渠道”，那时再执行 install.py install-openclaw --delivery-channel channel=target --delivery-account channel=accountId
- 仓库默认只安装通用层：OpenClaw 桥接、网页入口、协议文件、Web 服务；不为任何特定 AI 内置后台 worker

安装完成后，再执行：
1. python3 install.py doctor
2. python3 install.py status

成功标准：
- doctor 返回 ok=true
- status 能看到 openclaw bridge、skill、heartbeat、web plist

注意：
- 不要直接读取原始消息渠道或 OpenClaw 插件内部实现
- 不要自行做业务对话测试，除非我明确要求
- 如果安装失败，就原样贴出失败点并停止，不要自创旁路方案
- 当我直接对你说“接入 Relay Hub”时，你应把自己标记为 ready
- 当我直接对你说“Relay Hub 状态”时，你应告诉我你当前是否 ready，以及是否有待处理 branch
- 当我直接对你说“退出 Relay Hub”时，你应把自己标记为 offline
```

发给 OpenClaw 的话：

```text
这是一个已经安装 Relay Hub 的仓库。请先阅读：
1. README.md
2. docs/OPENCLAW_RULE.md
3. docs/OPENCLAW_INTEGRATION.md
4. docs/COMPATIBILITY.md

你只负责这 5 件事：
1. 当我说“打开 <agent> 入口”时，调用已安装的 relay bridge 打开入口
2. 当我说“已录入”时，把 branch 入队，并在需要时等待 claim
3. 当我说“状态”时，查询 branch 状态
4. 当有待发送回包时，发送到消息渠道并 ack-delivery
5. 当我说“退出”时，退出 relay

注意：
- 不要直接读取 routes.json、state.json、messages/*.md
- 不要自己解释协议细节，只调用桥接脚本
- 你是渠道网关，不是主记忆体
- main_context 和 merge-back 不由你负责
```

## 用户实际会说的话

对 AI 编程工具侧会话：

- 让它进入可接单状态：
  `接入 Relay Hub`
- 查询它当前是否已接入：
  `Relay Hub 状态`
- 让它退出可接单状态：
  `退出 Relay Hub`

对 OpenClaw / 用户侧会话：

- 开启某个对象的 relay 分支：
  `打开 <agent> 入口`
- 查询当前分支状态：
  `状态`
- 关闭当前 relay 分支并恢复 OpenClaw 正常模式：
  `退出`

AI 侧内部实际怎么执行这些动作，见 `docs/AGENT_WORKFLOW.md`。

## 这套机制的工作方式

- 用户仍然在 `OpenClaw` 已连接的消息渠道里交互
- 真正的录入入口放在本地网页
- 外部对象如 `Codex / Claude Code / Gemini CLI / Cursor CLI / Opencode` 只读写统一协议
- OpenClaw 只负责“开入口、收已录入、查状态、退出、发回包”
- 主对话窗口仍然是主线，网页 branch 只是分支记录

## 仓库里已经包含

- 通用协议与通用 CLI
- 本地网页入口
- OpenClaw 渠道桥接
- `launchd` 级别的 Web 服务安装能力
- 给外部对象和 OpenClaw 的最小规则文档
- 安装自检命令

更细的版本见：

- 安装章程：`docs/INSTALL_PLAYBOOK.md`
- 通用性审计：`docs/COMPATIBILITY.md`

通用性边界见 `docs/COMPATIBILITY.md`。当前最短可用组合是：

- `macOS`
- `OpenClaw`
- 任意一个能按协议接入的 AI 编程工具

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

## 一条命令完成安装

建议先做一次自检：

```bash
cd /path/to/relay-hub
python3 install.py doctor
```

确认基础依赖没问题后，再执行安装。

最常见的安装方式是：

```bash
cd /path/to/relay-hub
python3 install.py full --load-services
```

说明：

- `install.py` 会优先自动探测局域网可访问地址，作为网页入口地址
- `--load-services` 会把当前安装里需要的服务直接装进 `launchd`
- 基线安装默认不要求你先填渠道目标；回包默认走原始触发渠道
- 基线安装不会替任何特定 AI 安装后台 worker；外部对象后续按协议自行接入
- 如果你暂时只想装 OpenClaw 侧，不启服务，可以去掉 `--load-services`

如果你后面明确要加“额外镜像渠道”，再执行：

```bash
python3 install.py install-openclaw \
  --delivery-channel channel_a=target_a \
  --delivery-channel channel_b=target_b \
  --delivery-account channel_b=account_b
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
8. 如带 `--load-services`，会直接加载并启动 Web 服务

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
5. 外部对象按协议 claim 队列并处理
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
  --delivery-channel channel_a=target_a \
  --delivery-channel channel_b=target_b \
  --delivery-account channel_b=account_b
```

只安装或更新 `launchd` 服务：

```bash
cd /path/to/relay-hub
python3 install.py install-launchd --load-services
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

- Relay Hub 的协议层是通用的，但仓库当前不内置任何特定 AI 的常驻 worker
- Relay Hub 的渠道层不是只支持某几个预设渠道；凡是 `OpenClaw` 能通过 `openclaw message send` 发出的渠道都可以接
- 某些特定渠道参数只是安装器里的快捷写法，不是协议限制
- 当前仓库的现成后台服务托管是 `macOS + launchd`
- Relay Hub 依赖 `OpenClaw` 做消息网关，不直接对接别的渠道网关
- Relay Hub 的网页 branch 不是主对话本身，而是主线分支
- 当前主对话窗口仍然是主线
- OpenClaw 不负责主线快照和 merge-back
- 外部对象不应直接读取原始消息渠道
- OpenClaw 也不应自己翻 `routes.json`、`messages/*.md`

所有渠道读写都应该通过固定桥接 CLI 完成。
