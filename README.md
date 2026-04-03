# Relay Hub

Relay Hub 是一个中转层，用来把这三样东西接起来：

- AI 编程工具的主对话窗口
- `OpenClaw` 负责的消息渠道
- 一个临时网页工作区

它解决的问题很简单：

- 你平时在 AI 编程工具主窗口里继续主线开发
- 你离开电脑、切到手机或消息软件时，可以把要补充的内容先写进网页
- AI 再接手这次“离机处理”的任务，并把结果通过 `OpenClaw` 发回消息渠道
- 等你回到主窗口时，再把这次离机处理的增量合回原来的主线对话

可以把它理解成：

- AI 主对话窗口 = 主线
- 网页 = 临时工作区
- `OpenClaw` = 消息网关

网页链接发出去时，只表示入口已经打开；用户第一次在网页里保存消息后，这次远程处理才真正开始。

大致运行逻辑是：

1. 先在 AI 主窗口里说 `接入 Relay Hub`
2. Relay Hub 通过 `OpenClaw` 发出一条带网页入口的提醒
3. 用户如果要离机补充内容，就打开网页录入
4. 外部 AI 接手处理这次临时会话
5. 处理结果通过 `OpenClaw` 发回消息渠道
6. 用户回到 AI 主窗口时，再把这次会话增量合回主线

## 安装

### 命令安装

```bash
git clone https://github.com/Liu-Bot24/relay-hub.git
cd relay-hub
python3 install.py install-host --load-services
python3 install.py install-openclaw
```

如果 OpenClaw 工作区不在默认位置：

```bash
python3 install.py install-openclaw --openclaw-workspace /path/to/.openclaw/workspace
```

如果你只想先安装 AI 宿主侧共享层、不立刻加载服务：

```bash
python3 install.py install-host
```

建议安装后再执行两条检查：

```bash
python3 install.py doctor
python3 install.py status
```

默认安装按侧分开执行：

1. 当前 AI 宿主执行 `install-host`
2. OpenClaw 执行 `install-openclaw`

如果当前宿主没有仓库内置 adapter，就按 `docs/GENERIC_HOST_BOOTSTRAP.md` 用通用轮子完成最后一步自举。

### 交给 AI 编程工具安装

把下面这段话发给当前 AI 编程工具：

```text
请帮我安装 relay-hub。

仓库地址：
https://github.com/Liu-Bot24/relay-hub.git

请先阅读 README.md 和 docs/AI_INSTALL_PROMPT.md。
请完成安装；如果失败，告诉我失败原因。
如果成功，请分开告诉我这 3 件事：
1. 共享安装是否已经完成
2. 当前宿主的安装阶段自举是否已经完成；如果没有，明确告诉我还差什么
3. 当前主对话是否已经开启 Relay Hub；如果还没开启，只需要说明“尚未开启”，不要把它算成安装失败
另外，你只负责执行 `python3 install.py install-host ...` 和当前宿主自己的自举；不要代替 OpenClaw 执行 `install-openclaw`，不要删除、重置或重装 OpenClaw 侧现有 relay-hub 产物，也不要动别的 AI 宿主产物，除非我明确要求你这么做。
```

### 交给 OpenClaw 接入

把下面这段话发给 OpenClaw：

```text
请帮我接入 relay-hub。

仓库地址：
https://github.com/Liu-Bot24/relay-hub.git

请先阅读：
1. README.md
2. docs/OPENCLAW_RULE.md
3. docs/OPENCLAW_INTEGRATION.md
4. docs/INTEGRATION_CONTRACT.md
5. docs/COMPATIBILITY.md

请完成 OpenClaw 侧接入；如果失败，告诉我失败原因；如果成功，告诉我当前可以使用哪些 relay 命令。
首次从 AI 宿主侧开启 Relay Hub 时，默认提醒应发到当前已启用的所有 OpenClaw 消息渠道；用户后续可以再关闭不想要的渠道。
```

## 常用命令

### 命令大全

