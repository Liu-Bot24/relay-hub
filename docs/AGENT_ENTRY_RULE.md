# Relay Hub Minimal Agent Entry

把这份文件和仓库根的 `RELAY_PROTOCOL.md` 一起发给任意外部 AI，就够它建立最小配合关系。需要详细操作时，再补 `docs/AGENT_WORKFLOW.md`。

注意：

- 这份文件描述的是运行期动作
- 如果当前仍处于安装阶段，优先看 `docs/AI_INSTALL_PROMPT.md` 和 `docs/GENERIC_HOST_BOOTSTRAP.md`
- 通用默认的 merge-back 方式是：用户显式说 `合流上下文`

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
  1. 在自己的环境里创建或刷新一份最小长期规则 / skill / guide。
  2. 确定当前项目根目录。
  3. 复用或创建当前项目的 `DEVELOPMENT_LOG.md`。
  4. 写入一条主线快照。
  5. 以完整参数执行一次 `enable-relay --start-pickup`。
  6. pickup 真正运行后，才把自己视为 `ready`。
  7. 如果返回里出现 `resume_candidates`，提醒用户可说“合流上下文”先把旧 branch 接回主窗口。

- “Relay Hub 状态”
  1. 先确保 Relay Hub 跟随到用户当前正在使用的主对话。
  2. 返回自己当前是否 `ready`。
  3. 返回 pickup 是否在运行。
  4. 返回是否有待处理 branch、待合流 branch 或仅入口已打开但尚未开始的 entry。

- “合流上下文”
  1. 先确保 Relay Hub 跟随到用户当前正在使用的主对话。
  2. 复用当前主对话对应的 `main_session_ref`。
  3. 执行 `resume-main`。
  4. 如果返回里有多条 `resume_candidates`，不要猜测，明确让用户选先合哪一条。
  5. 合流成功后，再继续当前主窗口对话。

- “退出 Relay Hub”
  1. 执行 `stop-pickup`。
  2. 把自己标记为 `offline`。
  3. 不要顺手改 OpenClaw 的渠道配置。

处理 branch 时，再记住这几件事：

1. 同一主对话必须稳定复用同一个 `main_session_ref`；只有用户明确进入新主对话时，才换新的 ref。
2. 如果 branch 是你从主窗口主动开的，应显式绑定 `main_session_ref`、主线摘要、项目根目录和开发日志路径。
3. 如果 branch 是 OpenClaw 先开的，你第一次正式接单时必须补齐 `main_session_ref`、当前项目根目录、开发日志路径，以及缺失的主线摘要。
4. 完整支持模式下，只要自己是 `ready`，就应让持续接单机制保持运行并接走分配给自己的 `queued` branch；不能只会手动执行一次 `claim-next`。
5. 处理前，先读取 `main_context`、开发日志增量和当前 cycle 的 branch transcript。
6. 通用默认是：用户显式说“合流上下文”时再执行 `resume-main`；只有当前宿主确实已经落下可靠的前置 hook / pre-user 机制时，才允许自动做同样动作。
7. 只要当前仍处于 Relay Hub 已接入状态，主窗口里的正常回复默认也应镜像成提醒；优先使用 `relay_after_reply_hook.py`，否则使用宿主持久规则里的回复收尾流程；不要把“出问题时手动补跑一次”当成已经完成接入。
8. 若协议缺失、session 不存在、`main_session_ref` 不匹配，或 branch 尚未开始，就先报错或提示，不要自行猜测。
```
