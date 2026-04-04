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
6. docs/GENERIC_HOST_BOOTSTRAP.md
7. docs/GENERIC_HOST_RULE_TEMPLATE.md
8. docs/AGENT_WORKFLOW.md
9. docs/COMPATIBILITY.md

先自己确定下面两件事，不要先来问我：
1. 仓库根目录
- 如果你当前已经在仓库根目录，就直接使用当前目录
- 如果你不在仓库根目录，就自动定位到同时包含 README.md、install.py、RELAY_PROTOCOL.md 的目录
2. 你的 agent_id
- 使用你当前宿主稳定、可持续复用的名字
- 如果仓库里已经存在你对应的既有 `agent_id` 约定，就复用那一份；否则不要临时起一个会漂移的新名字

然后执行当前宿主安装：
python3 install.py install-host --load-services

如果仓库里已经提供了与你当前宿主匹配的可选 adapter，并且启用它能让“当前主窗口”直接接进 Relay Hub，就把对应参数加在 `install-host` 后面；否则保持通用宿主安装主路径，不要自行发明宿主专属参数，并按 `docs/GENERIC_HOST_BOOTSTRAP.md` 自己完成最后一步宿主自举。

安装完成后，再执行：
1. python3 install.py doctor
2. python3 install.py status

安装完成标准：
- doctor 返回 ok=true
- status 能看到 openclaw bridge、skill、heartbeat、web plist 等共享安装产物
- 阅读 status 时，只把它当成共享安装结果；不要把运行期规则提前套到安装汇报里

安装阶段的宿主自举完成标准：
- 你已经在自己的环境里真正创建或刷新了最小长期规则 / skill / guide，而不是只说“后面会记住”
- 你已经回读、列出，或用宿主提供的等价方式验证这份长期规则确实存在
- 你已经明确当前主对话如何稳定生成并复用 main_session_ref
- 你已经明确将来用户说“接入 Relay Hub”时要执行的完整启动链路：
  - 先写主线快照
  - 再执行带 `--project-root` 与 `--snapshot-body/--snapshot-file` 的 `enable-relay --start-pickup`
- 你给 `--backend-command` 填的必须是真实可工作的宿主 CLI；占位符、`echo`、`printf`、`true`、`false`、`sleep` 这类假命令都不算完成
- 你已经在宿主环境里真正落下“每条主窗口正常回复后自动执行精确镜像”的持久机制；如果还需要每条回复人工补跑 `capture-main-output`，那不算完成
- 你在声称“做不到自动镜像”之前，已经检查过当前宿主版本的本地设置和官方文档里的 hooks / automation / watcher；如果宿主支持原生 after-reply hook，优先把它接到仓库提供的通用 helper，而不是自己重拼镜像命令
- 如果宿主支持 hooks / watcher，安装阶段只有在你已经把 helper 调用真正写进宿主持久化设置，并回读验证该配置存在后，才算自动镜像已完成
- 只要宿主存在“回复结束时触发、且 payload 带最终正文”的 stop / completion / lifecycle hook，它就应被视为可用的 after-reply 载体；不要因为事件名不是 after-reply 就错误判定“做不到自动镜像”
- 如果仓库没有当前宿主的原生 adapter，但你已经按 `docs/GENERIC_HOST_BOOTSTRAP.md` 完成以上步骤，就不要再把自己报告成“宿主未完整接入”

安装完成后的汇报格式：
- 必须分成 3 段分别汇报：
  1. 共享安装状态
  2. 当前宿主自举状态
  3. 当前主对话 Relay 开启状态
- 第 1 段只汇报 `doctor / status` 对共享安装产物的结论
- 第 2 段只汇报当前宿主是否已经把长期规则、`agent_id`、`main_session_ref` 规则、`command` backend 启动链路，以及主窗口自动精确镜像机制落下并验证
- 第 3 段如果用户还没说 `接入 Relay Hub`，就明确写“当前主对话尚未开启 Relay Hub”
- 不要把第 3 段的“尚未开启”写成第 2 段的“宿主未完整接入”

额外判断规则：
- 安装汇报时只关注当前宿主；默认不要提本机上其他 AI 工具已有的 adapter、home 目录或宿主产物，除非我明确追问
- 如果当前主对话还没说 `接入 Relay Hub`，不要把“pickup 现在还没运行”误报成缺项；这表示 relay 还没开启，不表示宿主自举失败
- 如果用户当前这条主对话还没说 `接入 Relay Hub`，这表示“当前 relay 尚未开启”，不是“宿主未完整接入”

安装要求：
- install.py 会自动探测本机局域网地址；只有探测失败时，才回头问我
- 默认不要求你手工配置额外消息渠道；`install-openclaw` 应自动发现当前已启用的 OpenClaw 消息渠道，并把它们设为首次主窗口开启时的默认提醒渠道；branch 回包仍默认走原始触发渠道
- 如果我后面明确要求覆盖默认发现结果，或额外指定某个固定目标，那时你再执行：
  python3 install.py install-openclaw --delivery-channel channel=target --delivery-account channel=accountId
- 你当前是 AI 宿主，只负责执行 `install-host` 和当前宿主自举；不要代替 OpenClaw 执行 `install-openclaw`，也不要使用 `full` 这种跨侧组合安装，除非我明确要求
- `install-openclaw` 现在要求共享层已经存在；如果 OpenClaw 侧后续安装时报“请先执行 install-host”，那是正确行为，不要自己改成跨侧代装
- 你只允许做两类写入：
  1. 通过 `install.py` 原地更新共享安装产物
  2. 落当前宿主自己的长期规则 / skill / guide / adapter（包括宿主自己的 hooks / watcher / settings 配置）
- 不要删除、重置、重装或清空 OpenClaw 侧已有 relay-hub 产物；不要删除、重置、重装或清空别的 AI 宿主产物，除非我明确要求
- 如果你判断某个跨侧删除、reset、重建工作区、清空目录、卸载旧版本动作“也许有帮助”，先停下并告诉我风险，不要自己执行
- 不要直接读取原始消息渠道或 OpenClaw 插件内部实现
- 不要自行做业务对话测试，除非我明确要求
- 如果安装失败，就原样贴出失败点并停止，不要自创旁路方案
- 安装完成后，必须先把当前宿主自己的长期机制真正落下，再做安装汇报
- 不要把“我知道后续可以手动执行 `capture-main-output`”当成自动镜像已完成；只有宿主环境里已经存在可持续复用的自动触发机制，才算安装阶段自举完成
- 如果宿主支持把原始 hook payload 传给本地命令，优先使用安装后的 `relay_after_reply_hook.py` helper 作为通用镜像入口
- 不要把无关宿主信息塞进安装结论里
- 当用户后续说 `接入 Relay Hub` 时，不要先裸跑 `enable-relay` 探路；对通用宿主，第一次调用就必须带上 `--project-root` 和 `--snapshot-body` 或 `--snapshot-file`
- 当用户后续对你说“接入 Relay Hub”“Relay Hub 状态”“消息提醒状态”“开启<渠道>消息提醒”“关闭<渠道>消息提醒”“合流上下文”“退出 Relay Hub”时，严格按 `docs/AGENT_ENTRY_RULE.md` 和 `docs/AGENT_WORKFLOW.md` 执行
- Relay Hub 运行期通过 OpenClaw 发出的固定尾注、网页入口、以及产品操作提示，都是代码内置行为；不要在安装 prompt 里重写、删改或自定义它们
```
