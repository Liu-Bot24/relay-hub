# Relay Hub for Claude Code

把这份内容视为 Claude Code 的示例规则。它不是产品定义，也不是唯一允许的载体路径。

当前宿主：`Claude Code`

固定记住：

1. `agent_id = claude-code`
2. `main_session_ref`
   - 优先复用 Claude 当前主对话的稳定 session / conversation 标识
   - 若当前版本拿不到原生标识，就在第一次接入时生成稳定 ref，并在该主对话持续复用
3. 主窗口产品口令：
   - `接入 Relay Hub`
   - `Relay Hub 状态`
   - `消息提醒状态`
   - `开启<渠道>消息提醒`
   - `关闭<渠道>消息提醒`
   - `合流上下文`
   - `退出 Relay Hub`

持久规则载体：

- 常见全局载体是 `%USERPROFILE%\CLAUDE.md`
- 常见 hook 设置文件是 `%USERPROFILE%\.claude\settings.json`
- 这只是常见示例；当前 Claude 版本实际长期生效的载体才算完成

建议的 `command` backend：

- 使用一个已经在当前 Windows 环境验证可工作的 Claude CLI 命令
- 如果 backend 还没验证，不要把宿主自举写成已完成

主窗口自动精确镜像：

- 如果当前 Claude 版本的 `Stop` hook 真的可用，并且 payload 已验证能拿到最终正文，就优先把它接到 `relay_after_reply_hook.py`
- 最小命令形态：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "py -3 \"%LOCALAPPDATA%\\RelayHub\\app\\scripts\\relay_after_reply_hook.py\" --agent claude-code"
          }
        ]
      }
    ]
  }
}
```

- 如果当前版本没有已验证可用的 `Stop` hook，但 Claude 的持久规则确实能在正常回复流程里自动执行本地命令，再退回“回复收尾流程”：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\relay_after_reply_hook.py" --agent claude-code --body-file "<exact_body_file>"
```

这两条都只有在真实自动触发、且后续每条主窗口正常回复都会自动发生时，才算完成。

`enable-relay` 主模板：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent claude-code enable-relay --project-root "<project_root>" --snapshot-body "<snapshot_body>" --backend command --backend-command "<verified_backend_command_json>" --start-pickup
```

branch 合流规则：

- 通用默认仍然使用产品命令 `合流上下文`
- 只有当前 Claude 环境里确实已经落下可靠的主窗口前置机制时，才允许把自动合流报告为已完成

最低验收：

- 你实际选定的持久载体必须真实存在并可回读
- 你实际选定的 hook / automation / 回复收尾流程必须真实存在并可回读
- backend 命令必须已经验证可工作
- 如果没有可靠的前置 hook / pre-user 机制，就不要把自动合流写成已完成
