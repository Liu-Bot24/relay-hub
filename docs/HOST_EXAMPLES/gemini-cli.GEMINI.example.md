# Relay Hub for Gemini CLI

把这份内容视为 `GEMINI.md` 或 Gemini skill 示例。它不是产品定义。

当前宿主：`Gemini CLI`

固定记住：

1. `agent_id = gemini-cli`
2. `main_session_ref`
   - 优先复用 Gemini 当前主会话标识
   - 如果当前版本未暴露原生会话 id，就在第一次接入 Relay Hub 时生成稳定 ref，并在当前主对话复用
3. 主窗口产品口令：
   - `接入 Relay Hub`
   - `Relay Hub 状态`
   - `消息提醒状态`
   - `开启<渠道>消息提醒`
   - `关闭<渠道>消息提醒`
   - `合流上下文`
   - `退出 Relay Hub`

backend 规则：

- 只有当 `gemini` 的当前 Windows CLI 形态已经本地验证可工作时，才允许把它写进 `--backend-command`
- 不要把“可能支持 hooks / skills / 非交互模式”写成已验证完成

主窗口自动精确镜像：

- 如果当前 Gemini 版本的 hook 配置已经真实验证能在回复结束时拿到最终正文，优先把 hook 接到 `relay_after_reply_hook.py`
- 否则，只有在 `GEMINI.md` 或 Gemini skill 确实能在正常回复流程里自动执行本地命令时，才允许退回回复收尾流程：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\relay_after_reply_hook.py" --agent gemini-cli --body-file "<exact_body_file>"
```

`enable-relay` 主模板：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent gemini-cli enable-relay --project-root "<project_root>" --snapshot-body "<snapshot_body>" --backend command --backend-command "<verified_backend_command_json>" --start-pickup
```

最低验收：

- 不能把“Gemini 也许支持 hook / skill”直接等同于“自动镜像已完成”
- 只有当前版本的 hook、规则或 skill 已经真实持久化，并且后续无需用户提醒时，才算安装阶段完成
