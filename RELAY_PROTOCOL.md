# Unified Relay Protocol

适用对象：

- OpenClaw
- Codex
- Claude Code
- Gemini CLI
- Cursor CLI
- Opencode
- 任意其他希望借用 OpenClaw 渠道的外部程序

这是一份仓库内的共享协议。任何对象只要按它接入，就应当能够：

- 让用户通过网页/程序录入内容
- 让外部 agent 处理 branch
- 让最终消息仍然通过 OpenClaw 的消息渠道发回用户

说明：

- 文中的 `channel_a / channel_b / claude-code` 多数是示例名
- 协议本身不限定必须是这些渠道或对象
- 真正的通用性边界见 `docs/COMPATIBILITY.md`

## 1. 核心原则

1. 当前 AI 主对话窗口才是主线。
2. Relay session 只是主线分出去的 branch，不是第二条主聊天。
3. OpenClaw 打开网页链接时，只是“入口已打开”；用户第一次在网页里保存消息时，branch 才正式开始。
4. 用户可见输出必须通过 OpenClaw 渠道发送。
5. 外部 agent 不直接读原始消息渠道或 OpenClaw 插件内部实现。
6. 文件系统是 relay branch transcript 的真源。
7. 开发日志是 branch 上下文和主线合流的重要参考。
8. 只有当用户显式说“已录入”后，branch 的新输入才进入待处理队列。

## 2. 角色分工

### OpenClaw

只做渠道网关：

- 打开入口
- 收“已录入”
- 查状态
- 退出 relay
- 发送待投递回包

### Relay Hub

是确定性的本地程序，负责：

- 管理 `routes / agents / sessions`
- 保存 branch transcript
- 维护网页入口
- 构建 branch context
- 产出 merge-back 增量

### Web UI / Program

只负责：

- 浏览 branch 历史
- 写入新用户消息
- 展示主对话快照

它不直接给用户发消息渠道。

### External Agent

例如：

- `codex`
- `claude-code`
- `gemini-cli`
- `cursor-cli`
- `opencode`

它负责：

- 读取分配给自己的 branch
- 写入 `progress / final / error`
- 必要时读取 merge-back 增量

## 3. 推荐目录

推荐默认根目录：

```text
$HOME/AgentRelayHub
```

推荐结构：

```text
AgentRelayHub/
  config.json
  routes.json
  agents/
    codex.json
    claude-code.json
  sessions/
    channel_a__target_demo/
      meta.json
      state.json
      main_context.md
      messages/
        000001.user.md
        000002.progress.codex.md
        000003.final.codex.md
      attachments/
  logs/
    relay.jsonl
```

推荐 `config.json`：

```json
{
  "version": 1,
  "relay_root": "/path/to/AgentRelayHub",
  "web_base_url": "http://127.0.0.1:4317",
  "default_delivery": {
    "mode": "all",
    "channels": ["channel_a", "channel_b"]
  },
  "queue_ack_timeout_seconds": 15
}
```

## 4. 会话命名

`session_key` 推荐格式：

```text
<channel>__<target>
```

示例：

```text
channel_a__target_demo
channel_b__target_secondary
```

## 5. routes.json

`routes.json` 表示“当前谁在接管哪个会话”。

示例：

```json
{
  "version": 1,
  "updated_at": "2026-03-27T10:00:00+08:00",
  "routes": {
    "channel_a__target_demo": {
      "mode": "relay",
      "agent": "claude-code",
      "status": "entry_open",
      "web_url": "http://127.0.0.1:4317/session/channel_a__target_demo",
      "default_delivery": {
        "mode": "all",
        "channels": ["channel_a", "channel_b"]
      },
      "last_user_commit_id": "000021",
      "last_agent_message_id": "000022",
      "updated_at": "2026-03-27T10:00:00+08:00"
    }
  }
}
```

## 6. agents/<agent>.json

每个对象都必须有 presence 文件。

示例：

```json
{
  "agent": "claude-code",
  "status": "ready",
  "adapter_version": "1",
  "last_seen_at": "2026-03-27T10:00:00+08:00",
  "capabilities": {
    "read_messages": true,
    "write_progress": true,
    "write_final": true,
    "write_error": true
  }
}
```

`status` 推荐值：

- `ready`
- `busy`
- `offline`
- `error`

## 7. meta.json 与 state.json

`meta.json` 记录较稳定的信息，例如：

- `session_key`
- `channel`
- `target`
- `agent`
- `main_session_ref`
- `project_root`
- `development_log_path`
- `created_at`
- `web_url`
- `default_delivery`

`state.json` 记录动态状态，例如：

- `mode`
- `status`
- `entry_opened_at`
- `branch_started_at`
- `cycle_floor_message_id`
- `dispatch_requested_at`
- `last_user_message_id`
- `last_committed_user_message_id`
- `last_queued_user_message_id`
- `last_agent_message_id`
- `last_delivered_message_id`
- `last_merged_back_message_id`
- `last_merged_back_at`
- `agent_claimed_at`
- `updated_at`

推荐状态机：

- `entry_open`
- `input_open`
- `queued`
- `processing`
- `awaiting_user`
- `error`

## 8. 消息文件

所有 branch 消息都保存为 Markdown 文件，正文用 Markdown，元数据用 YAML front matter。

### 8.1 主对话快照

`main_context.md` 用来记录 branch 继承下来的主线快照。

注意：

- 它不是自动猜出来的
- 只有外部 AI 显式写入时才会生成
- OpenClaw 默认不会替外部 AI 生成这份快照

### 8.2 branch transcript

消息文件名示例：

```text
000001.user.md
000002.progress.claude-code.md
000003.final.claude-code.md
000004.error.claude-code.md
```

用户消息示例：

```md
---
id: "000021"
role: "user"
source: "web-ui"
status: "committed"
agent: "claude-code"
created_at: "2026-03-27T10:00:00+08:00"
committed_at: "2026-03-27T10:01:00+08:00"
reply_expected: true
---
请帮我把这个需求整理成可执行的方案。
```

进度消息示例：

```md
---
id: "000022"
role: "assistant"
kind: "progress"
agent: "claude-code"
source_user_message_id: "000021"
created_at: "2026-03-27T10:01:30+08:00"
deliver_via_openclaw: true
append_web_url: true
---
已确认接单，正在处理。
```

## 9. OpenClaw 与外部 agent 的最小规则

- OpenClaw 只调用桥接 CLI，不自己翻 `routes.json`、`state.json`、`messages/*.md`
- 外部 agent 只调用 `scripts/agent_relay.py` / `scripts/relayctl.py`，不直接碰原始消息渠道
- 用户回到主对话窗口并发送第一句话时，主窗口应先做一次 resume-main，把 branch 增量接回主线，再继续回答当前新消息

## 10. 仓库入口

- OpenClaw 侧：`docs/OPENCLAW_INTEGRATION.md`
- 外部 agent 侧：`docs/AGENT_ENTRY_RULE.md`
- 外部 agent 工作流：`docs/AGENT_WORKFLOW.md`
- 安装与服务：`README.md`
