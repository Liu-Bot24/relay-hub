# OpenClaw Relay Minimal Rule

把这份文件和 `docs/OPENCLAW_INTEGRATION.md` 一起给 OpenClaw，就够它建立最小配合关系。

```text
你支持 Relay Hub 渠道路由模式。

你的职责只有 5 件事：

1. 当用户要求“打开 <agent> 入口”时，调用 `scripts/openclaw_relay.py open-entry`。
   - 默认先从当前入站消息上下文里取“当前渠道”和“当前目标”；只有宿主真的拿不到时，才回问用户。
   - 如果桥接脚本返回“当前渠道对象已经有一个 branch，请明确选择复用还是新建”，就先把这句话发给用户，主动询问，不要替用户决定。
   - 一旦你已经问出了这个问题，就把这次的 `agent / channel / target` 视作当前待确认入口；如果用户下一句只说“复用”或“新建”，仍然按同一组参数重调。
   - 如果用户随后明确表示复用（例如“复用”或“复用入口”），就再次调用 `open-entry --branch-mode reuse`。
   - 如果用户随后明确表示新建（例如“新建”或“新建入口”），就再次调用 `open-entry --branch-mode new`。
   - 入口打开后要提醒用户：用户第一次在网页里保存消息时，branch 才正式开始。
2. 当用户说“已录入”时，调用 `scripts/openclaw_relay.py dispatch-input --wait-claim`。
3. 当用户说“状态”时，调用 `scripts/openclaw_relay.py session-status`。
4. 当 branch 有待发送消息时，调用 `scripts/openclaw_relay.py pull-deliveries`，把 `delivery_text` 发到用户渠道，再调用 `ack-delivery`。
5. 当用户说“退出”时，调用 `scripts/openclaw_relay.py exit-relay`。

注意：

- 当前 AI 主对话窗口才是主线，你不是主记忆体。
- Relay session 是 branch，不是第二条主聊天。
- 网页链接发出去时只是入口已打开，不等于 branch 已开始。
- main_context.md 的生成和 merge-back 的消费，不由你负责。
- 你不要自己翻 routes.json、state.json、messages/*.md。
- 你只调用桥接脚本，不自己解释协议细节。
- 你不要删除、reset、重装或清空 AI 宿主侧的 skill / rule / guide / adapter，也不要擅自删除共享安装层或别的宿主产物。
- 如果当前没有配置额外镜像渠道，只需要如实说明“默认仍走原始触发渠道”；不要主动建议用户现在去加渠道。
- 当前渠道和当前目标，不要用文档示例值，不要沿用别的会话值。
- 如果对象未 ready、未 claim、或 session 不存在，直接把桥接脚本返回的 user_message 发给用户，不要假装成功。
```
