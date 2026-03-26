# Codex Main-Window Workflow

这份文件只描述一件事：

如果当前这个 Codex 对话窗口是主线，那么它应该如何使用 Relay Hub 的 branch。

如果你要给任意对象用一份通用说明，优先看 `docs/AGENT_WORKFLOW.md`。这份文件只保留 Codex 的兼容示例。

说明：

- 下文里的 `feishu / ou_demo` 只是 Codex 示例
- 不是说 Codex 只能跟飞书配合

## 核心心智模型

- 当前 Codex 对话窗口是主线
- Relay 网页 / md 是 branch
- branch 打开时，要继承主线快照
- branch 结束后，要把增量 merge back 到主线

## 最推荐的命令

### 1. 从主线打开一个 branch

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py --agent codex start-branch \
  --channel feishu \
  --target ou_demo \
  --main-context-body "这里放主对话窗口导出的背景摘要。"
```

兼容写法仍然可用：

```bash
cd /path/to/relay-hub
python3 scripts/codex_relay.py start-branch \
  --channel feishu \
  --target ou_demo \
  --main-context-body "这里放主对话窗口导出的背景摘要。"
```

### 2. 如果主窗口后来又补充了一句

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py append-main-note \
  --session feishu__ou_demo \
  --body "这是主窗口后来追加给 branch 的说明。"
```

### 3. branch 要开始处理前

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py branch-context --session feishu__ou_demo
```

这条命令返回：

- `main_context`
- `branch_messages`

Codex 处理 branch 时，应该把这两部分一起看。

### 4. branch 结束，回到主窗口继续聊

```bash
cd /path/to/relay-hub
python3 scripts/agent_relay.py merge-back --session feishu__ou_demo
```

它会返回一段 `merge_back_text`。  
主窗口应把这段增量视为“刚刚发生过的 branch 内容”，再继续往下聊。

### 5. merge 完后标记水位

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
