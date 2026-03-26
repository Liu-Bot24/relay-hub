# Relay Hub 安装章程

这份文件回答 3 件事：

1. 仓库下载后，应该先执行什么安装命令
2. 应该跟 `Claude Code` 说什么
3. 应该跟 `OpenClaw` 说什么

这不是协议文档；协议本体仍然是仓库根的 `RELAY_PROTOCOL.md`。

## 1. 人类先做的事

先把仓库放到本机，然后执行一次自检：

```bash
cd /path/to/relay-hub
python3 install.py doctor \
  --web-base-url http://YOUR_LAN_IP:4317 \
  --delivery-channel feishu=ou_xxx \
  --worker-backend claude-code
```

如果你不用飞书，`feishu=ou_xxx` 只是示例；把它换成任何 `OpenClaw` 能发消息的渠道即可。

通过后，再执行完整安装：

```bash
cd /path/to/relay-hub
python3 install.py full \
  --web-base-url http://YOUR_LAN_IP:4317 \
  --delivery-channel feishu=ou_xxx \
  --delivery-channel openclaw-weixin=xxx@im.wechat \
  --delivery-account openclaw-weixin=your-account-id \
  --worker-agent claude-code \
  --worker-backend claude-code \
  --load-services
```

如果你只想先装 OpenClaw 侧：

```bash
cd /path/to/relay-hub
python3 install.py install-openclaw \
  --web-base-url http://YOUR_LAN_IP:4317 \
  --delivery-channel feishu=ou_xxx
```

## 2. 应该跟 Claude Code 说什么

下面这段可以直接发给 `Claude Code`：

```text
这是一个 Relay Hub 仓库。请先阅读：

1. README.md
2. RELAY_PROTOCOL.md
3. docs/AGENT_ENTRY_RULE.md
4. docs/AGENT_WORKFLOW.md
5. docs/COMPATIBILITY.md

你的 agent_id 是 claude-code。

要求：
- 不要直接读取原始消息渠道或 OpenClaw 插件内部实现。
- 只通过 scripts/agent_relay.py、scripts/relayctl.py 和仓库文档工作。
- 当前 AI 对话窗口是主线，网页 / md 是 branch。
- 如果用户要求你参与 Relay Hub，就先按文档确认环境，再通过 agent_relay.py 接入。
- 如果仓库尚未安装完成，先按 README 和 docs/INSTALL_PLAYBOOK.md 执行安装。
- 安装完成后，只汇报是否进入“可用状态”，不要自行替用户做完整业务测试，除非用户明确要求。
```

如果不是 `Claude Code`，只需要把其中一句：

```text
你的 agent_id 是 claude-code。
```

换成：

```text
你的 agent_id 是 <你的对象名>。
```

例如：

- `codex`
- `gemini-cli`
- `cursor-cli`
- `opencode`

## 3. 应该跟 OpenClaw 说什么

下面这段可以直接发给 `OpenClaw`：

```text
这是一个 Relay Hub 接入仓库。请先阅读：

1. README.md
2. docs/OPENCLAW_RULE.md
3. docs/OPENCLAW_INTEGRATION.md
4. docs/COMPATIBILITY.md

你的职责只有：
- 打开 <agent> 入口
- 处理“已录入”
- 查询“状态”
- 退出 relay
- 发送 pull-deliveries 里的待回包消息

要求：
- 不要直接读取 routes.json、state.json、messages/*.md。
- 只通过 scripts/openclaw_relay.py 或安装后写入 ~/.openclaw/workspace/scripts/relay_openclaw_bridge.py 的桥接脚本工作。
- OpenClaw 只是渠道网关，不是主记忆体。
- main_context 和 merge-back 不由你负责。
- 如果用户要求接入 Relay Hub，而本机尚未安装完成，就先按 README 和 docs/INSTALL_PLAYBOOK.md 完成 install.py install-openclaw 或 install.py full。
```

## 4. 成功标准

当下面几件事都成立时，就可以认为仓库已经安装到“可用状态”：

1. `python3 install.py doctor ...` 返回 `"ok": true`
2. `python3 install.py status` 能看到 OpenClaw 桥接文件和 launchd 服务
3. `OpenClaw` 能响应：
   - `打开 claude 入口`
   - `已录入`
   - `状态`
   - `退出`
4. 本地网页入口能打开 branch 页面
5. `Claude Code` worker 能 claim 队列并把 final 回包重新发回 OpenClaw 渠道

## 5. 不要做什么

- 不要让外部 AI 直接读原始消息渠道
- 不要让 OpenClaw 自己翻 Relay Hub 的底层文件
- 不要把网页 branch 当成第二条主聊天
- 不要假设本仓库已经对所有 AI CLI 都内置了现成后台 worker

更详细的通用性边界，见 `docs/COMPATIBILITY.md`。