| 使用位置 | 命令 | 作用 | 备注 |
| --- | --- | --- | --- |
| AI 编程工具主窗口 | `接入 Relay Hub` | 把当前主会话接入 Relay Hub，并启动当前会话的持续接单/镜像 | 这是主窗口侧的开启命令 |
| AI 编程工具主窗口 | `Relay Hub 状态` | 查看当前主会话是否 ready、是否有待处理 branch、是否有待合回主线的历史分支 | 只查当前主会话 |
| AI 编程工具主窗口 | `消息提醒状态` | 查看当前所有默认 OpenClaw 提醒渠道的开关状态 | 默认显示当前已发现并已配置的提醒渠道 |
| AI 编程工具主窗口 | `开启<渠道>消息提醒` | 开启某一个 OpenClaw 提醒渠道 | 例如：`开启飞书消息提醒` / `开启telegram消息提醒` |
| AI 编程工具主窗口 | `关闭<渠道>消息提醒` | 关闭某一个 OpenClaw 提醒渠道 | 例如：`关闭微信消息提醒` / `关闭telegram消息提醒` |
| AI 编程工具主窗口 | `合流上下文` | 把当前主会话下尚未合回主线的分支内容接回主窗口 | 如果有多个待合流分支，会先提示选择 |
| AI 编程工具主窗口 | `退出 Relay Hub` | 关闭当前主会话的 Relay Hub | 只关闭当前主会话 |
| OpenClaw | `打开 <agent> 入口` | 打开网页入口，或在已有 branch 时让用户选择“复用入口 / 新建入口” | 如果当前入口下已有 branch，会继续追问你是复用还是新建 |
| OpenClaw | `已录入` | 把网页里刚保存的输入正式入队 | 只有网页已经保存过输入时才有效 |
| OpenClaw | `状态` | 查看当前入口 / branch 状态 | 面向当前渠道对象 |
| OpenClaw | `退出` | 退出当前 relay branch | 只退出当前 branch，不会关闭主会话 |
| OpenClaw | `relay help` | 查看这份命令大全 | 用于快速回看命令说明 |
| OpenClaw | `复用入口` / `新建入口` | 在 OpenClaw 追问时，明确选择继续旧 branch 还是创建新 branch | 用于回答上一条“复用还是新建”的追问 |

## 安装后会得到什么

`python3 install.py install-host --load-services` 会：

1. 安装 Relay Hub 本体
2. 安装网页入口并加载 Web 服务
3. 写入后续检查所需的基础状态
4. 如果你显式启用了某个宿主 adapter，再补充对应宿主侧产物

`python3 install.py install-openclaw` 会：

1. 安装或更新 OpenClaw 侧桥接与相关配置
2. 只触碰 OpenClaw 侧 relay-hub 产物，不负责宿主侧自举
3. 如果共享层还没由 `install-host` 装好，会直接报错并要求先装共享层

如果你只想确认共享安装结果，直接运行 `python3 install.py status` 即可。`status` 默认只看共享安装产物；当前宿主最后一步是否已经自举完成，应由安装它的 AI 按 `docs/GENERIC_HOST_BOOTSTRAP.md` 自己落实并汇报。

程序文件会安装到 macOS 的 `Application Support` 目录。

## 安装后怎么用

装完以后，正常流程是：

1. 用户在当前 AI 主对话里说一次：`接入 Relay Hub`
2. 这会开启 Relay Hub，并给当前活跃主对话建立接单能力
3. 用户收到 OpenClaw 同步消息，消息里自带网页入口和产品指令
4. 只要 Relay Hub 还没退出，用户切回旧主对话就继续旧主对话，切到新主对话就切到新主对话；不需要再重复说“接入 Relay Hub”
5. 用户如果只是继续在当前主窗口对话，不需要额外动作；当前主窗口回复仍可继续同步到 OpenClaw
6. 用户如果要调整哪些 OpenClaw 渠道继续收到提醒，直接在主窗口说：`消息提醒状态`、`开启<渠道>消息提醒`、`关闭<渠道>消息提醒`；这些命令默认作用于安装时自动发现并已配置的提醒渠道
7. 用户如果要离机接管，直接点网页入口并保存第一条消息；这一刻 branch 才正式开始
8. 用户回到 OpenClaw 说：`已录入`
9. 外部 AI 按协议接手 branch
10. 处理结果通过 OpenClaw 发回原消息渠道
11. 用户如需显式重发入口，或在已有 branch 上选择“复用/新建”，再说：`打开 <agent> 入口`
12. 用户回到当前 AI 主窗口说第一句话时，AI 先做一次 merge-back，再继续主线对话

