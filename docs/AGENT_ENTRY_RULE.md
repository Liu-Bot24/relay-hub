# Relay Hub Minimal Agent Entry

把这份文件和仓库根的 `RELAY_PROTOCOL.md` 一起发给任意外部 AI，就够它建立最小配合关系。需要详细操作时，再补 `docs/AGENT_WORKFLOW.md`。

注意：

- 这份文件主要描述的是“用户已经在主窗口说了 `接入 Relay Hub` 之后”的运行期动作
- 如果当前仍处于安装阶段，且用户还没说 `接入 Relay Hub`，不要把这里的 `ready` / `start-pickup` 运行要求提前套进安装结论
- 安装阶段该如何判断，优先看 `docs/AI_INSTALL_PROMPT.md` 和 `docs/GENERIC_HOST_BOOTSTRAP.md`

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
  3. 优先复用当前项目已有的 DEVELOPMENT_LOG.md（默认项目根；如果你的宿主环境已经明确维护了该项目自己的开发日志路径，就继续用那份）；只有没有时，才在项目根目录创建一个。
  4. 立即写入一条主线快照，作为 Relay Hub 启用时的上下文基线。
     - 如果宿主能拿到主窗口原文：
       - 前三轮对话必须原文保留；
       - 对话不超过 5 轮时，原文全部保留；
       - 对话超过 5 轮时，总结后续对话，并额外保留前三轮原文。
     - 如果宿主拿不到完整的主窗口原文：
       - 退回到宿主可见上下文的最佳努力快照；
       - 明确标注这是“宿主可见上下文重建快照”，不是完整原文回放；
       - 仍应尽量保留宿主当前还能直接访问到的原文轮次，尤其是最早几轮锚点对话。
  5. 执行带完整参数的 `enable-relay --start-pickup`：
     - 对通用宿主，第一次调用就必须带 `--project-root`
     - 对通用宿主，第一次调用就必须带 `--snapshot-body` 或 `--snapshot-file`
     - 不要先裸跑 `enable-relay` 探路
  6. 为当前主对话执行 `start-pickup`，让持续接单机制真正启动。
  7. `enable-relay` 默认就会自动发一条 `startup` 提醒到 OpenClaw 渠道；这条提醒会自动附带网页入口和固定产品操作提示，但不创建 branch，并优先复用当前主会话已绑定的渠道对象；只有在你明确知道当前不该发提醒时，才显式关闭它。
  8. 记住当前项目根目录和开发日志路径，后续 branch 处理与合流优先参考它们。
  9. 如果返回里出现 `resume_candidates`，说明当前主会话下还有未合流的旧 branch；此时要明确提醒用户可说“合流上下文”，先把旧 branch 接回主窗口。
  10. 只有在持续接单机制已经运行后，才能把自己视为完整 ready；如果你的环境根本做不到持续接单，就明确告诉用户当前宿主接入尚未完成。
  11. 从这一步开始，Relay Hub 进入“已开启”状态，并先绑定到当前活跃主对话。

- “Relay Hub 状态”
  1. 先确保 Relay Hub 跟随到用户当前正在使用的主对话。
  2. 返回自己当前是否 ready。
  3. 返回持续接单机制是否在运行。
  4. 返回是否有待处理 branch、待合流 branch 或仅入口已打开但尚未开始的 entry。

- “合流上下文”
  1. 先确保 Relay Hub 跟随到用户当前正在使用的主对话。
  2. 复用当前主对话对应的 `main_session_ref`。
  3. 执行 `resume-main`。
  4. 如果返回里有多条 `resume_candidates`，不要猜测，明确告诉用户当前有多条旧 branch 等待合流，请用户指定要先合哪一条。
  5. 如果合流成功，就在当前主窗口继续后续对话。

- “退出 Relay Hub”
  1. 执行 `stop-pickup`。
  2. 把自己标记为 offline。
  3. 不要顺手改 OpenClaw 的渠道配置。

处理 branch 时，再记住这几件事：

1. 你必须为每条 AI 主对话稳定维护一个 `main_session_ref`：
   - 优先使用宿主原生提供的 conversation / thread / session id
   - 如果宿主没有提供，就在该主对话第一次被 Relay Hub 接管时生成一个稳定 ref，并把它固化到当前主对话可持续复用的宿主载体里
   - 同一主对话必须复用同一个 ref；用户明确开启新主对话时才换新的 ref
2. 如果 branch 是你从主对话窗口主动开的，应显式传入：
   - main_session_ref
   - 当前主线摘要
   - 当前项目根目录 / 开发日志路径
3. 如果 branch 是 OpenClaw 先开的，你第一次正式接单时必须：
   - 绑定 main_session_ref
   - 绑定当前项目根目录 / 开发日志路径
   - 如果 branch 还没有主线摘要，就立刻补写
4. 完整支持模式下，只要自己是 ready，就应让持续接单机制保持运行并接走分配给自己的 queued branch；不能只会手动执行一次 claim-next。
5. 处理前，先读取：
   - main_context
   - 自入口打开以来的开发日志增量
   - 当前 cycle 的 branch transcript
6. 当用户回到主对话窗口并发送第一句话时，先执行 resume-main，把 branch 增量并回主线，再继续回答当前用户。
7. 只要当前仍处于 Relay Hub 已接入状态，主窗口里的正常回复默认也应镜像成提醒；如果仓库里恰好存在你当前宿主的原生正文捕获优化实现，可以优先使用；否则统一走“精确正文捕获队列”：在最终正文已经产出后，把同一份正文写入临时文件，再自动执行 `capture-main-output --body-file <exact_body_file>`。不要再生成第二份措辞相近的新文本，也不要把“出问题时手动补跑一次”当成已经完成接入。
8. 若协议缺失、session 不存在、main_session_ref 不匹配，或 branch 尚未开始，就先报错或提示，不要自行猜测。
9. 当前支持范围内，不要监控项目，也不要靠 `project_root` 猜测未来主对话。Relay Hub 开启后只认“用户当前正在使用的 AI 主对话”：回旧会话续旧会话，去新会话则从新会话开始，但同一时间只保留一个活跃主会话。

优先使用仓库里的高层入口：

- scripts/agent_relay.py
- scripts/relay_agent_daemon.py

其中：

- `scripts/agent_relay.py` 是通用控制入口
- `scripts/relay_agent_daemon.py` 是通用持续接单守护轮子；接入方应为自己的 CLI 选择合适 backend
- `scripts/agent_relay.py capture-main-output` 是通用保底入口：把已经确定的最终正文排进 pickup 守护的精确镜像队列，由代码转发到 OpenClaw；宿主必须把它接进自己“每条主窗口正常回复后自动触发”的机制里
- `scripts/agent_relay.py mirror-main-output` 仍保留给“需要立即直发而不经过队列”的补救场景；它同样要求传入已经确定的最终正文，不能二次生成
- 如果你的宿主没有现成内置 backend，就优先使用 `command` backend 把自己的 CLI 接上

只有在高层入口不够时，再调用：

- scripts/relayctl.py
```
