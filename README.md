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

## 最短人类操作手册

如果你的目标是“把这个仓库交给 AI，让它自己部署到可用状态”，最低门槛的路径就是：

1. 把下面这整段“发给 Claude Code / 其他 AI 编程工具的话”直接发给它
2. 等它确认安装完成
3. 再把“发给 OpenClaw 的话”发给 `OpenClaw`

发给 Claude Code / 其他 AI 编程工具的话：

```text
这是一个 Relay Hub 仓库。请在仓库根目录工作，并严格按下面流程执行，不要自行简化步骤。

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

你的 agent_id 默认按下面处理：
- 如果你是 Claude Code，就用 claude-code
- 如果你不是 Claude Code，就把 claude-code 替换成你自己的 agent_id，例如 codex、gemini-cli、cursor-cli、opencode

然后执行安装：

- 如果你是 Claude Code，执行：
  cd <仓库路径>
  python3 install.py full --worker-agent claude-code --worker-backend manual --load-services

- 如果你不是 Claude Code，执行：
  cd <仓库路径>
  python3 install.py full --worker-agent <你的 agent_id> --worker-backend manual --load-services

说明：
- install.py 会自动探测本机局域网 IPv4，并生成 web_base_url；只有探测失败时，才回头问我
- 默认不要求你先配置飞书、微信或别的渠道目标；如果安装时没有显式配置额外渠道，回包就默认走原始触发渠道
- 如果用户后面明确要求“除原始触发渠道外，还要额外镜像到别的渠道”，那时再执行 install.py install-openclaw --delivery-channel channel=target --delivery-account channel=accountId
- manual 的意思是：仓库不为你内置现成自动 worker，但 OpenClaw 和网页入口会先安装好；后续你再按 docs/AGENT_ENTRY_RULE.md 和 docs/AGENT_WORKFLOW.md 接入

安装完成后，再执行：
1. python3 install.py doctor --worker-backend manual
2. python3 install.py status

成功标准：
- doctor 返回 ok=true
- status 能看到 openclaw bridge、skill、heartbeat、web plist

注意：
- 不要直接读取原始消息渠道或 OpenClaw 插件内部实现
- 不要自行做业务对话测试，除非我明确要求
- 如果安装失败，就原样贴出失败点并停止，不要自创旁路方案
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

如果你想知道这套东西到底通用到什么程度，先看 `docs/COMPATIBILITY.md`。当前最短路径是：

- `macOS`
- `OpenClaw`
- 任意一个能按协议接入的 AI 编程工具（基线走 `manual`）

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
  - 基线安装模式下，不要求它自带现成后台 worker
  - 如果你后面明确要启用仓库内置的 `Claude Code` 自动 worker，再单独加那一步

## 一条命令完成安装

建议先做一次自检：

```bash
cd /path/to/relay-hub
python3 install.py doctor --worker-backend manual
```

确认基础依赖没问题后，再执行安装。

最常见的安装方式是：

```bash
cd /path/to/relay-hub
python3 install.py full \
  --worker-agent claude-code \
  --worker-backend manual \
  --load-services
```

说明：

- `install.py` 会优先自动探测局域网可访问地址，作为网页入口地址
- `--load-services` 会把当前安装里需要的服务直接装进 `launchd`
- 基线安装默认不要求你先填渠道目标；回包默认走原始触发渠道
- 如果你暂时只想装 OpenClaw 侧，不启服务，可以去掉 `--load-services`

如果你后面明确要加“额外镜像渠道”，再执行：

```bash
python3 install.py install-openclaw \
  --delivery-channel feishu=ou_xxx \
  --delivery-channel openclaw-weixin=xxx@im.wechat \
  --delivery-account openclaw-weixin=your-account-id
```

如果你明确要启用仓库内置的 `Claude Code` 自动 worker，再额外执行：

```bash
python3 install.py install-launchd \
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
   - `com.relayhub.worker.<agent>`（仅在你启用现成自动 worker 时）
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
5. 外部对象按协议 claim 队列并处理；如果你启用了现成自动 worker，它会自动 claim
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
- 外部对象不应直接读取原始消息渠道
- OpenClaw 也不应自己翻 `routes.json`、`messages/*.md`

所有渠道读写都应该通过固定桥接 CLI 完成。
