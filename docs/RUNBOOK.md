# Relay Hub Runbook

这份文件只关注运维，不重复安装说明。

## 关键路径

- 仓库根：`/path/to/relay-hub`
- runtime：`~/Library/Application Support/RelayHub/runtime`
- 安装副本：`~/Library/Application Support/RelayHub/app`
- OpenClaw 配置：`~/.openclaw/workspace/data/relay_hub_openclaw.json`
- OpenClaw 桥接脚本：`~/.openclaw/workspace/scripts/relay_openclaw_bridge.py`

## launchd 服务名

- Web: `com.relayhub.web`
- Worker: `com.relayhub.worker.<agent>`

例如 Claude：

- `com.relayhub.worker.claude-code`

## 常用命令

查看安装状态：

```bash
cd /path/to/relay-hub
python3 install.py status
```

重装 OpenClaw 侧：

```bash
cd /path/to/relay-hub
python3 install.py install-openclaw
```

重装服务：

```bash
cd /path/to/relay-hub
python3 install.py install-launchd --worker-agent <agent_id> --worker-backend manual --load-services
```

## 手动管理 launchd

重启 Web：

```bash
launchctl kickstart -k gui/$(id -u)/com.relayhub.web
```

重启某个 Worker：

```bash
launchctl kickstart -k gui/$(id -u)/com.relayhub.worker.<agent>
```

卸载服务：

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.relayhub.web.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.relayhub.worker.<agent>.plist
```

## 日志位置

Web：

- `runtime/logs/launchd.web.out.log`
- `runtime/logs/launchd.web.err.log`

Worker：

- `runtime/logs/launchd.worker.<agent>.out.log`
- `runtime/logs/launchd.worker.<agent>.err.log`

OpenClaw 网页启动日志：

- `~/.openclaw/workspace/log/relay_hub_web.log`

## 排障顺序

如果网页打不开：

1. `python3 install.py status`
2. 看 `com.relayhub.web` 是否已安装
3. 看 `runtime/logs/launchd.web.err.log`
4. 看 `~/.openclaw/workspace/log/relay_hub_web.log`
5. 确认 `--web-base-url` 使用的是用户设备能访问的地址

如果 OpenClaw 说“已录入但对象尚未确认接单”：

1. 看对应 worker 是否在跑
2. 看 `runtime/logs/launchd.worker.<agent>.err.log`
3. 检查该对象本身是否已登录、可调用
4. 用 `python3 scripts/relayctl.py show-session --session <session_key>` 看是否真的进入 `queued`

如果回包没发到目标渠道：

1. 看 `~/.openclaw/workspace/data/relay_hub_openclaw.json`
2. 看目标 channel / target / accountId 是否正确
3. 手动跑一次：

```bash
cd /path/to/relay-hub
python3 scripts/relay_openclaw_bridge.py --config ~/.openclaw/workspace/data/relay_hub_openclaw.json --json pump-deliveries
```

4. 若返回 `RELAY_PUMP_SENT`，说明 Relay Hub 到 OpenClaw 的发送泵正常
5. 若失败，再看 OpenClaw 渠道本身是否健康

## 变更原则

- 先改仓库版本，再通过安装器同步到 OpenClaw 工作区
- 不要手工在多个地方维护两份桥接脚本
- 优先改仓库里的 `scripts/relay_openclaw_bridge.py`
- 安装器负责把它装进 `~/.openclaw/workspace/scripts/`
