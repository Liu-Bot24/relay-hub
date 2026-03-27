# Relay Hub

Relay Hub 把三件事连到一起：

- `OpenClaw` 负责消息渠道
- 本地网页负责录入 branch 内容
- AI 编程工具按统一协议接入并处理 branch

主线始终是 AI 自己的主对话窗口；网页只是分支工作区，不是第二条主聊天。网页链接发出时只是入口打开，用户第一次在网页里保存消息时，branch 才正式开始。

## 最短人类操作手册

如果你的目标是“把这个仓库交给 AI，让它自己部署到可用状态”，就按下面两步做：

1. 把“发给 AI 编程工具的话”整段发给它
2. 等它确认安装完成后，再把“发给 OpenClaw 的话”发给 `OpenClaw`

### 发给 AI 编程工具的话

```text
你现在正在处理位于 [本包所在路径] 的 Relay Hub 仓库。这个路径就是当前这个包解压或克隆后的目录。请在该仓库根目录工作，并严格按下面流程执行，不要自行简化步骤。

先优先阅读这 4 个关键文件：
1. README.md
2. RELAY_PROTOCOL.md
3. docs/INTEGRATION_CONTRACT.md
4. docs/AGENT_ENTRY_RULE.md

如果读完上面 4 个文件后还需要具体安装细节，再补读：
5. docs/INSTALL_PLAYBOOK.md
6. docs/AGENT_WORKFLOW.md
7. docs/COMPATIBILITY.md

先自己确定下面两件事，不要先来问我：
1. 仓库根目录
- 如果你当前已经在仓库根目录，就直接使用当前目录
- 如果你不在仓库根目录，就自动定位到同时包含 README.md、install.py、RELAY_PROTOCOL.md 的目录
2. 你的 agent_id
- Codex -> codex
- Claude Code -> claude-code
- Gemini CLI -> gemini-cli
- Cursor CLI -> cursor-cli
- Opencode -> opencode
- 其他工具 -> 用你自己稳定的名字

然后执行安装：
cd [本包所在路径]
python3 install.py full --load-services

安装完成后，再执行：
1. python3 install.py doctor
2. python3 install.py status

安装完成标准：
- doctor 返回 ok=true
- status 能看到 openclaw bridge、skill、heartbeat、web plist

完整接入标准：
- 你已经在自己的环境里固化最小长期规则 / skill / guide
- 你已经明确当前主对话如何稳定生成并复用 main_session_ref
- 你已经进入 ready，并且能在自己的环境里持续接单；如果做不到，就明确说明当前只能 manual-only

安装要求：
- install.py 会自动探测本机局域网地址；只有探测失败时，才回头问我
- 默认不要求你先配置额外消息渠道；如果没有显式配置，回包默认走原始触发渠道
- 如果我后面明确要求“除原始触发渠道外，还要额外镜像到别的渠道”，那时你再执行：
  python3 install.py install-openclaw --delivery-channel channel=target --delivery-account channel=accountId
- 不要直接读取原始消息渠道或 OpenClaw 插件内部实现
- 不要自行做业务对话测试，除非我明确要求
- 如果安装失败，就原样贴出失败点并停止，不要自创旁路方案
- 当我对你说“接入 Relay Hub”时：
  1. 先确定当前项目根目录
  2. 查找 DEVELOPMENT_LOG.md；如果没有，就在项目根目录创建
  3. 立即写入一条当前主线快照
  4. 然后再把自己标记为 ready
  5. 并在你自己的环境里开启持续接单机制；最低要求是：只要自己是 ready，就周期性检查 queued branch，发现后立即 claim-next -> branch-context -> reply；如果你的环境根本做不到持续接单，就明确告诉我当前只支持 manual-only，不要假装已经完整接入
- 当我对你说“Relay Hub 状态”时，告诉我你当前是否 ready，以及是否有待处理 branch
- 当我对你说“退出 Relay Hub”时，把自己标记为 offline，并关闭持续接单机制
- 当 OpenClaw 先帮我打开网页入口时，不要把那一刻当成 branch 已开始；用户第一次在网页里保存消息时，branch 才正式开始
- 你必须为每条 AI 主对话稳定维护一个 main_session_ref：
  1. 优先使用宿主环境原生提供的 conversation / thread / session id
  2. 如果宿主没有提供，就在当前主对话第一次接入 Relay Hub 时生成一个稳定 ref，并把它固化到当前主对话可持续复用的宿主载体里，再在该主对话范围内持续复用；不能只把它留在单条回复里
- 当你第一次正式接 OpenClaw 打开的 branch 时，必须补齐：
  1. main_session_ref
  2. 当前主线摘要
  3. 当前项目根目录 / 开发日志绑定
- 当你已经是 ready 时，不能只会手动执行一次 claim-next；完整支持模式下，你应持续监控 queued branch，并在自己的环境里接单处理
- 当我回到当前主对话窗口说第一句话时，先执行一次 resume-main，把 branch 增量合流回主线，再继续回答我
```

