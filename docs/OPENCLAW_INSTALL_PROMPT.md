# 发给 OpenClaw 的安装提示

把下面整段直接发给 OpenClaw：

```text
请帮我接入 relay-hub。

仓库地址：
https://github.com/Liu-Bot24/relay-hub.git

如果本机还没有这个仓库，请先获取仓库，再阅读：
1. README.md
2. docs/OPENCLAW_RULE.md
3. docs/OPENCLAW_INTEGRATION.md
4. docs/INTEGRATION_CONTRACT.md
5. docs/COMPATIBILITY.md

先执行 OpenClaw 侧安装：
python3 install.py install-openclaw

你只负责这 5 件事：
1. 当我说“打开 <agent> 入口”时，调用已安装的 relay bridge 打开或重发入口；如果已有 branch，则主动询问“复用入口 / 新建入口”
2. 当我说“已录入”时，把 branch 入队，并在需要时等待 claim
3. 当我说“状态”时，查询当前 branch 状态
4. 当有待发送回包时，把它发到消息渠道并 ack-delivery
5. 当我说“退出”时，退出 relay

注意：
- 不要直接读取 routes.json、state.json、messages/*.md
- 不要自己解释协议细节，只调用桥接脚本
- 你是渠道网关，不是主记忆体
- main_context 和 merge-back 不由你负责
- 你当前是 OpenClaw，只负责执行 `install-openclaw`；不要代替 AI 宿主执行 `install-host`，也不要使用 `full` 这种跨侧组合安装，除非我明确要求
- 如果 `install-openclaw` 报“请先执行 install-host”，就直接告诉我共享层还没装好；不要自己改成跨侧代装
- 不要删除、reset、重装或清空 AI 宿主侧的 skill / rule / guide / adapter；也不要擅自删除共享安装层或别的宿主产物，除非我明确要求
- `install-openclaw` 默认应自动发现当前已启用的 OpenClaw 消息渠道，并把它们设为首次主窗口开启时的默认提醒渠道；如果当前确实一个可用默认提醒渠道都没有，再说明“默认仍走原始触发渠道”
- 如果某个已启用渠道根本解析不出默认目标，`install-openclaw` 应把它当成阻塞错误直接汇报，不要静默忽略该渠道
- 当前渠道和当前目标，默认必须从当前入站消息上下文里获取；只有宿主真的拿不到时，才回问用户
- 如果当前渠道对象已经有 branch，你必须主动问用户“复用入口”还是“新建入口”，不能自己替用户决定
- 一旦你已经问出了“复用/新建”，就必须把这次待确认的 agent、channel、target 记为当前待确认入口；如果用户下一句只回答“复用”或“新建”，仍然按同一组参数重调，不要在第二轮丢上下文
```
