# Generic Agent Workflow

这份文件描述的是任意外部对象如何接入 Relay Hub。

适用对象包括但不限于：

- `codex`
- `claude-code`
- `gemini-cli`
- `cursor-cli`
- `opencode`
- 任何能执行命令并长期记住最小规则的 AI / 程序

说明：

- 下文里的 `agent_demo / channel_a / target_demo` 只是示例
- 协议本身并不要求必须是某个特定对象，也不要求必须是某个特定渠道
- 仓库默认只安装 Relay Hub 本体；外部对象需要按本文件自行接入

## 核心心智模型

- 当前 AI 主对话窗口是主线
- Relay 网页 / md 是 branch
- branch 打开时，要继承主线快照
- branch 结束后，要把增量 merge back 到主线
- 用户可见输出仍然只通过 OpenClaw 渠道发出
- 每条 branch 最终都必须绑定到一个明确的 `main_session_ref`，否则不能安全 merge back

## 最推荐的做法

优先使用通用桥接脚本：

```bash
python3 /path/to/relay-hub/scripts/agent_relay.py
```

你有两种指定自己身份的方式：

1. 每次都传 `--agent`
2. 或者先设置环境变量 `RELAY_AGENT_ID`

例如：

```bash
export RELAY_AGENT_ID=claude-code
```

或者：

```bash
python3 /path/to/relay-hub/scripts/agent_relay.py --agent agent_demo ...
```

`main_session_ref` 是外部 AI 当前这条主对话的稳定标识。
如果宿主工具能提供真实会话 ID，就直接用它；
如果宿主工具不提供，就由该工具自己生成并持续复用一个稳定字符串。

## 用户对 AI 说什么

用户不需要手写命令行，直接对 AI 说这几句就够：

- `接入 Relay Hub`
- `Relay Hub 状态`
- `退出 Relay Hub`

AI 自己应把它们映射成下面的内部动作。

## 1. 标记在线

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo set-presence --status ready
```

查询当前接入状态：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo agent-status
```

如果你要临时关闭接单：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo set-presence --status offline
```

## 2. 从主线打开一个 branch

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo start-branch \
  --channel channel_a \
  --target target_demo \
  --main-session-ref agent_demo_main_001 \
  --main-context-body "这里放主对话窗口导出的背景摘要。"
```

如果你已经设置了 `RELAY_AGENT_ID`，就不用重复传 `--agent`。

## 3. 如果主窗口后来又补充了一句

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py append-main-note \
  --session channel_a__target_demo \
  --body "这是主窗口后来追加给 branch 的说明。"
```

如果这条 branch 不是你主动开的，而是 OpenClaw 先开的，那么它一开始通常还没有 `main_session_ref`。
这时应在你第一次正式接单时完成绑定。

## 4. 用户说“已录入”后，接单

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo claim-next \
  --main-session-ref agent_demo_main_001
```

返回里会带：

- `session_key`
- `last_user_message`
- `meta`

## 5. 真正处理前，读取 branch 上下文

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py branch-context \
  --session channel_a__target_demo \
  --main-session-ref agent_demo_main_001
```

这条命令返回：

- `main_context`
- `main_context_present`
- `branch_messages`

处理 branch 时，应把这两部分一起看。  
如果 `main_context_present = false`，说明这条 branch 目前还没有继承到主线快照；外部对象应谨慎处理，不要假装自己天然拥有主线完整上下文。  
如果传入的 `main_session_ref` 和 branch 已绑定的主会话不一致，命令会直接拒绝继续。

## 6. 写回进度或最终结果

进度：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo reply \
  --session channel_a__target_demo \
  --kind progress \
  --body "正在整理中。"
```

最终结果：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo reply \
  --session channel_a__target_demo \
  --kind final \
  --body "这是最终回复。"
```

错误结果：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent agent_demo reply \
  --session channel_a__target_demo \
  --kind error \
  --body "处理失败，请重试。"
```

这些消息不会直接发给用户；它们会进入待发送队列，再由 OpenClaw 渠道发出。

## 7. branch 结束，回到主窗口继续聊

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py merge-back \
  --session channel_a__target_demo \
  --main-session-ref agent_demo_main_001
```

它会返回一段 `merge_back_text`。  
主窗口应把这段增量视为“刚刚发生过的 branch 内容”，再继续往下聊。  
如果 branch 还没有绑定 `main_session_ref`，或者你传的是另一条主会话的 ref，命令会拒绝执行，防止误并回。

## 8. merge 完后标记水位

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py merge-back \
  --session channel_a__target_demo \
  --main-session-ref agent_demo_main_001 \
  --mark-merged
```

这样下一次再回主窗口时，只会拿到新的 branch 增量。

## 边界

- OpenClaw 不负责主线快照和 merge-back
- OpenClaw 只管 branch 入口、`已录入`、渠道发送、退出
- main chat 和 branch 不是并列双主线
- branch 只是主线的外部分支工作区
- 以 `scripts/agent_relay.py` 作为通用入口，不要依赖私有壳脚本
