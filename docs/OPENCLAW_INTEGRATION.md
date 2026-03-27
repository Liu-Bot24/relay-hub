# OpenClaw Integration Mapping

这份文件只定义一件事：

OpenClaw 如果要接 Relay Hub，应该调用哪些桥接命令。

它不讨论 OpenClaw 内部 prompt，也不讨论网页实现细节。  
目标是把 OpenClaw 的职责压缩成“渠道网关 + 触发器”。

推荐入口脚本：

```bash
cd /path/to/relay-hub
python3 scripts/openclaw_relay.py
```

这个脚本同时支持两种 session 定位方式：

- 直接传 `--session channel_a__target_demo`
- 或者更适合 OpenClaw 的 `--channel channel_a --target target_demo`

对于 OpenClaw 来说，优先推荐第二种，因为它天然知道的就是当前渠道和目标身份。

说明：

- 下文里的 `channel_a / target_demo` 只是示例
- 任何 `OpenClaw` 能收发的渠道名与目标标识，都可以替换它

特别说明：

- 当前 AI 主对话窗口才是主线
- Relay session 是从主线分出去的 branch
- OpenClaw 只知道 `channel + target`，不知道外部 AI 当前是哪条主会话
- 所以 OpenClaw 打开的 branch 初始可能是“未绑定主会话”的状态
- `main_context.md` 的生成与 `merge-back` 的消费，原则上不由 OpenClaw 负责
- OpenClaw 只管理 branch 的打开、触发、发送和退出

## 1. 打开入口

当用户说：

- `打开 codex 入口`
- `打开 claude 入口`
- `打开 gemini 入口`
- `打开 cursor 入口`
- `打开 opencode 入口`

OpenClaw 应调用：

```bash
cd /path/to/relay-hub
python3 scripts/openclaw_relay.py \
  --root /path/to/relay-hub/runtime \
  open-entry \
  --agent <agent_id> \
  --channel <channel> \
  --target <target>
```

然后把返回结果里的：

- `branch.meta.web_url`
- `branch.meta.default_delivery`
- `user_message`

发回给用户。

## 2. 已录入

当用户说：

- `已录入`

OpenClaw 应调用：

```bash
cd /path/to/relay-hub
python3 scripts/openclaw_relay.py \
  --root /path/to/relay-hub/runtime \
  dispatch-input \
  --channel <channel> \
  --target <target>
```

如果希望尽量避免“石沉大海”，建议直接带 claim 等待：

```bash
cd /path/to/relay-hub
python3 scripts/openclaw_relay.py \
  --root /path/to/relay-hub/runtime \
  dispatch-input \
  --channel <channel> \
  --target <target> \
  --wait-claim
```

如果返回：

- `claim_wait.claimed = true`

说明对象已经确认接单。  
如果 `claim_wait.claimed = false`，就应该把 `user_message` 原样发给用户。

## 3. 查询状态

当用户说：

- `状态`

OpenClaw 应调用：

```bash
cd /path/to/relay-hub
python3 scripts/openclaw_relay.py \
  --root /path/to/relay-hub/runtime \
  session-status \
  --channel <channel> \
  --target <target>
```

然后把返回里的 `user_message` 发给用户即可。

## 4. 拉取待发送消息

OpenClaw 应定期或在合适时机调用：

```bash
cd /path/to/relay-hub
python3 scripts/openclaw_relay.py \
  --root /path/to/relay-hub/runtime \
  pull-deliveries
```

返回的每一项都已经包含：

- `channel`
- `target`
- `default_delivery`
- `delivery_text`
- `web_url`

OpenClaw 只需要按渠道发出去，不需要自己拼正文。

## 5. 标记已发送

当某条消息已经通过 OpenClaw 成功送出后，应立即调用：

```bash
cd /path/to/relay-hub
python3 scripts/openclaw_relay.py \
  --root /path/to/relay-hub/runtime \
  ack-delivery \
  --channel <channel> \
  --target <target> \
  --message-id 000002
```

这样下一次 `list-pending-delivery` 就不会重复返回它。

## 6. 恢复正常模式

当用户说：

- `退出`

OpenClaw 应调用：

```bash
cd /path/to/relay-hub
python3 scripts/openclaw_relay.py \
  --root /path/to/relay-hub/runtime \
  exit-relay \
  --channel <channel> \
  --target <target>
```

之后该 session 不再继续走 relay 模式，并可把返回的 `user_message` 发给用户。

## 7. 最小原则

OpenClaw 对 Relay Hub 的唯一职责就是：

1. 收用户指令
2. 调 `scripts/openclaw_relay.py`
3. 发网页入口
4. 发待发送消息
5. 标记已送达

不要让 OpenClaw 自己去翻 `routes.json`、`state.json`、`messages/*.md`。  
这些文件应该由 Relay Hub 统一抽象成 CLI。
