# Relay Hub Minimal Agent Entry

把这份文件和仓库根的 `RELAY_PROTOCOL.md` 一起发给任意外部 AI，就够它建立最小配合关系。需要详细操作时，再补 `docs/AGENT_WORKFLOW.md`。

```text
你支持 Relay Hub 模式。

先记住这几个硬规则：

1. 当前 AI 主对话窗口才是主线；Relay 网页只是 branch 工作区。
2. OpenClaw 打开网页入口时，只是“入口已打开”；用户第一次在网页里保存消息时，branch 才正式开始。
3. 不要直接读取原始消息渠道或 OpenClaw 插件内部实现。
4. 只处理分配给你自己的 branch。
5. 用户可见输出仍然只通过 OpenClaw 渠道发出。
6. 你如果声称自己“已接入 Relay Hub”，就必须在自己的环境里建立可持续复用的最小机制，而不是每次都临时现想。

用户对你说这些话时，你要这样做：

- “接入 Relay Hub”
  1. 在自己的环境里创建或刷新一份最小长期规则 / skill / guide，使这些规则后续持续生效。
  2. 确定当前项目根目录。
  3. 在项目中查找 DEVELOPMENT_LOG.md；如果没有，就在项目根目录创建一个。
  4. 立即写入一条主线快照，作为 Relay Hub 启用时的上下文基线。
  5. 把自己标记为 ready。
  6. 记住当前项目根目录和开发日志路径，后续 branch 处理与合流优先参考它们。
  7. 在自己的环境里开启持续接单机制；最低要求是：只要自己是 ready，就周期性检查 queued branch，发现后立即 claim-next -> branch-context -> reply；如果你的环境根本做不到持续接单，就明确告诉用户当前只能 manual-only。

- “Relay Hub 状态”
  1. 返回自己当前是否 ready。
  2. 返回是否有待处理 branch、待合流 branch 或仅入口已打开但尚未开始的 entry。

- “退出 Relay Hub”
  1. 关闭持续接单机制。
  2. 把自己标记为 offline。
  3. 不要顺手改 OpenClaw 的渠道配置。

处理 branch 时，再记住这几件事：

1. 你必须为每条 AI 主对话稳定维护一个 `main_session_ref`：
   - 优先使用宿主原生提供的 conversation / thread / session id
   - 如果宿主没有提供，就在当前主对话第一次接入 Relay Hub 时生成一个稳定 ref，并把它固化到当前主对话可持续复用的宿主载体里
   - 同一主对话必须复用同一个 ref；用户明确开启新主对话时才换新的 ref
2. 如果 branch 是你从主对话窗口主动开的，应显式传入：
   - main_session_ref
   - 当前主线摘要
   - 当前项目根目录 / 开发日志路径
3. 如果 branch 是 OpenClaw 先开的，你第一次正式接单时必须：
   - 绑定 main_session_ref
   - 绑定当前项目根目录 / 开发日志路径
   - 如果 branch 还没有主线摘要，就立刻补写
4. 完整支持模式下，只要自己是 ready，就应持续监控并接走分配给自己的 queued branch；不能只会手动执行一次 claim-next。
5. 处理前，先读取：
   - main_context
   - 自入口打开以来的开发日志增量
   - 当前 cycle 的 branch transcript
6. 当用户回到主对话窗口并发送第一句话时，先执行 resume-main，把 branch 增量并回主线，再继续回答当前用户。
7. 若协议缺失、session 不存在、main_session_ref 不匹配，或 branch 尚未开始，就先报错或提示，不要自行猜测。

优先使用仓库里的高层入口：

- scripts/agent_relay.py

只有在高层入口不够时，再调用：

- scripts/relayctl.py
```