## 仓库结构

```text
relay-hub/
  README.md
  install.py
  RELAY_PROTOCOL.md
  docs/
    INSTALL_PLAYBOOK.md
    INTEGRATION_CONTRACT.md
    COMPATIBILITY.md
    RUNBOOK.md
    AGENT_ENTRY_RULE.md
    AGENT_WORKFLOW.md
    OPENCLAW_INTEGRATION.md
    OPENCLAW_RULE.md
  scripts/
    relay_openclaw_bridge.py
    agent_relay.py
    openclaw_relay.py
    relayctl.py
    relay_web.py
  relay_hub/
    __init__.py
    store.py
    web.py
```

## 安装前提

- `macOS`
- `python3`
- 已安装并可用的 `OpenClaw`
- 至少一个可按协议接入的 AI 编程工具

## 常用维护命令

查看当前安装状态：

```bash
cd relay-hub
python3 install.py status
```

只重装 OpenClaw 侧桥接：

```bash
cd relay-hub
python3 install.py install-openclaw \
  --delivery-channel <channel_a>=<target_a> \
  --delivery-channel <channel_b>=<target_b> \
  --delivery-account <channel_b>=<account_b>
```

只安装或更新 `launchd` 服务：

```bash
cd relay-hub
python3 install.py install-launchd --load-services
```

宿主侧主路径：

```bash
cd relay-hub
python3 install.py install-host --load-services
```

## 文档入口

- 通用协议：`RELAY_PROTOCOL.md`
- 给 AI 编程工具的安装提示：`docs/AI_INSTALL_PROMPT.md`
- 安装章程：`docs/INSTALL_PLAYBOOK.md`
- 通用宿主自举：`docs/GENERIC_HOST_BOOTSTRAP.md`
- 接入硬章程：`docs/INTEGRATION_CONTRACT.md`
- 通用性审计：`docs/COMPATIBILITY.md`
- 给 OpenClaw 的安装提示：`docs/OPENCLAW_INSTALL_PROMPT.md`
- OpenClaw 接入映射：`docs/OPENCLAW_INTEGRATION.md`
- OpenClaw 最小规则：`docs/OPENCLAW_RULE.md`
- 外部对象最小入口：`docs/AGENT_ENTRY_RULE.md`
- 外部对象工作流：`docs/AGENT_WORKFLOW.md`
- 日常运维：`docs/RUNBOOK.md`

## 边界说明

- Relay Hub 本身是通用中转层，但不同 AI 宿主仍需要完成自己的接入。
- 消息渠道统一通过 OpenClaw 接入；只要 OpenClaw 已支持该渠道，就可以接进 Relay Hub。
- 当前仓库直接提供的是 `macOS + launchd` 的安装与服务托管。
- Relay Hub 通过 OpenClaw 对接消息渠道，不直接连接其他渠道网关。
- 网页 branch 是主线对话的临时工作区，不是第二条主对话。
- 你正在使用的 AI 主对话窗口始终是主线。
- 项目开发日志会参与 branch 上下文和回主线时的内容整理。
- 代码目录和开发日志只用于定位项目内容；主会话切换仍然跟随当前 AI 主对话。
- 如果项目里还没有 `DEVELOPMENT_LOG.md`，启用 Relay Hub 时会自动补建。
- OpenClaw 负责消息入口和回包，不负责主线快照与回主线合流。
- 外部 AI 不直接读取原始消息渠道。
- OpenClaw 也不需要直接翻 Relay Hub 的底层数据文件。
- 共享安装层允许原地更新，但不允许任何一侧擅自删除、重置或重装另一侧的现有 relay-hub 产物。
- AI 宿主只负责共享安装层和自己宿主侧的长期机制；OpenClaw 只负责自己的渠道网关动作。
- 任何跨侧清理、删除、卸载、reset、重建工作区，都必须先得到用户明确授权。

所有消息渠道读写都通过固定桥接 CLI 完成。
