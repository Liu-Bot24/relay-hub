# Relay Hub Minimal Agent Entry

把这份文件和仓库根的 `RELAY_PROTOCOL.md` 一起发给任意外部 AI，就够它建立最小配合关系。需要操作手册时，再补 `docs/AGENT_WORKFLOW.md`。

```text
你支持 Relay Hub 模式。

当用户要求你参与 Relay Hub 时：

1. 先读取 RELAY_PROTOCOL.md，并把它视为唯一共享规则。
2. 你的 agent_id 由用户指定，例如 codex / claude-code / gemini-cli / cursor-cli / opencode。
3. 不要直接读原始消息渠道或 OpenClaw 插件内部实现。
4. 把当前 AI 对话窗口视为主线，把 relay session 视为 branch。
5. 处理 branch 前，先读取 main_context.md，再读取 branch transcript。
6. 只处理 routes.json 中 agent 等于你的 session。
7. 你可以写 progress / final / error，但都必须通过 OpenClaw 渠道送达用户。
8. 当用户回到主对话窗口时，应优先使用 merge-back 增量把 branch 新增内容接回主线。
9. 如果协议缺失、session 不存在或状态不一致，先写 error，不要自行猜测。
10. 如果你的环境支持长期配置，请把这段规则固化为最小 skill / rule / project guide / bootstrap prompt，使其后续持续生效。
11. 如果仓库中存在 scripts/agent_relay.py，优先调用它；如果需要更底层能力，再调用 scripts/relayctl.py。
12. 你可以通过 --agent <agent_id> 或 RELAY_AGENT_ID 指定自己的身份，不要把身份写死在协议文件里。
13. 当用户说“接入 Relay Hub”时，把自己标记为 ready。
14. 当用户说“Relay Hub 状态”时，返回自己当前是否 ready，以及是否有待处理 branch。
15. 当用户说“退出 Relay Hub”时，把自己标记为 offline。
```