### 发给 OpenClaw 的话

```text
这是一个已经安装 Relay Hub 的仓库。请先阅读：
1. README.md
2. docs/OPENCLAW_RULE.md
3. docs/OPENCLAW_INTEGRATION.md
4. docs/INTEGRATION_CONTRACT.md
5. docs/COMPATIBILITY.md

你只负责这 5 件事：
1. 当我说“打开 <agent> 入口”时，调用已安装的 relay bridge 打开入口
2. 当我说“已录入”时，把 branch 入队，并在需要时等待 claim
3. 当我说“状态”时，查询当前 branch 状态
4. 当有待发送回包时，把它发到消息渠道并 ack-delivery
5. 当我说“退出”时，退出 relay

注意：
- 不要直接读取 routes.json、state.json、messages/*.md
- 不要自己解释协议细节，只调用桥接脚本
- 你是渠道网关，不是主记忆体
- main_context 和 merge-back 不由你负责
- 当前渠道和当前目标，默认必须从当前入站消息上下文里获取；只有宿主真的拿不到时，才回问用户
- 如果当前渠道对象已经有 branch，你必须主动问用户“复用入口”还是“新建入口”，不能自己替用户决定
- 一旦你已经问出了“复用/新建”，就必须把这次待确认的 agent、channel、target 记为当前待确认入口；如果用户下一句只回答“复用”或“新建”，仍然按同一组参数重调，不要在第二轮丢上下文
```

## 用户实际会说的话

对 AI 编程工具：

- `接入 Relay Hub`
- `Relay Hub 状态`
- `退出 Relay Hub`

对 OpenClaw：

- `打开 <agent> 入口`
- `已录入`
- `状态`
- `退出`

## 一条命令完成安装

安装和更新的主入口只有这一条：

```bash
cd [本包所在路径]
python3 install.py full --load-services
```

说明：

- `install.py` 会自动探测局域网可访问地址，生成网页入口地址
- `--load-services` 会把 Web 服务直接装进 `launchd`
- 默认不要求先填写消息渠道目标；回包默认走原始触发渠道
- 如果后面配置了额外回传渠道，那些渠道只是额外镜像；原始触发渠道仍然保留
- 如果这台机器之前已经配置过额外回传渠道，重装时不显式传参也会保留原配置
- 如果你只想先装文件，不想立即加载服务，可以去掉 `--load-services`

建议安装后再执行两条检查：

```bash
cd [本包所在路径]
python3 install.py doctor
python3 install.py status
```

## 这条安装命令会做什么

`python3 install.py full --load-services` 会：

1. 初始化默认 runtime：
   - `~/Library/Application Support/RelayHub/runtime`
2. 安装 OpenClaw 桥接脚本：
   - `~/.openclaw/workspace/scripts/relay_openclaw_bridge.py`
3. 写入 OpenClaw 配置：
   - `~/.openclaw/workspace/data/relay_hub_openclaw.json`
