# Relay Hub Agent Workflow

这份文件给外部 AI 一个可直接执行的运行期工作流。

## 0. 先认清当前分支口径

- `main-Windows` 只提供 Windows 安装主路径
- 下面所有命令都按 Windows / PowerShell 写
- `installed_app_root` 默认是 `%LOCALAPPDATA%\RelayHub\app`
- 如果安装时使用了自定义根目录，就以 `py -3 install.py status` 里的 `app_root` 为准

## 1. 在当前主对话里开启 Relay Hub

用户说 `接入 Relay Hub` 时，通用主路径统一按下面顺序：

1. 确定当前项目根目录
2. 复用或创建当前项目的 `DEVELOPMENT_LOG.md`
3. 写入一条主线快照
4. 以完整参数执行**一次** `enable-relay --start-pickup`
5. pickup 真正运行后，才把自己视为 `ready`

标准命令：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent <agent_id> enable-relay --project-root "<project_root>" --snapshot-body "<snapshot_body>" --backend command --backend-command "<verified_backend_command_json>" --start-pickup
```

硬规则：

- 不要先裸跑 `enable-relay`
- 不要再在后面单独补跑一遍 `start-pickup`
- backend 命令没有验证前，不要把自己写成已完成接入

## 2. 查询当前接入状态

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent <agent_id> agent-status
```

重点看：

- 是否 `ready`
- pickup 是否在运行
- 是否有 `queued / processing / awaiting_user / entry_open`

## 3. OpenClaw 先开入口时，第一次怎么接单

如果入口是 OpenClaw 先开的，那么它一开始通常只有：

- 渠道对象绑定
- 网页入口

它通常还没有：

- `main_session_ref`
- 主线快照
- 项目开发日志绑定

所以第一次正式接单时，必须补齐这些信息：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent <agent_id> claim-next --main-session-ref "<main_session_ref>" --main-context-body "<main_context_body>"
```

如果你已经先做过 `enable-relay`，这个命令会自动复用你当前项目根目录和开发日志路径。

## 4. 读取 branch 上下文

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent <agent_id> branch-context --session "<session_key>" --main-session-ref "<main_session_ref>"
```

返回内容里重点看：

- `main_context`
- `development_log`
- `branch_messages`

## 5. 写回进度或最终结果

进度：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent <agent_id> reply --session "<session_key>" --kind progress --body "正在处理。"
```

最终结果：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent <agent_id> reply --session "<session_key>" --kind final --body "这是最终回复。"
```

这些消息不会直接发给用户；它们会进入待发送队列，再由 OpenClaw 的发送泵发到真实消息渠道。

## 6. 主窗口正常回复后的精确镜像

优先顺序：

1. 当前宿主原生提供的 reply-end / stop / lifecycle hook
2. 宿主持久规则里的回复收尾流程
3. 宿主原生 automation / watcher

如果宿主能把 hook payload 传给本地命令，优先接：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\relay_after_reply_hook.py" --agent <agent_id>
```

如果宿主拿不到原始 payload，但能在回复收尾阶段自动执行本地命令，就走保底路径：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\relay_after_reply_hook.py" --agent <agent_id> --body-file "<exact_body_file>"
```

硬规则：

- 写入文件的正文必须和最终真正发给用户的正文完全一致
- 不要先镜像 A 文本，再向用户发送 B 文本
- “出问题时手动补跑一次”不算安装完成

## 7. merge-back 默认标准

通用默认是：

- 用户回到主窗口后，先显式说 `合流上下文`
- 宿主收到后，再执行：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent <agent_id> resume-main --main-session-ref "<main_session_ref>"
```

只有当前宿主已经真实落下可靠的前置 hook / pre-user 机制时，才允许自动做同样动作。

## 8. 退出 Relay Hub

当用户说 `退出 Relay Hub` 时：

```powershell
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent <agent_id> stop-pickup --main-session-ref "<main_session_ref>"
py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\agent_relay.py" --agent <agent_id> disable-relay
```

## 9. 边界

- OpenClaw 不负责主线快照和 merge-back
- branch 不是第二条主聊天
- `project_root` 只用于定位代码目录、开发日志和工作区；不要拿它去猜测未来主会话
- 同一时间只保留一个活跃主会话；回旧会话续旧会话，去新会话则为新会话建立新的 `main_session_ref`
