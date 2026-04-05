# OpenClaw Integration Mapping

这份文件只定义一件事：

OpenClaw 如果要接 Relay Hub，应该调用哪些**已安装 bridge** 命令。

## 0. 只认安装后的 bridge

OpenClaw 运行期只调用安装后 bridge，不调用仓库里的旧脚本。

默认安装路径：

- bridge：`%USERPROFILE%\.openclaw\workspace\scripts\relay_openclaw_bridge.py`
- config：`%USERPROFILE%\.openclaw\workspace\data\relay_hub_openclaw.json`

如果安装时使用了自定义 OpenClaw workspace，就以 `install-openclaw` 输出里的 `bridge_script` 和 `config_path` 为准。

当前 bridge 的实际命令只有这些：

- `open-entry`
- `dispatch-input`
- `session-status`
- `pump-deliveries`
- `notify`
- `relay-help`

## 1. 打开入口

当用户显式要求重发入口，或要求在已有 branch 上重新做“复用 / 新建”选择时，调用：

```powershell
py -3 "%USERPROFILE%\.openclaw\workspace\scripts\relay_openclaw_bridge.py" --json open-entry --agent <agent_id> --channel <channel> --target <target>
```

如果用户明确要求复用或新建，则带：

- `--branch-mode reuse`
- `--branch-mode new`

硬规则：

- `<channel>` 和 `<target>` 默认从当前入站消息上下文直接取
- 只有真的拿不到时才回问用户
- 如果当前渠道对象已经有 branch，而这次调用没有显式指定“复用”或“新建”，bridge 会返回追问；OpenClaw 必须主动把这个问题问给用户，不能替用户决定
- 发出去的是网页入口，不是“branch 已经开始处理”的信号

## 2. 已录入

当用户说 `已录入` 时，调用：

```powershell
py -3 "%USERPROFILE%\.openclaw\workspace\scripts\relay_openclaw_bridge.py" --json dispatch-input --channel <channel> --target <target> --wait-claim
```

如果返回 `claim_wait.claimed = false`，就把 bridge 返回的 `user_message` 原样发给用户。

## 3. 查询状态

当用户说 `状态` 时，调用：

```powershell
py -3 "%USERPROFILE%\.openclaw\workspace\scripts\relay_openclaw_bridge.py" --json session-status --channel <channel> --target <target>
```

然后把返回里的 `user_message` 发给用户即可。

## 4. 发送待回包消息

当有待发送回包时，调用：

```powershell
py -3 "%USERPROFILE%\.openclaw\workspace\scripts\relay_openclaw_bridge.py" --json pump-deliveries
```

如果你只想处理某一个渠道对象，也可以加：

- `--channel <channel>`
- `--target <target>`

重要：

- `pump-deliveries` 已经负责发送并推进递送状态
- OpenClaw 不需要自己再补一套手工“拉取待发消息 / 确认已发送”流程

## 5. 返回固定命令大全

当用户说 `relay help` 时，调用：

```powershell
py -3 "%USERPROFILE%\.openclaw\workspace\scripts\relay_openclaw_bridge.py" --json relay-help --agent <agent_id>
```

## 6. 最小原则

- OpenClaw 只调用已安装 bridge，不自己翻 `routes.json`、`state.json`、`messages/*.md`
- OpenClaw 不是主记忆体；`main_context` 与 merge-back 不由它负责
- 网页入口发出去时只是“入口已打开”；用户第一次在网页里保存消息时，branch 才正式开始
