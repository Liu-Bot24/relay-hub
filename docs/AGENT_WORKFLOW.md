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

当用户说“退出 Relay Hub”时，只需要把自己标记为 offline：

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