4. 安装 OpenClaw skill：
   - `~/.openclaw/workspace/skills/relay-hub-openclaw/SKILL.md`
5. 给 `HEARTBEAT.md` 加上回包发送泵
6. 把程序副本放到：
   - `~/Library/Application Support/RelayHub/app`
7. 写入并加载 Web 服务：
   - `com.relayhub.web`

程序副本和默认 runtime 放在 `Application Support`，是为了避开 macOS 对 `Desktop/Documents` 后台服务的权限限制。

## 安装后怎么用

装完以后，正常流程是：

1. 用户在 OpenClaw 里说：`打开 <agent> 入口`
2. OpenClaw 返回网页入口
3. 用户第一次在网页里保存消息，branch 才正式开始
4. 用户继续在网页里写 branch 内容
5. 用户回到 OpenClaw 说：`已录入`
6. 外部 AI 按协议接手 branch
7. 处理结果通过 OpenClaw 发回原消息渠道
8. 用户回到 AI 主窗口说第一句话时，AI 先做一次 merge-back，再继续主线对话

## 仓库结构

```text
relay-hub/
  README.md
  install.py
  RELAY_PROTOCOL.md
  docs/
    INSTALL_PLAYBOOK.md
    INTEGRATION_CONTRACT.md
    COMPATIBILITY.md
    RUNBOOK.md
    AGENT_ENTRY_RULE.md
    AGENT_WORKFLOW.md
    OPENCLAW_INTEGRATION.md
    OPENCLAW_RULE.md
  scripts/
    relay_openclaw_bridge.py
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

- `macOS`
- `python3`
- 已安装并可用的 `OpenClaw`
- 至少一个可按协议接入的 AI 编程工具

## 常用维护命令

查看当前安装状态：

```bash
cd [本包所在路径]
python3 install.py status
```

只重装 OpenClaw 侧桥接：

```bash
cd [本包所在路径]
python3 install.py install-openclaw \
  --delivery-channel <channel_a>=<target_a> \
  --delivery-channel <channel_b>=<target_b> \
  --delivery-account <channel_b>=<account_b>
```

只安装或更新 `launchd` 服务：

```bash
cd [本包所在路径]
python3 install.py install-launchd --load-services
```

## 文档入口

- 通用协议：`RELAY_PROTOCOL.md`
- 安装章程：`docs/INSTALL_PLAYBOOK.md`
- 接入硬章程：`docs/INTEGRATION_CONTRACT.md`
- 通用性审计：`docs/COMPATIBILITY.md`
- OpenClaw 接入映射：`docs/OPENCLAW_INTEGRATION.md`
- OpenClaw 最小规则：`docs/OPENCLAW_RULE.md`
- 外部对象最小入口：`docs/AGENT_ENTRY_RULE.md`
- 外部对象工作流：`docs/AGENT_WORKFLOW.md`
- 日常运维：`docs/RUNBOOK.md`

## 边界说明

- Relay Hub 的协议层是通用的，但外部 AI 仍需要在安装后按协议自己接入
- 消息渠道统一走 OpenClaw；只要该渠道已经被 OpenClaw 支持，就可以接进 Relay Hub
- 当前仓库现成提供的是 `macOS + launchd` 的安装和服务托管
- Relay Hub 依赖 `OpenClaw` 做消息网关，不直接对接别的渠道网关
- Relay Hub 的网页 branch 不是主对话本身，而是主线分支
- 当前主对话窗口仍然是主线
- 项目开发日志是 branch 上下文和主线合流的重要参考
- 如果项目里没有 `DEVELOPMENT_LOG.md`，启用 Relay Hub 时应自动创建，并把第一条写成主线快照
- OpenClaw 不负责主线快照和 merge-back
- 外部对象不应直接读取原始消息渠道
- OpenClaw 也不应自己翻 `routes.json`、`messages/*.md`

所有渠道读写都应该通过固定桥接 CLI 完成。
