# Relay Hub for Gemini CLI

把这份内容视为 `GEMINI.md` 或 Gemini skill 示例。

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
4. Gemini CLI 本机已支持：
   - 非交互模式：`gemini --prompt ... --output-format text`
   - hooks 能力：`gemini hooks ...`
   - skills 能力：`gemini skills ...`

5. 建议的 `command` backend：

```json
["bash","-lc","tmp=$(mktemp); cat > \"$tmp\"; gemini --prompt \"$(cat \"$tmp\")\" --output-format text; rc=$?; rm -f \"$tmp\"; exit $rc"]
```

这条命令的实际 worker 仍然是 `gemini`，只是用一层最薄的 shell 包装把 stdin prompt 交给它。

6. 主窗口自动精确镜像：
   - 如果当前 Gemini hooks 配置能在回复结束时直接拿到最终正文，优先把 hook 接到 `relay_after_reply_hook.py`
   - 否则在 `GEMINI.md` 或 Gemini skill 里持久写入“回复收尾流程”：
     1. 把即将发给用户的最终正文原样写入 `<exact_body_file>`
     2. 自动执行：

```bash
python3 "<app_root>/scripts/relay_after_reply_hook.py" --agent gemini-cli --body-file <exact_body_file>
```

     3. 最后发送同一份 `<exact_body_file>` 的内容

7. `enable-relay` 默认模板：

```bash
python3 "<app_root>/scripts/agent_relay.py" --agent gemini-cli enable-relay \
  --project-root <project_root> \
  --development-log-path <development_log_path> \
  --main-session-ref <main_session_ref> \
  --snapshot-body "<snapshot_body>" \
  --backend command \
  --backend-command '<json_string_array>' \
  --start-pickup
```

最低验收：

- 不能把“Gemini 没配置 hook”直接等同于“自动镜像无法完成”
- 只要 `GEMINI.md` / skill 已经持久化了回复收尾流程，并且后续无需用户提醒，就算安装阶段完成
