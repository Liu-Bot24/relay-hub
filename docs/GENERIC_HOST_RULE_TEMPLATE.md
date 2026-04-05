# 通用宿主最小规则模板

当仓库里没有当前宿主的现成 adapter 时，安装它的 AI 应立刻把下面这份模板改成适合自己宿主的持久规则，并落到自己真正会长期生效的位置。

可选载体包括：

- 宿主自带的长期 rule / instruction / guide
- 宿主 skill
- 项目级 guide
- 宿主 automation / watcher

优先使用当前宿主会自动加载的项目级 guide / rule；如果没有，再用宿主自己的全局持久规则载体。

安装阶段不要只说“后续我会记住这些”，而要真正写下去，并在写完后回读或等价验证一次。

如果需要 Windows 可直接照抄的 hook 接法样例，优先看 `docs/GENERIC_HOST_BOOTSTRAP.md`。

最小模板如下：

```text
你支持 Relay Hub。

固定记住：

1. agent_id = <当前宿主稳定名字>
2. main_session_ref 规则：
   - 优先复用宿主原生 conversation / thread / session id
   - 若宿主没有原生会话 id，就在该主对话第一次接入 Relay Hub 时生成稳定 ref
   - 同一主对话复用同一个 ref
   - 用户明确进入新主对话时才更换 ref
3. project_root 只能用于定位代码目录、开发日志和工作区，不能冒充 main_session_ref
4. 主窗口产品口令：
   - 接入 Relay Hub
   - Relay Hub 状态
   - 消息提醒状态
   - 开启<渠道>消息提醒
   - 关闭<渠道>消息提醒
   - 合流上下文
   - 退出 Relay Hub
5. branch 主链路：
   - claim-next -> branch-context -> reply -> resume-main
   - 如果宿主没有可靠的“主窗口用户发言前”触发机制，就不要假装自动合流；回到主窗口时明确先执行产品命令：合流上下文
6. 主窗口正常回复后的精确镜像：
   - 这必须是宿主环境里的自动触发机制，不允许每条回复靠人工补跑
   - 先检查宿主有没有原生 reply-end / stop hook；如果有，优先把 hook 接到：
     py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\relay_after_reply_hook.py" --agent <agent_id>
   - 若没有宿主专属正文捕获实现，但宿主持久规则能在正常回复流程里自动执行本地命令，就把最终正文原样写入文件
   - 再自动执行：
     py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\relay_after_reply_hook.py" --agent <agent_id> --body-file "<exact_body_file>"
   - 手动补跑一次只算补救，不算安装完成
7. 启用 Relay Hub 时的启动链路：
   - 先写 DEVELOPMENT_LOG.md 主线快照
   - 再执行一次带完整参数的 enable-relay --start-pickup
8. enable-relay 最小模板：
   py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent <agent_id> enable-relay --project-root "<project_root>" --snapshot-body "<snapshot_body>" --backend command --backend-command "<verified_backend_command_json>" --start-pickup
9. 不要先裸跑 enable-relay 探路；对通用宿主来说，`--project-root` 与 `--snapshot-body/--snapshot-file` 从一开始就是必填
10. `<verified_backend_command_json>` 必须替换成当前宿主自己的已验证非交互 CLI 调用，不能用 `echo`、`printf`、`true`、`false`、`sleep` 或带 `<...>` 占位符的假命令
11. 只有在用户真的说了“接入 Relay Hub”并且 pickup 已运行后，才报告 ready

安装阶段额外规则：

1. 现在就把这份规则落到持久载体里，不要停在口头说明
2. 写完后回读或等价验证，确认后续会持续生效
3. 现在就把“主窗口正常回复后的自动精确镜像机制”也落到持久载体里，并验证不是人工补跑
4. 安装汇报固定分成三段：
   - 共享安装状态
   - 当前宿主自举状态
   - 当前主对话 Relay 开启状态
5. 如果当前宿主没有可靠的主窗口前置 hook / pre-user 机制，安装汇报里要明确告诉用户：回主窗口后先说“合流上下文”，不要把自动合流写成已完成
```
