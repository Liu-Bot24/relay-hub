# Relay Hub 安装章程

这份文件只讲安装，不讲协议细节。

它回答 3 件事：

1. 仓库下载后，应该先执行什么安装命令
2. 应该跟 AI 编程工具说什么
3. 应该跟 `OpenClaw` 说什么

协议本体仍然是仓库根的 `RELAY_PROTOCOL.md`。

## 1. 人类先做的事

先把仓库放到本机。仓库路径就是这个包本身的路径。

建议先执行一次自检：

```bash
cd /path/to/relay-hub
python3 install.py doctor
```

说明：

- `web_base_url` 默认会由安装器自动探测局域网 IPv4 后生成，只有探测失败时才回落到 `127.0.0.1`

通过后，再执行完整安装：

```bash
cd /path/to/relay-hub
python3 install.py full --load-services
```

这表示：

- Relay Hub 本身会先装好
- OpenClaw 桥接和网页入口会一起装好
- 默认回包走原始触发渠道，不要求先配置额外渠道
- 如果机器上已经配过额外回传渠道，重装时不显式传参也会保留原配置
- 外部对象后续再按 `docs/AGENT_ENTRY_RULE.md` 和 `docs/AGENT_WORKFLOW.md` 接入

如果你后面明确要“除原始触发渠道外，还要额外镜像到别的渠道”，再单独执行：

```bash
cd /path/to/relay-hub
python3 install.py install-openclaw \
  --delivery-channel some-channel=target_id \
  --delivery-account some-channel=account_id
```

如果你只想先装 OpenClaw 侧：

```bash
cd /path/to/relay-hub
python3 install.py install-openclaw
```

## 2. 应该跟 AI 编程工具说什么

下面这段可以直接发给 AI 编程工具。把其中的 `<your-agent-id>` 换成它自己的标准名字：

```text
这是一个 Relay Hub 仓库。请先阅读：

1. README.md
2. RELAY_PROTOCOL.md
3. docs/AGENT_ENTRY_RULE.md
4. docs/AGENT_WORKFLOW.md
5. docs/COMPATIBILITY.md

你的 agent_id 是 <your-agent-id>。

要求：
- 不要直接读取原始消息渠道或 OpenClaw 插件内部实现。
- 只通过 scripts/agent_relay.py、scripts/relayctl.py 和仓库文档工作。
- 当前 AI 对话窗口是主线，网页 / md 是 branch。
- 如果用户要求你参与 Relay Hub，就先按文档确认环境，再通过 agent_relay.py 接入。
- 当用户对你说“接入 Relay Hub”时，把自己标记为 ready。
- 当用户对你说“Relay Hub 状态”时，返回你当前是否 ready，以及是否有待处理 branch。
- 当用户对你说“退出 Relay Hub”时，把自己标记为 offline。
- 如果仓库尚未安装完成，先按 README 和 docs/INSTALL_PLAYBOOK.md 执行安装。
- 安装完成后，只汇报是否进入“可用状态”，不要自行替用户做完整业务测试，除非用户明确要求。
```

例如：

- `claude-code`
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
   - `打开 <agent> 入口`
   - `已录入`
   - `状态`
   - `退出`
4. 本地网页入口能打开 branch 页面
5. 网页入口和 OpenClaw 命令链已经进入可用状态

## 5. 不要做什么

- 不要让外部 AI 直接读原始消息渠道
- 不要让 OpenClaw 自己翻 Relay Hub 的底层文件
- 不要把网页 branch 当成第二条主聊天
- 不要假设仓库会替外部 AI 自动接手处理；外部 AI 仍需按协议接入

更详细的通用性边界，见 `docs/COMPATIBILITY.md`。
