# Relay Hub for Claude Code

把这份内容视为 `CLAUDE.md` 示例。

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
4. 建议的 `command` backend：

```json
["claude","-p","--output-format","text","--no-session-persistence"]
```

如果当前场景要求绑定已有 Claude session，也可以改成当前版本支持的可工作 `--resume` / `--session-id` 形式，但不能写成占位待定。

5. 主窗口自动精确镜像：
   - Claude Code 当前主路径优先使用 `Stop` hook，不要先假设“没有 after-reply hook”
   - 可直接写入 `~/.claude/settings.json` 的最小示例如下：

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"<app_root>/scripts/relay_after_reply_hook.py\" --agent claude-code"
          }
        ]
      }
    ]
  }
}
```

   - `relay_after_reply_hook.py` 现在会直接读取 Claude `Stop` payload 里的 `transcript_path`，并提取最后一条 assistant 正文排入镜像队列
   - 如果当前环境下确实无法落 `Stop` hook，再退回宿主持久规则里的“回复收尾流程”：
     1. 在真正发给用户之前，先把最终正文原样写入 `<exact_body_file>`
     2. 自动执行：

```bash
python3 "<app_root>/scripts/relay_after_reply_hook.py" --agent claude-code --body-file <exact_body_file>
```

     3. 然后把同一份 `<exact_body_file>` 的内容作为最终回复发给用户

6. 这不算“手动补跑”，前提是：
   - 用户不需要每次再提醒
   - `Stop` hook 或回复收尾流程已经写进 Claude 的持久载体
   - 每条正常主窗口回复都会自动遵守

7. `enable-relay` 默认模板：

```bash
python3 "<app_root>/scripts/agent_relay.py" --agent claude-code enable-relay \
  --project-root <project_root> \
  --development-log-path <development_log_path> \
  --main-session-ref <main_session_ref> \
  --snapshot-body "<snapshot_body>" \
  --backend command \
  --backend-command '<json_string_array>' \
  --start-pickup
```

8. branch 合流规则：
   - 通用主路径默认仍然使用产品命令 `合流上下文`
   - 只有在当前 Claude 环境里，确实已经落下了可靠的“主窗口用户发言前”触发机制，并且该机制会先执行合流，再继续当前回答时，才允许把自动合流报告为已完成
   - 如果没有这类可靠前置机制，就必须明确告诉用户：回到主窗口后先说 `合流上下文`，再继续主线

最低验收：

- 不能再写“Claude Code 没有原生 after-reply hook，所以只能部分完成”
- 如果 `Stop` hook 已写入 `~/.claude/settings.json` 并回读验证，就应优先判定为已完成
- 只有当前环境确实不能落 `Stop` hook 时，才退回 `CLAUDE.md` 里的回复收尾流程
- 如果没有可靠的前置 hook / pre-prompt 机制，就不要把自动合流写成已完成
