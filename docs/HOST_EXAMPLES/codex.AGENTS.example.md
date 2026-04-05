# Relay Hub for Codex

把这份内容视为 Codex 的 `AGENTS.md` 示例。它只在**你已经明确启用 Codex 宿主增强**时使用；如果当前仍走通用宿主路径，优先看 `docs/GENERIC_HOST_BOOTSTRAP.md`。

当前宿主：`Codex`

固定记住：

1. `agent_id = codex`
2. `main_session_ref`
   - 同一主对话复用同一个 ref
   - 用户明确进入新主对话时，换新的 ref
3. 主窗口产品口令：
   - `接入 Relay Hub`
   - `Relay Hub 状态`
   - `消息提醒状态`
   - `开启<渠道>消息提醒`
   - `关闭<渠道>消息提醒`
   - `合流上下文`
   - `退出 Relay Hub`

主窗口回复前的准备动作：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent codex prepare-main-reply
```

backend 选择：

- Windows 下不要把 `codex` 直接写成 `command` backend 的 JSON 数组
- 优先使用已经启用并验证可工作的 Codex 宿主增强
- 如果当前 Windows 环境还没验证过 `codex exec` 能被后台子进程正常启动，就不要把 pickup 报告为已完成

主窗口自动精确镜像：

- 优先沿用 Codex 已安装的主窗口规则
- 如果当前实现拿不到代码级最终正文，就在回复收尾阶段自动执行：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\relay_after_reply_hook.py" --agent codex --body-file "<exact_body_file>"
```

然后把同一份 `<exact_body_file>` 的内容作为最终回复发给用户；不允许先镜像 A 文本、再向用户发送 B 文本。

仅在 Codex 宿主增强已经启用时，`enable-relay` 主模板是：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent codex enable-relay --project-root "<project_root>" --start-pickup
```

最低验收：

- 不要把 `["codex", ...]` 直接当成 Windows 下的 `command` backend 示例
- 正常主窗口回复时，镜像必须自动发生，不能靠用户提醒
