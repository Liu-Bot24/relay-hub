# Generic Agent Workflow

这份文件描述任意外部 AI / 程序如何接入 Relay Hub。

适用对象：

- 任何能执行命令、长期记住最小规则并稳定复用 `agent_id` 的 AI / 程序

说明：

- 下文里的 `agent_demo / channel_a / target_demo / main_demo_001` 都只是示例
- 协议本身不绑定任何特定 AI，也不绑定任何特定消息渠道
- Relay Hub 默认只安装通用层；外部 AI 需要按本文件自行接入
- 这份文件主要描述的是运行期动作；如果当前仍处于安装阶段，且用户还没说 `接入 Relay Hub`，不要把这里的 `ready` / 持续接单要求直接误报成安装缺项
- 安装阶段该如何判断，优先看 `docs/AI_INSTALL_PROMPT.md` 和 `docs/GENERIC_HOST_BOOTSTRAP.md`

## 0. 目标状态

如果一个外部 AI 只会临时执行命令、不会在自己的环境里持续接单，说明它的接入还没完成。

只有当它能在自己的环境里建立最小长期机制，并在 `ready` 时持续接走 `queued` branch，才算真正接入完成。

Relay Hub 仓库不会替某一家 AI 内置专属后台接单器；接单机制必须由接入方 AI 在自己的环境里落地。

所以从产品角度要分清两件事：

- `安装完成`
  说明仓库和 OpenClaw 侧已经装好
- `完整接入`
  说明外部 AI 也已经把自己的长期规则、`main_session_ref` 规则和持续接单机制落好了

## 核心心智模型

- 当前 AI 主对话窗口是主线
- Relay 网页 / md 是 branch 工作区
- OpenClaw 打开网页入口时，只是“入口已打开”
- 用户第一次在网页里保存消息时，branch 才正式开始
- 开发日志是 branch 上下文和主线合流的重要托底
- branch 结束后，用户回到主窗口说第一句话时，应先把 branch 增量 merge back，再继续回答
- 每条 branch 最终都必须绑定到一个明确的 `main_session_ref`

## 用户对 AI 说什么

用户不需要手写命令行，直接说这几句就够：

- `接入 Relay Hub`
- `Relay Hub 状态`
- `消息提醒状态`
- `开启<渠道>消息提醒`
- `关闭<渠道>消息提醒`
- `合流上下文`
- `退出 Relay Hub`

AI 自己应把这些话映射成下面的内部动作。

## 1. 启用 Relay Hub

当用户说“接入 Relay Hub”时：

1. 确定当前项目根目录
2. 优先复用当前项目已有的 `DEVELOPMENT_LOG.md`（默认项目根；如果宿主环境已有该项目自己的日志路径，就继续用那份）；只有没有时，才在项目根目录创建
3. 写入一条当前主线快照
4. 先执行 `enable-relay`
5. 再为当前主对话启动持续接单机制
6. 只有在持续接单机制已经运行后，才算完整 ready
7. 这一步建立的是“Relay Hub 已开启，并已绑定当前活跃主对话”的状态

推荐直接执行：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo enable-relay \
  --project-root /path/to/project \
  --snapshot-body "这里放当前主线的简洁快照。"
```

这一步会：

- 创建或复用开发日志
- 把当前主线快照写进开发日志
- 记住当前项目根目录和开发日志路径
- 把当前对象状态标记为 `ready`

然后立刻为当前主对话启动持续接单。对仓库外的接入方，优先使用通用 `command` backend：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo start-pickup \
  --main-session-ref main_demo_001 \
  --backend command \
  --backend-command '["your-cli", "your-subcommand", "..."]'
```

仓库当前提供两类 backend 路径：

- `command`：面向任意 CLI 的通用主路径
- 其他内置 backend：如果仓库里存在，就只应视作可选优化实现，不改变通用主路径

如果宿主环境当前根本做不到持续接单，应明确告诉用户当前宿主接入尚未完成。

`enable-relay` 默认会立刻发一条启动提醒到 OpenClaw 渠道；这条提醒不创建 branch，但会自动附带网页入口和固定产品操作提示：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo enable-relay \
  --project-root /path/to/project \
  --snapshot-body "这里放当前主线的简洁快照。"
