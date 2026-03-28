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
- OpenClaw 打开的链接只是“入口已打开”；用户第一次在网页里保存消息时，branch 才正式开始
- 当 OpenClaw 或外部 AI 发同步提醒时，提醒消息会自动附带网页入口和固定产品操作提示；提醒默认优先复用当前主会话已绑定的 OpenClaw 渠道对象，若额外配置了镜像渠道再一并发送；`打开 <agent> 入口` 仍保留为显式重发入口或会话管理动作
- `main_context.md` 的生成与 `merge-back` 的消费，原则上不由 OpenClaw 负责
- OpenClaw 只管理 branch 的打开、触发、发送和退出
- 当前渠道和当前目标，默认应从当前入站消息上下文里获取；不要使用文档示例值，也不要静默沿用无关会话的渠道或目标

## 1. 打开入口

当用户显式要求重发入口，或要求在已有 branch 上重新做“复用/新建”选择时说：

- `打开 <agent> 入口`

其中 `<agent>` 应使用该外部工具稳定使用的 `agent_id`。常见别名如 `codex / claude / gemini / cursor / opencode` 会由桥接层归一化，但并不限于这些固定名称。

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

这一步发出去的是网页入口，不是“branch 已经开始处理”的信号。

前提：

- 这里的 `<channel>` 和 `<target>` 默认应从当前入站消息上下文里直接取
- 如果宿主没有直接给出，再用宿主可查询的当前会话信息补取
- 只有宿主真的拿不到时，才回问用户

补充规则：

- 如果当前渠道对象还没有 branch，OpenClaw 可以直接打开入口
- 如果当前渠道对象已经有 branch，而这次调用没有显式指定“复用”或“新建”，桥接层会直接返回一条提示，让用户自己选
- `复用` 表示继续使用当前 active branch
- `新建` 表示为同一个 `channel + target` 创建一条全新的 branch，并把该渠道对象的 active alias 切到新 branch
- OpenClaw 不应该静默替用户决定“复用还是新建”
- 因此 OpenClaw 的正确行为是：第一次命中该提示时，主动把问题问给用户，并把当时的 `agent / channel / target` 保留为当前待确认入口；等用户回答后，再带 `--branch-mode reuse` 或 `--branch-mode new`、并继续使用同一组参数重调一次

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

这样下一次 `pull-deliveries` 就不会重复返回它。

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
