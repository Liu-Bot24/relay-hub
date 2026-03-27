# Generic Agent Workflow

这份文件描述任意外部 AI / 程序如何接入 Relay Hub。

适用对象包括但不限于：

- `codex`
- `claude-code`
- `gemini-cli`
- `cursor-cli`
- `opencode`
- 任何能执行命令、长期记住最小规则并稳定复用 `agent_id` 的 AI / 程序

说明：

- 下文里的 `agent_demo / channel_a / target_demo / main_demo_001` 都只是示例
- 协议本身不绑定任何特定 AI，也不绑定任何特定消息渠道
- Relay Hub 默认只安装通用层；外部 AI 需要按本文件自行接入

## 0. 完整支持 vs manual-only

如果一个外部 AI 只会临时执行命令、不会在自己的环境里持续接单，那它只能算：

- `manual-only`

只有当它能在自己的环境里建立最小长期机制，并在 `ready` 时持续接走 `queued` branch，才算：

- `完整支持`

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
- `退出 Relay Hub`

AI 自己应把这些话映射成下面的内部动作。

## 1. 启用 Relay Hub

当用户说“接入 Relay Hub”时：

1. 确定当前项目根目录
2. 查找或创建 `DEVELOPMENT_LOG.md`
3. 写入一条当前主线快照
4. 把自己标记为 ready
5. 在自己的环境里启动持续接单机制

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

然后还要做一件仓库不会替你做的事：

- 在自己的环境里开启持续接单机制

如果宿主环境根本做不到持续接单，应明确告诉用户当前只能 `manual-only`。

最简单、最通用的最低实现可以是：

1. 只要自己是 `ready`
2. 就周期性执行 `agent-status`
3. 若 `queued_count == 0`，继续等待
4. 若 `queued_count > 0`，立刻 `claim-next`
5. 若 branch 缺少主线摘要，再立刻补写
6. 再执行 `branch-context -> reply`

是否用 skill、rule、automation 或宿主自己的 watcher，由接入方自己决定；但这套最小动作链不能缺。

## 2. 查询当前接入状态

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo agent-status
```

重点看：

- 是否 `ready`
- 是否有 `queued / processing / awaiting_user / entry_open`

其中：

- `entry_open` 表示入口已打开，但用户还没在网页里写第一条消息
- `input_open` 表示 branch 已开始，用户还在继续网页录入

## 2.1 main_session_ref 规范

每条 AI 主对话都必须稳定维护一个 `main_session_ref`。

优先级从高到低：

1. 优先用宿主环境原生提供的 conversation / thread / session id
2. 如果宿主没有暴露原生会话标识，就在该主对话第一次“接入 Relay Hub”时生成一个稳定 ref，并把它存进当前主对话可持续复用的宿主载体

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

当用户回到当前 AI 主窗口，并发送第一句话时：

1. 先执行 `resume-main`
2. 读取 `merge_back_text`
3. 把它视为“刚刚发生过的 branch 增量”
4. 再继续回答当前这句新消息

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
