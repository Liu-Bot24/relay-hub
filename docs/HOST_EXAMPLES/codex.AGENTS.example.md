# Relay Hub for Codex

把这份内容视为 `AGENTS.md` 示例。

当前宿主：`Codex`

固定记住：

1. `agent_id = codex`
2. `main_session_ref`
   - 优先复用 Codex 当前主线程 / 当前对话标识
   - 同一主对话复用同一个 ref
3. 主窗口产品口令：
   - `接入 Relay Hub`
   - `Relay Hub 状态`
   - `消息提醒状态`
   - `开启<渠道>消息提醒`
   - `关闭<渠道>消息提醒`
   - `合流上下文`
   - `退出 Relay Hub`
4. 当处于 Relay Hub 已接入状态时，正常主窗口回复前先执行：

```bash
python3 <app_root>/scripts/agent_relay.py --agent codex prepare-main-reply
```

5. 建议的 `command` backend：

```json
["bash","-lc","codex exec --skip-git-repo-check --sandbox workspace-write -o \"$RELAY_OUTPUT_FILE\" -"]
```

如果需要显式绑定项目根目录，可改成：

```json
["bash","-lc","codex exec --skip-git-repo-check --sandbox workspace-write --cd \"<project_root>\" -o \"$RELAY_OUTPUT_FILE\" -"]
```

6. 主窗口自动精确镜像：
   - 优先沿用 Codex 当前仓库里的 Relay Hub 主窗口规则
   - 如果当前实现拿不到代码级最终正文，就在回复收尾阶段自动执行：
     1. 把即将发给用户的最终正文原样写入 `<exact_body_file>`
     2. 运行：

```bash
python3 <app_root>/scripts/relay_after_reply_hook.py --agent codex --body-file <exact_body_file>
```

   - 然后把同一份 `<exact_body_file>` 的内容作为最终回复发给用户
   - 不允许先镜像 A 文本、再向用户发送 B 文本

7. `enable-relay` 默认模板：

```bash
python3 <app_root>/scripts/agent_relay.py --agent codex enable-relay \
  --project-root <project_root> \
  --development-log-path <development_log_path> \
  --main-session-ref <main_session_ref> \
  --snapshot-body "<snapshot_body>" \
  --backend command \
  --backend-command '<json_string_array>' \
  --start-pickup
```

最低验收：

- `command` backend 不能留空，也不能写成“后面再确定”
- 正常主窗口回复时，镜像必须自动发生，不能靠用户提醒