```

如果当前主会话还没有任何可复用的 OpenClaw 渠道对象，且当前实例也没有配置额外默认提醒渠道，这一步应明确告诉用户“提醒已跳过”，而不是假装发送成功。只有你明确知道当前不该发启动提醒时，才额外加上：

```bash
--no-notify-openclaw
```

只要当前仍处于 Relay Hub 已接入状态，主窗口后续的正常回复默认也应镜像成提醒消息；只有用户明确说不要同步，或你已经执行了“退出 Relay Hub”，才停止。

只要 Relay Hub 还没退出，活跃主会话也应跟随用户当前正在使用的 AI 主对话切换：

1. 回到旧主对话时，复用那条主对话已有的 `main_session_ref`
2. 去到此前没有 Relay Hub 历史的新主对话时，为它建立新的 `main_session_ref`
3. 同一时间只保留一个活跃主会话
4. `project_root` 只用于定位代码目录、开发日志和工作区；不要拿它去猜测未来主对话

如果 `enable-relay` 返回里带了 `resume_candidates`，说明当前主会话下还有未合流的旧 branch。此时要明确提醒用户：

- 可以先说 `合流上下文`，把旧 branch 接回主窗口
- 也可以稍后直接通过网页继续远程处理

优先级规则：

1. 如果宿主能代码级拿到“刚刚发给主窗口的最终正文”，就直接用这份原文镜像。
2. 如果宿主拿不到原文，再退回保底方案：先把同一份最终正文写进临时文件，再执行：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo capture-main-output \
  --main-session-ref main_demo_001 \
  --body-file /path/to/exact_final_body.txt
```

注意：

- 这份文件必须就是主窗口最终正文本身，不允许重新组织一版“差不多意思”的文案。
- `capture-main-output` 是通用精确镜像队列入口：pickup 守护会按原文顺序把它转发到 OpenClaw。
- `mirror-main-output` 仍可用于“需要立即直发”的补救场景，但也必须传入同一份最终正文。
- `notify-openclaw` 仍保留给 startup / 显式提醒场景；主窗口镜像默认不要再手动拼 `--body "<reply body>"`。

这类提醒消息不创建 branch；用户如果真的要远程接管，默认直接点消息里的网页入口即可。`打开 agent_demo 入口` 仍然保留，用于显式重发入口，或在已有 branch 上选择“复用/新建”。

最简单、最通用的最低实现可以是：

1. 只要自己是 `ready`
2. 就周期性执行 `agent-status`
3. 若 `queued_count == 0`，继续等待
4. 若 `queued_count > 0`，立刻 `claim-next`
5. 若 branch 缺少主线摘要，再立刻补写
6. 再执行 `branch-context -> reply`

是否用 skill、rule、automation 或宿主自己的 watcher，由接入方自己决定；但这套最小动作链不能缺。当前仓库也已经提供了最小控制入口：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo pickup-status --main-session-ref main_demo_001
python3 scripts/agent_relay.py --agent agent_demo stop-pickup --main-session-ref main_demo_001
```

## 2. 查询当前接入状态

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo agent-status
```

重点看：

- 是否 `ready`
- 是否有活动中的 pickup
- 是否有 `queued / processing / awaiting_user / entry_open`

其中：

- `entry_open` 表示入口已打开，但用户还没在网页里写第一条消息
- `input_open` 表示 branch 已开始，用户还在继续网页录入

## 2.1 查询消息提醒状态

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo notification-status
```

这个命令只显示当前已经配置好的 OpenClaw 提醒渠道，以及它们现在是开启还是关闭。

## 2.2 开启单个渠道提醒

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo enable-notification-channel --channel "<channel>"
```

例如：

- `飞书` / `feishu`
- `微信` / `weixin` / `wechat` / `openclaw-weixin`
- `telegram` / `tg`

只对当前已经配置好的提醒渠道生效；不会顺手创建一个原本没配置的渠道。

