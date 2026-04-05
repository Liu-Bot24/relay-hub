# Relay Hub 安装章程

这份文件只讲安装，不讲协议细节。

它回答 3 件事：

1. 仓库下载后，应该先执行什么安装命令
2. 应该跟 AI 编程工具说什么
3. 应该跟 `OpenClaw` 说什么

协议本体仍然是仓库根的 `RELAY_PROTOCOL.md`。

## 1. 人类先做的事

先把仓库放到本机。仓库路径就是这个包本身的路径。

仓库来源只允许这两类：

- 用户已经有一份本地目录：只要该目录同时包含 `README.md`、`install.py`、`RELAY_PROTOCOL.md`，就直接使用它；即使这是桌面上的解压目录、下载目录里的副本、或没有 `.git` 的包目录，也算有效安装源
- 本机确实还没有本地副本：这时才允许 `git clone`

禁止做的事：

- 发现当前目录已经是有效仓库后，又擅自 clone 第二份
- 因为“桌面上的目录不是 git clone”就额外再下载一份
- 把仓库 clone 到临时目录、缓存目录、隐藏工作区、或用户并未明确感知的位置

如果必须 clone，目标路径只能使用可预期位置，例如当前目录下的 `./relay-hub`，或用户 home 下的 `~/relay-hub`；不要自己发明第三个落点。

建议先执行一次自检：

```bash
cd /path/to/relay-hub
py -3 install.py doctor
```

说明：

- `web_base_url` 默认会由安装器自动探测局域网 IPv4 后生成，只有探测失败时才回落到 `127.0.0.1`
- 如果当前机器还没有 `OpenClaw`，这一步可能因为 `openclaw_cli` 缺失而不是 `ok=true`；这不妨碍你先完成 `install-host`

通过后，再执行完整安装：

```bash
cd /path/to/relay-hub
py -3 install.py install-host --load-services
```

如果仓库里已经提供了与你当前宿主匹配的可选 adapter，并且启用它能让“当前主窗口”也一起接进 Relay Hub，就在这条命令后追加对应参数；否则保持通用宿主安装主路径，并按 `docs/GENERIC_HOST_BOOTSTRAP.md` 让当前宿主自己完成最后一步自举，不要自行发明宿主专属参数。

这表示：

- Relay Hub 本身会先装好
- 网页入口与共享服务会一起装好
- 如果你额外启用了某个宿主 adapter，才会改写对应宿主自己的目录
- branch 回包默认走原始触发渠道
- `install-openclaw` 默认会自动发现当前已启用的 OpenClaw 消息渠道，并把它们设为首次主窗口开启时的默认提醒渠道
- 如果某个已启用渠道解析不出默认目标，`install-openclaw` 应直接报错，不要静默漏掉该渠道
- 如果机器上已经配过默认提醒渠道，重装时不显式传参也会保留原配置，并补齐新增的已启用渠道
- OpenClaw 侧需要单独执行 `install-openclaw`
- `install-openclaw` 要求共享层已经由 `install-host` 装好；如果共享层缺失，应直接报错而不是跨侧代装
- 外部对象后续再按 `docs/AGENT_ENTRY_RULE.md` 和 `docs/AGENT_WORKFLOW.md` 接入

如果你后面明确要覆盖自动发现结果，或额外指定某个固定目标，再单独执行：

```bash
cd /path/to/relay-hub
py -3 install.py install-openclaw \
  --delivery-channel some-channel=target_id \
  --delivery-account some-channel=account_id
```

如果你只想先装 OpenClaw 侧：

```bash
cd /path/to/relay-hub
py -3 install.py install-openclaw
```

## 2. 应该跟 AI 编程工具说什么

如果你只是要一份可直接复制的提示，优先使用 `docs/AI_INSTALL_PROMPT.md`。

