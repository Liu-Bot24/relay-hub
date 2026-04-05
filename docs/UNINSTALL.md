# 卸载说明

Relay Hub 的卸载和安装一样，按侧分开执行。

默认规则：

- AI 宿主侧使用 `uninstall-host`
- OpenClaw 侧使用 `uninstall-openclaw`
- 只有在你明确要整机一起清理时，才使用组合 `uninstall`

## 1. 卸载宿主侧共享层

```bash
cd /path/to/relay-hub
python3 install.py uninstall-host
```

这会移除：

- 共享 runtime
- 安装副本 app
- 当前平台的宿主 Web 托管定义

默认路径下通常包括：

- macOS：`~/Library/Application Support/RelayHub/runtime`
- macOS：`~/Library/Application Support/RelayHub/app`
- macOS：`~/Library/LaunchAgents/com.relayhub.web.plist`
- Windows：`%LOCALAPPDATA%\RelayHub\runtime`
- Windows：`%LOCALAPPDATA%\RelayHub\app`
- Windows：`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\RelayHub Web.cmd`

这不会移除：

- OpenClaw 工作区里的 bridge / skill / config
- 其他 AI 宿主自己的长期规则

如果还想顺手移除 Codex 侧由 Relay Hub 安装过的 skill / AGENTS block，可额外加：

```bash
python3 install.py uninstall-host --uninstall-codex-host
```

## 2. 卸载 OpenClaw 侧

```bash
cd /path/to/relay-hub
python3 install.py uninstall-openclaw
```

这会移除 OpenClaw 工作区里由 Relay Hub 写入的这些产物：

- `scripts/relay_openclaw_bridge.py`
- `data/relay_hub_openclaw.json`
- `data/relay_hub_channel_aliases.json`
- `skills/relay-hub-openclaw/`
- `HEARTBEAT.md` 中的 Relay Hub block
- Relay Hub 写入的 pid / log 文件

这不会移除：

- 共享 runtime / app / 宿主 Web 托管
- OpenClaw 里的其他非 Relay Hub 内容

## 3. 只卸载宿主 Web 托管

```bash
cd /path/to/relay-hub
python3 install.py uninstall-service
```

适合只想停掉并删除当前平台宿主 Web 托管定义的场景。
macOS 仍兼容旧别名 `python3 install.py uninstall-launchd`。

## 4. 组合卸载

```bash
cd /path/to/relay-hub
python3 install.py uninstall
```

这是 operator-only 组合卸载，会：

- 先清 OpenClaw 侧 bridge / config / heartbeat block
- 再清宿主侧共享 runtime / app / 宿主 Web 托管

默认不会删除：

- Claude / Gemini / Cursor 等宿主自己落下的长期规则
- 用户项目代码
- OpenClaw 或其他宿主的无关内容

## 5. 边界

- 卸载命令只清理 Relay Hub 自己管理的产物
- 不会擅自删掉别的 AI 宿主私有配置
- 如果某个宿主的长期规则不是 `install.py` 写入的，而是宿主自己在安装阶段落下的，那部分仍应由该宿主自己移除
