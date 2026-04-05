# Relay Hub Runbook

这份文件只关注 Windows 运维，不重复安装说明。

## 关键路径

- 仓库根：当前 `main-Windows` git 副本根目录
- Windows runtime：`%LOCALAPPDATA%\RelayHub\runtime`
- Windows 安装副本：`%LOCALAPPDATA%\RelayHub\app`
- Windows Web 托管：`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\RelayHub Web.cmd`
- OpenClaw 配置：`%USERPROFILE%\.openclaw\workspace\data\relay_hub_openclaw.json`
- OpenClaw bridge：`%USERPROFILE%\.openclaw\workspace\scripts\relay_openclaw_bridge.py`

如果 OpenClaw 使用自定义 workspace，就以 `install-openclaw` 输出里的 `config_path` 与 `bridge_script` 为准。

## 宿主侧常用命令

查看共享安装状态：

```powershell
py -3 install.py status
```

重装宿主 Web 托管并立即拉起：

```powershell
py -3 install.py install-service --load-services
```

卸载宿主 Web 托管：

```powershell
py -3 install.py uninstall-service
```

## OpenClaw 侧命令

这是一组**跨侧动作**，不要把它们当成宿主 Web 故障排查的默认步骤。

重装 OpenClaw 侧：

```powershell
py -3 install.py install-openclaw
```

手动跑一次发送泵：

```powershell
py -3 "%USERPROFILE%\.openclaw\workspace\scripts\relay_openclaw_bridge.py" --config "%USERPROFILE%\.openclaw\workspace\data\relay_hub_openclaw.json" --json pump-deliveries
```

## 日志位置

宿主 Web：

- `%LOCALAPPDATA%\RelayHub\runtime\logs\windows.web.out.log`
- `%LOCALAPPDATA%\RelayHub\runtime\logs\windows.web.err.log`

OpenClaw 相关日志：

- `%USERPROFILE%\.openclaw\workspace\log\relay_hub_web.log`

## 排障顺序

如果网页打不开：

1. 先看 `py -3 install.py status`
2. 看宿主 Web 托管是否已安装
3. 看 `%LOCALAPPDATA%\RelayHub\runtime\logs\windows.web.err.log`
4. 如果问题明显发生在 OpenClaw 侧，再看 `%USERPROFILE%\.openclaw\workspace\log\relay_hub_web.log`
5. 确认 `--web-base-url` 使用的是用户设备能访问的地址

如果 OpenClaw 说“已录入但对象尚未确认接单”：

1. 检查该对象是否真的已经按协议接入
2. 确认它是否已经把自己标成 `ready`
3. 用 `py -3 "%LOCALAPPDATA%\RelayHub\app\scripts\relayctl.py" show-session --session <session_key>` 看是否真的进入 `queued`

如果回包没发到目标渠道：

1. 看 `%USERPROFILE%\.openclaw\workspace\data\relay_hub_openclaw.json`
2. 看目标 `channel / target / accountId` 是否正确
3. 手动跑一次 `pump-deliveries`
4. 若返回 `RELAY_PUMP_IDLE` 或 `RELAY_PUMP_SENT`，说明 Relay Hub 到 OpenClaw 的发送泵仍在按当前配置工作
5. 若失败，再看 OpenClaw 渠道本身是否健康

## 变更原则

- 先改仓库版本，再通过安装器同步到 OpenClaw 工作区
- 不要手工在多个地方维护两份 bridge
- 优先改仓库里的 `scripts\relay_openclaw_bridge.py`
- 安装器负责把它同步进 OpenClaw 工作区
