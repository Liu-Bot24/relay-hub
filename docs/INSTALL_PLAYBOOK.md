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

如果当前宿主就是 Codex，并且你要把“当前 Codex 主窗口”也一起接进 Relay Hub，再在这条命令后追加：

```bash
--install-codex-host
```

这表示：

- Relay Hub 本身会先装好
- OpenClaw 桥接和网页入口会一起装好
- 只有在显式追加 `--install-codex-host` 时，才会改写 `~/.codex`
- branch 回包默认走原始触发渠道，主窗口提醒优先复用当前主会话已绑定的来源渠道；不要求先配置额外渠道
- 如果后面配置了额外回传渠道，那些渠道只是额外镜像；不会替代当前来源渠道
- 如果机器上已经配过额外回传渠道，重装时不显式传参也会保留原配置
- 外部对象后续再按 `docs/AGENT_ENTRY_RULE.md` 和 `docs/AGENT_WORKFLOW.md` 接入

如果你后面明确要“除当前来源渠道外，还要额外镜像到别的渠道”，再单独执行：

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
3. docs/INTEGRATION_CONTRACT.md
4. docs/AGENT_ENTRY_RULE.md
5. docs/AGENT_WORKFLOW.md
6. docs/COMPATIBILITY.md

你的 agent_id 是 <your-agent-id>。

要求：
- 不要直接读取原始消息渠道或 OpenClaw 插件内部实现。
- 只通过 scripts/agent_relay.py、scripts/relayctl.py 和仓库文档工作。
- 当前 AI 对话窗口是主线，网页 / md 是 branch。
- 如果用户要求你参与 Relay Hub，就先按文档确认环境，再通过 agent_relay.py 接入。
- 不要把“install.py 已跑通”误当成“已经完整接入”；只有当你已经在自己的环境里固化最小长期机制，并能持续接单时，才算完整接入。
- 安装完成后，只汇报是否进入“可用状态”，不要自行替用户做完整业务测试，除非用户明确要求。
- 当用户后续对你说“接入 Relay Hub”“Relay Hub 状态”“消息提醒状态”“开启<渠道>消息提醒”“关闭<渠道>消息提醒”“合流上下文”“退出 Relay Hub”时，严格按 docs/AGENT_ENTRY_RULE.md 和 docs/AGENT_WORKFLOW.md 执行。
- Relay Hub 运行期通过 OpenClaw 发出的固定尾注、网页入口、以及产品操作提示，都是代码内置行为；不要在这段安装话术里重写、删改或自定义它们。
```

例如（不限于此）：

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
4. docs/INTEGRATION_CONTRACT.md
5. docs/COMPATIBILITY.md

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
- 当前渠道和当前目标，默认必须从当前入站消息上下文或宿主可查询的当前会话信息里获取；只有真的拿不到时才回问用户。
- 如果当前渠道对象已经有 branch，必须主动问用户“复用入口”还是“新建入口”，不能静默替用户决定。
- 一旦你已经问出了“复用/新建”，就必须把这次待确认的 agent、channel、target 记为当前待确认入口；如果用户下一句只回答“复用”或“新建”，仍然按同一组参数重调。
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
- 不要假设仓库会替外部 AI 自动完成宿主侧接单机制；外部 AI 仍需按协议在自己环境里接入并保持持续接单能力

更详细的通用性边界，见 `docs/COMPATIBILITY.md`。