## 2.3 关闭单个渠道提醒

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo disable-notification-channel --channel "<channel>"
```

同样只对当前已经配置好的提醒渠道生效。

## 2.4 main_session_ref 规范

每条 AI 主对话都必须稳定维护一个 `main_session_ref`。

优先级从高到低：

1. 优先用宿主环境原生提供的 conversation / thread / session id
2. 如果宿主没有暴露原生会话标识，就在该主对话第一次被 Relay Hub 接管时生成一个稳定 ref，并把它存进当前主对话可持续复用的宿主载体

要求：

- 同一主对话必须复用同一个 `main_session_ref`
- 用户明确新开主对话时，才换新的 `main_session_ref`
- 不要每次 branch 都重新生成

## 3. 从主线主动打开一个 branch

如果 branch 是你从主窗口主动分出去的，推荐一开始就带上：

- `main_session_ref`
- 当前主线摘要
- 当前项目根目录 / 开发日志

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo start-branch \
  --channel channel_a \
  --target target_demo \
  --main-session-ref main_demo_001 \
  --main-context-body "这里放主对话窗口当前摘要。"
```

这时 branch 会立刻拿到：

- `main_session_ref`
- `main_context`
- 当前项目的开发日志绑定

但即便如此，branch 仍然是在用户第一次保存网页消息时才算正式开始。

## 4. OpenClaw 先开的入口，如何接单

如果入口是 OpenClaw 先开的，那么它一开始通常只有：

- 渠道对象绑定
- 网页入口

它通常还没有：

- `main_session_ref`
- 主线快照
- 项目开发日志绑定

所以你第一次正式接单时，必须把这些补齐：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo claim-next \
  --main-session-ref main_demo_001 \
  --main-context-body "这里放当前主线摘要。"
```

如果你已经先做过 `enable-relay`，这个命令会自动复用你当前项目根目录和开发日志路径，把 branch 绑到当前项目上。

### 4.1 持续接单的最低实现

完整支持模式下，你在自己的环境里至少要做到：

1. 只要自己是 `ready`
2. 就持续检查是否出现新的 `queued` branch
3. 一旦出现，就立刻 `claim-next`
4. 如有需要，补写 `main_context`
5. 再继续 `branch-context -> reply`

这层长期机制可以是：

- skill
- rule
- automation
- watcher
- 任何宿主原生支持的持久化方式

但不能只靠用户每次手动提醒你执行一次命令。

## 5. 真正处理前，读取上下文

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo branch-context \
  --session channel_a__target_demo \
  --main-session-ref main_demo_001
```

返回内容里重点看三块：

- `main_context`
- `development_log`
- `branch_messages`

还会给一段现成的：

- `context_packet_text`

如果你需要低成本把上下文喂给另一个模型，优先用这段打包好的文本。

## 6. 写回进度或最终结果

进度：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo reply \
  --session channel_a__target_demo \
  --kind progress \
  --body "正在处理。"
```

最终结果：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo reply \
  --session channel_a__target_demo \
  --kind final \
  --body "这是最终回复。"
```

这些消息不会直接发给用户；它们会进入待发送队列，再由 OpenClaw 发到真实消息渠道。

## 7. 用户回到主窗口时，先合流再回答

这一步不要等用户手动去 OpenClaw 说“退出”。

如果用户直接对你说 `合流上下文`，也走这一节。

当用户回到当前 AI 主窗口，并发送第一句话时：

1. 先执行 `resume-main`
2. 读取 `merge_back_text`
3. 把它视为“当前主会话最后一句之后、当前这条新输入之前发生的 branch 增量”
4. 先按顺序吸收进当前统一上下文
5. 再继续回答当前这句新消息

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo resume-main \
  --main-session-ref main_demo_001
```

默认行为：

- 自动做 merge-back
- 自动推进 merge 水位
- 自动把该 branch 退出 Relay 模式

如果你确实要合流但暂时不关闭 relay，可以加：

```bash
--keep-relay-open
```

## 8. 退出 Relay Hub

当用户说“退出 Relay Hub”时，先关闭持续接单机制，再把自己标记为 offline：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo stop-pickup --main-session-ref main_demo_001
python3 scripts/agent_relay.py --agent agent_demo disable-relay
```

## 边界

- OpenClaw 不负责主线快照和 merge-back
- OpenClaw 只负责入口、已录入、状态、退出、渠道发回包
- branch 不是第二条主聊天
- branch 只是主线的外部分支工作区
- 如果没有 `main_session_ref`，branch 不能安全 merge back
- 如果项目里没有开发日志，启用 Relay Hub 时应立即创建，并把第一条写成主线快照
- 不要直接读取原始消息渠道
- 不要依赖私有壳脚本；优先用 `scripts/agent_relay.py`
