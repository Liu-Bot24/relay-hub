# Relay Hub Runbook

这份文件只关注运维，不重复安装说明。

## 关键路径

- 仓库根：`/path/to/relay-hub`
- OpenClaw 配置：`~/.openclaw/workspace/data/relay_hub_openclaw.json`
- OpenClaw 桥接脚本：`~/.openclaw/workspace/scripts/relay_openclaw_bridge.py`

宿主侧默认路径：

- Windows runtime：`%LOCALAPPDATA%\RelayHub\runtime`
- Windows 安装副本：`%LOCALAPPDATA%\RelayHub\app`
- Windows Web 托管：`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\RelayHub Web.cmd`

## 宿主 Web 托管

- Windows：用户级 `Startup` 自启动入口 `RelayHub Web.cmd`

## 常用命令

查看安装状态：

```bash
cd /path/to/relay-hub
py -3 install.py status
```

重装 OpenClaw 侧：

```bash
cd /path/to/relay-hub
py -3 install.py install-openclaw
```

重装宿主 Web 托管并立即拉起：

```bash
cd /path/to/relay-hub
py -3 install.py install-service --load-services
```

卸载宿主 Web 托管：

```bash
cd /path/to/relay-hub
py -3 install.py uninstall-service
```

## 手动管理

Windows 如需重新写入 Startup 入口并立即拉起，优先直接重跑：

```bash
cd /path/to/relay-hub
py -3 install.py install-service --load-services
```

## 日志位置

宿主 Web：

- Windows：`runtime/logs/windows.web.out.log`
- Windows：`runtime/logs/windows.web.err.log`

OpenClaw 网页启动日志：

- `~/.openclaw/workspace/log/relay_hub_web.log`

## 排障顺序

如果网页打不开：

1. `py -3 install.py status`
2. 看当前平台的宿主 Web 托管是否已安装
3. 看当前平台对应的 `runtime/logs/*.err.log`
4. 看 `~/.openclaw/workspace/log/relay_hub_web.log`
5. 确认 `--web-base-url` 使用的是用户设备能访问的地址

如果 OpenClaw 说“已录入但对象尚未确认接单”：

1. 检查该对象是否真的已经按协议接入
2. 确认它是否已经把自己标成 `ready`
3. 用 `py -3 scripts/relayctl.py show-session --session <session_key>` 看是否真的进入 `queued`

如果回包没发到目标渠道：

1. 看 `~/.openclaw/workspace/data/relay_hub_openclaw.json`
2. 看目标 channel / target / accountId 是否正确
3. 手动跑一次：

```bash
cd /path/to/relay-hub
py -3 scripts/relay_openclaw_bridge.py --config ~/.openclaw/workspace/data/relay_hub_openclaw.json --json pump-deliveries
```

4. 若返回 `RELAY_PUMP_SENT`，说明 Relay Hub 到 OpenClaw 的发送泵正常
5. 若失败，再看 OpenClaw 渠道本身是否健康

## 变更原则

- 先改仓库版本，再通过安装器同步到 OpenClaw 工作区
- 不要手工在多个地方维护两份桥接脚本
- 优先改仓库里的 `scripts/relay_openclaw_bridge.py`
- 安装器负责把它装进 `~/.openclaw/workspace/scripts/`