下面这段是同一份安装提示的展开版，便于审查口径。把其中的 `<your-agent-id>` 换成它自己的标准名字：

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
- 你当前是 AI 宿主，只负责执行 `install-host` 和当前宿主自举；不要代替 OpenClaw 执行 `install-openclaw`，也不要使用 `full` 这种跨侧组合安装，除非用户明确要求。
- 你只允许原地更新共享安装层，并写入当前宿主自己的长期机制；不要删除、reset、重装或清空 OpenClaw 侧现有 relay-hub 产物，也不要碰别的 AI 宿主产物，除非用户明确要求。
- 如果你认为必须做跨侧清理或破坏性重装，先停下并向用户说明风险，不要自己执行。
- 安装汇报必须分成三段：共享安装状态、当前宿主自举状态、当前主对话 Relay 开启状态。
- 如果用户当前还没说 `接入 Relay Hub`，只允许把第 3 段写成“尚未开启”；不要把它误写成“宿主未完整接入”。
- 安装完成后，只汇报是否进入“可用状态”，不要自行替用户做完整业务测试，除非用户明确要求。
- 当用户后续对你说“接入 Relay Hub”“Relay Hub 状态”“消息提醒状态”“开启<渠道>消息提醒”“关闭<渠道>消息提醒”“合流上下文”“退出 Relay Hub”时，严格按 docs/AGENT_ENTRY_RULE.md 和 docs/AGENT_WORKFLOW.md 执行。
- Relay Hub 运行期通过 OpenClaw 发出的固定尾注、网页入口、以及产品操作提示，都是代码内置行为；不要在这段安装话术里重写、删改或自定义它们。
```

`<your-agent-id>` 应该就是当前宿主自己稳定、可持续复用的标识；不要为了迎合文档示例，临时改成别的名字。

## 3. 应该跟 OpenClaw 说什么

如果你只是要一份可直接复制的提示，优先使用 `docs/OPENCLAW_INSTALL_PROMPT.md`。

下面这段是同一份提示的展开版：

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
- 发送 pull-deliveries 里的待回包消息

要求：
- 不要直接读取 routes.json、state.json、messages/*.md。
- 只通过 scripts/openclaw_relay.py 或安装后写入 ~/.openclaw/workspace/scripts/relay_openclaw_bridge.py 的桥接脚本工作。
- OpenClaw 只是渠道网关，不是主记忆体。
- main_context 和 merge-back 不由你负责。
- 你当前是 OpenClaw，只负责执行 `install-openclaw`；不要代替 AI 宿主执行 `install-host`，也不要使用 `full` 这种跨侧组合安装，除非用户明确要求。
- 如果执行 `install-openclaw` 时发现共享层不存在，应直接告诉用户先让 AI 宿主执行 `install-host`，不要自己补装共享层。
- 不要删除、reset、重装或清空 AI 宿主侧的 skill / rule / guide / adapter；也不要擅自删除共享安装层或别的宿主产物，除非用户明确要求。
- 如果已经自动发现了默认提醒渠道，就直接如实汇报；如果当前确实没有任何可用默认提醒渠道，再说明“默认仍走原始触发渠道”，不要主动把“加哪个渠道”当成当前安装回执的一部分。
- 当前渠道和当前目标，默认必须从当前入站消息上下文或宿主可查询的当前会话信息里获取；只有真的拿不到时才回问用户。
- 如果当前渠道对象已经有 branch，必须主动问用户“复用入口”还是“新建入口”，不能静默替用户决定。
- 一旦你已经问出了“复用/新建”，就必须把这次待确认的 agent、channel、target 记为当前待确认入口；如果用户下一句只回答“复用”或“新建”，仍然按同一组参数重调。
- 如果用户要求接入 Relay Hub，而本机尚未安装完成，就先按 README 和 docs/INSTALL_PLAYBOOK.md 分侧完成 `install-host` 与 `install-openclaw`，不要默认回到 `full`。
```

## 4. 成功标准

当下面几件事都成立时，就可以认为仓库已经安装到“可用状态”：

1. 宿主侧共享安装完成后，`py -3 install.py status` 能看到当前已经安装到位的共享产物
   - `status` 只用于确认共享安装产物
   - 当前宿主最后一步是否已经自举完成，要由安装它的 AI 按 `docs/GENERIC_HOST_BOOTSTRAP.md` 实际落下长期机制后再汇报
2. 若当前机器同时具备 OpenClaw 侧前提，`py -3 install.py doctor ...` 应返回 `"ok": true`
3. `OpenClaw` 能响应：
   - `打开 <agent> 入口`
   - `已录入`
   - `状态`
   - `relay help`
4. 本地网页入口能打开 branch 页面
5. 网页入口和 OpenClaw 命令链已经进入可用状态

## 5. 不要做什么

- 不要让外部 AI 直接读原始消息渠道
- 不要让 OpenClaw 自己翻 Relay Hub 的底层文件
- 不要把网页 branch 当成第二条主聊天
- 不要让 AI 宿主擅自清理 OpenClaw 侧 relay-hub 产物，也不要让 OpenClaw 擅自清理 AI 宿主侧产物
- 任何删除、卸载、reset、重建工作区这类破坏性动作，都必须先得到用户明确授权
- 仓库目标是尽量提供通用轮子，让外部 AI 低门槛自主接入；如果某个宿主当前还没把这些轮子真正接好，应视为该宿主接入未完成，而不是产品目标状态

更详细的通用性边界，见 `docs/COMPATIBILITY.md`。

