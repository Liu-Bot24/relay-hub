# Generic Agent Workflow

这份文件描述的是任意外部对象如何接入 Relay Hub。

适用对象包括但不限于：

- `codex`
- `claude-code`
- `gemini-cli`
- `cursor-cli`
- `opencode`
- 任何能执行命令并长期记住最小规则的 AI / 程序

## 核心心智模型

- 当前 AI 主对话窗口是主线
- Relay 网页 / md 是 branch
- branch 打开时，要继承主线快照
- branch 结束后，要把增量 merge back 到主线
- 用户可见输出仍然只通过 OpenClaw 渠道发出

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
python3 /path/to/relay-hub/scripts/agent_relay.py --agent opencode ...
```

## 1. 标记在线

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent claude-code set-presence --status ready
```

## 2. 从主线打开一个 branch

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent claude-code start-branch \
  --channel feishu \
  --target ou_demo \
  --main-context-body "这里放主对话窗口导出的背景摘要。"
```

如果你已经设置了 `RELAY_AGENT_ID`，就不用重复传 `--agent`。

## 3. 如果主窗口后来又补充了一句

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py append-main-note \
  --session feishu__ou_demo \
  --body "这是主窗口后来追加给 branch 的说明。"
```

## 4. 用户说“已录入”后，接单

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent claude-code claim-next
```

返回里会带：

- `session_key`
- `last_user_message`
- `meta`

## 5. 真正处理前，读取 branch 上下文

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py branch-context --session feishu__ou_demo
```

这条命令返回：

- `main_context`
- `branch_messages`

处理 branch 时，应把这两部分一起看。

## 6. 写回进度或最终结果

进度：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent claude-code reply \
  --session feishu__ou_demo \
  --kind progress \
  --body "正在整理中。"
```

最终结果：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent claude-code reply \
  --session feishu__ou_demo \
  --kind final \
  --body "这是最终回复。"
```

错误结果：

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent claude-code reply \
  --session feishu__ou_demo \
  --kind error \
  --body "处理失败，请重试。"
```

这些消息不会直接发给用户；它们会进入待发送队列，再由 OpenClaw 渠道发出。

## 7. branch 结束，回到主窗口继续聊

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py merge-back --session feishu__ou_demo
```

它会返回一段 `merge_back_text`。  
主窗口应把这段增量视为“刚刚发生过的 branch 内容”，再继续往下聊。

## 8. merge 完后标记水位

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py merge-back --session feishu__ou_demo --mark-merged
```

这样下一次再回主窗口时，只会拿到新的 branch 增量。

## 边界

- OpenClaw 不负责主线快照和 merge-back
- OpenClaw 只管 branch 入口、`已录入`、渠道发送、退出
- main chat 和 branch 不是并列双主线
- branch 只是主线的外部分支工作区
- 如果仓库里同时存在专用壳，例如 `scripts/codex_relay.py`，它只是兼容入口；通用入口仍然是 `scripts/agent_relay.py`
