# 发给 AI 编程工具的安装提示

把下面整段直接发给当前 AI 编程工具：

```text
这是 Relay Hub 仓库。

仓库地址：
https://github.com/Liu-Bot24/relay-hub.git

如果本机还没有这个仓库，请先克隆；如果已经有本地副本，就直接定位到包含 README.md、install.py、RELAY_PROTOCOL.md 的仓库根目录。请在该仓库根目录工作，并严格按下面流程执行，不要自行简化步骤。

先优先阅读这 4 个关键文件：
1. README.md
2. RELAY_PROTOCOL.md
3. docs/INTEGRATION_CONTRACT.md
4. docs/AGENT_ENTRY_RULE.md

如果读完上面 4 个文件后还需要具体安装细节，再补读：
5. docs/INSTALL_PLAYBOOK.md
6. docs/AGENT_WORKFLOW.md
7. docs/COMPATIBILITY.md

先自己确定下面两件事，不要先来问我：
1. 仓库根目录
- 如果你当前已经在仓库根目录，就直接使用当前目录
- 如果你不在仓库根目录，就自动定位到同时包含 README.md、install.py、RELAY_PROTOCOL.md 的目录
2. 你的 agent_id
- 使用你当前宿主稳定、可持续复用的名字
- 如果仓库里已经存在你对应的既有 `agent_id` 约定，就复用那一份；否则不要临时起一个会漂移的新名字

然后执行安装：
python3 install.py full --load-services

如果仓库里已经提供了与你当前宿主匹配的可选 adapter，并且启用它能让“当前主窗口”直接接进 Relay Hub，就一并启用；否则保持通用安装主路径，不要自行发明宿主专属参数。

安装完成后，再执行：
1. python3 install.py doctor
2. python3 install.py status

安装完成标准：
- doctor 返回 ok=true
- status 能看到 openclaw bridge、skill、heartbeat、web plist 等基础安装产物
- 如果你额外安装了当前宿主的 host adapter，status 里还应能看到对应宿主侧产物

完整接入标准：
- 你已经在自己的环境里固化最小长期规则 / skill / guide
- 你已经明确当前主对话如何稳定生成并复用 main_session_ref
- 你已经把“显式开启一次、随后跟随当前活跃主会话切换、同一时间只保留一个活跃主会话、主窗口精确镜像”都落好
- 你已经进入 ready，并且持续接单机制已经真正启动；如果做不到，就明确说明当前接入还没完成，不要把自己报告成 ready

安装要求：
- install.py 会自动探测本机局域网地址；只有探测失败时，才回头问我
- 默认不要求你先配置额外消息渠道；branch 回包默认走原始触发渠道，主窗口提醒优先复用当前主会话已绑定的来源渠道
- 如果我后面明确要求“除当前来源渠道外，还要额外镜像到别的渠道”，那时你再执行：
  python3 install.py install-openclaw --delivery-channel channel=target --delivery-account channel=accountId
- 不要直接读取原始消息渠道或 OpenClaw 插件内部实现
- 不要自行做业务对话测试，除非我明确要求
- 如果安装失败，就原样贴出失败点并停止，不要自创旁路方案
- 安装完成后，不要在这段安装约束里继续脑补运行期行为
- 当用户后续对你说“接入 Relay Hub”“Relay Hub 状态”“消息提醒状态”“开启<渠道>消息提醒”“关闭<渠道>消息提醒”“合流上下文”“退出 Relay Hub”时，严格按 `docs/AGENT_ENTRY_RULE.md` 和 `docs/AGENT_WORKFLOW.md` 执行
- Relay Hub 运行期通过 OpenClaw 发出的固定尾注、网页入口、以及产品操作提示，都是代码内置行为；不要在安装 prompt 里重写、删改或自定义它们
```
