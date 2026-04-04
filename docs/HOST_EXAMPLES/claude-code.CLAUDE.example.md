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
   - 如果当前 Claude 版本暴露了可用的 `Stop` hook / 生命周期 hook，并且 payload 足以拿到最终正文，就优先接到 `relay_after_reply_hook.py`
   - 如果当前版本没有可直接用的原生 hook，也不能因此判定安装失败；改走宿主持久规则里的“回复收尾流程”：
     1. 在真正发给用户之前，先把最终正文原样写入 `<exact_body_file>`
     2. 自动执行：

```bash
python3 <app_root>/scripts/relay_after_reply_hook.py --agent claude-code --body-file <exact_body_file>
```

     3. 然后把同一份 `<exact_body_file>` 的内容作为最终回复发给用户

6. 这不算“手动补跑”，前提是：
   - 用户不需要每次再提醒
   - 这条流程已经写进 `CLAUDE.md` 或等价长期载体
   - 每条正常主窗口回复都会自动遵守

7. `enable-relay` 默认模板：

```bash
python3 <app_root>/scripts/agent_relay.py --agent claude-code enable-relay \
  --project-root <project_root> \
  --development-log-path <development_log_path> \
  --main-session-ref <main_session_ref> \
  --snapshot-body "<snapshot_body>" \
  --backend command \
  --backend-command '<json_string_array>' \
  --start-pickup
```

最低验收：

- 不能再写“Claude Code 没有原生 after-reply hook，所以只能部分完成”
- 只要回复收尾流程已经被持久规则自动接住，就算自动镜像已完成
