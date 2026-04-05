# 发给 OpenClaw 的安装提示

把下面整段直接发给 OpenClaw：

```text
这是 Relay Hub 的 Windows 分支 OpenClaw 接入任务。

你先只做两件事：
1. 确认当前安装源是可验证的 `main-Windows` git 副本
2. 只执行 OpenClaw 侧安装和 OpenClaw 侧桥接动作

安装源规则：

- 如果本机还没有这个仓库的 git 副本，执行：
  git clone -b main-Windows https://github.com/Liu-Bot24/relay-hub.git
  cd relay-hub
- 如果本机已经有这个仓库的 git 副本，先进入那份仓库根目录，再执行：
  git fetch origin
  git switch main-Windows
- 如果当前目录不是 git 副本，或无法确认当前分支就是 `main-Windows`，就停止并告诉用户：
  “当前安装源不可验证；不要在 zip、解压目录或来源不明的本地副本上继续安装。”

然后阅读：
1. README.md
2. docs/OPENCLAW_RULE.md
3. docs/OPENCLAW_INTEGRATION.md
4. docs/INTEGRATION_CONTRACT.md

重要边界：

- 你当前是 OpenClaw；只执行 `py -3 install.py install-openclaw`
- 不要执行 `install-host`
- 不要使用 `full`
- 不要调用仓库里的旧桥接入口
- 安装完成后，只调用已安装的 `relay_openclaw_bridge.py`
- 不要删除、reset、重装或清空 AI 宿主侧已有 relay-hub 产物，除非用户明确要求

直接执行：
- `py -3 install.py install-openclaw`

如果自动发现不到默认提醒渠道，只能显式传 `--delivery-channel <channel>=<target>` / `--delivery-account <channel>=<accountId>`。这里的 `<target>` 必须是真实 OpenClaw 渠道对象；不要写 `default` 这类占位值。对飞书，目标应使用真实 peer id，例如 `user:<openId>` 或 `chat:<chatId>`。

如果 `install-openclaw` 报“请先执行 install-host”，就直接告诉用户共享层还没装好；不要自己跨侧补装。

安装完成后，你对 Relay Hub 的职责只有这些：
1. 当用户说“打开 <agent> 入口”时，调用已安装 bridge 的 `open-entry`
2. 当用户说“已录入”时，调用已安装 bridge 的 `dispatch-input`
3. 当用户说“状态”时，调用已安装 bridge 的 `session-status`
4. 当有待发送回包时，调用已安装 bridge 的 `pump-deliveries`
5. 当用户说“relay help”时，调用已安装 bridge 的 `relay-help`

额外规则：

- 当前渠道和当前目标，默认必须从当前入站消息上下文里获取；只有真的拿不到时才回问用户
- 如果当前渠道对象已经有 branch，你必须主动问用户“复用入口”还是“新建入口”；不能替用户决定
- 一旦问出了“复用/新建”，就必须保留这次待确认入口的 `agent / channel / target`，用户下一句只回答“复用”或“新建”时，仍按同一组参数重调
- 不要直接读取 routes.json、state.json、messages/*.md
- 不要自己解释协议细节，只调用已安装 bridge
- 你是渠道网关，不是主记忆体；main_context 和 merge-back 不由你负责
```
