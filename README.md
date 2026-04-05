# Relay Hub

Relay Hub 把 3 个角色接到同一条主线上：

- AI 编程工具的主对话窗口
- `OpenClaw` 负责的消息渠道
- 一个只承担 branch 工作区的网页入口

产品主线始终在 AI 宿主的主对话里。网页只是 branch 工作区，`OpenClaw` 只是消息网关，不承担主记忆体。

## `main-Windows` 分支定位

- 这个分支只提供 Windows 安装与运行主路径。
- 安装源只接受**可验证的 `main-Windows` git 副本**；不要在 zip、解压目录或来源不明的本地副本上继续安装。
- 宿主侧共享安装和 OpenClaw 侧接入必须分开执行。
- 当前分支不宣称“Windows + OpenClaw + 真实消息渠道”已经端到端实机完成。

## 安装

### 1. 准备仓库

新 clone：

```powershell
git clone -b main-Windows https://github.com/Liu-Bot24/relay-hub.git
cd relay-hub
```

如果本机已经有这个仓库的 git 副本：

```powershell
git fetch origin
git switch main-Windows
```

只允许在这样一个**可验证分支**上继续安装。  
如果当前目录不是 git 副本，或无法确认当前分支就是 `main-Windows`，不要继续安装。

### 2. 宿主侧共享安装

```powershell
py -3 install.py install-host --load-services
```

如果你只想先安装共享层、不立刻加载宿主 Web：

```powershell
py -3 install.py install-host
```

安装后检查：

```powershell
py -3 install.py status
py -3 install.py doctor
```

解释：

- `status` 只用来确认共享安装产物是否到位。
- 如果当前机器还没有 `OpenClaw`，`doctor` 可能因为 `openclaw_cli` 缺失而不是 `ok=true`；这不等于宿主侧共享安装失败。
- 当前宿主最后一步是否已经自举完成，要按 [docs/GENERIC_HOST_BOOTSTRAP.md](/D:/work/Claude%20Code/relay-hub/docs/GENERIC_HOST_BOOTSTRAP.md) 判断。

### 3. OpenClaw 侧接入

这一步只应由 `OpenClaw` 执行，不是宿主侧默认步骤。

```powershell
py -3 install.py install-openclaw
```

如果 OpenClaw 工作区不在默认位置：

```powershell
py -3 install.py install-openclaw --openclaw-workspace "%USERPROFILE%\.openclaw\workspace"
```

### 发给 AI 编程工具

把下面整段发给当前 AI 编程工具：

```text
请帮我安装 relay-hub。

先确认当前安装源是可验证的 `main-Windows` git 副本：

1. 如果本机还没有这个仓库的 git 副本，执行：
   git clone -b main-Windows https://github.com/Liu-Bot24/relay-hub.git
   cd relay-hub
2. 如果本机已经有这个仓库的 git 副本，先执行：
   git fetch origin
   git switch main-Windows
3. 如果当前目录不是 git 副本，或无法确认当前分支是 main-Windows，就停止并告诉我“当前安装源不可验证，不要在 zip/解压目录上继续安装”。

然后阅读 README.md 和 docs/AI_INSTALL_PROMPT.md。

你当前只负责宿主侧共享安装和当前宿主自举：
- 只执行 `py -3 install.py install-host ...`
- 不要执行 `install-openclaw`
- 不要删除、重置或重装 OpenClaw 侧现有 relay-hub 产物
- 不要动别的 AI 宿主产物，除非我明确要求

安装完成后，请分开告诉我这 3 件事：
1. 共享安装是否已经完成
2. 当前宿主自举是否已经完成；如果没有，明确告诉我还差什么
3. 当前主对话是否已经开启 Relay Hub；如果还没开启，只写“尚未开启”，不要把它算成安装失败
```

### 发给 OpenClaw

把下面整段发给 OpenClaw：

```text
请帮我接入 relay-hub。

先确认当前安装源是可验证的 `main-Windows` git 副本：

1. 如果本机还没有这个仓库的 git 副本，执行：
   git clone -b main-Windows https://github.com/Liu-Bot24/relay-hub.git
   cd relay-hub
2. 如果本机已经有这个仓库的 git 副本，先执行：
   git fetch origin
   git switch main-Windows
3. 如果当前目录不是 git 副本，或无法确认当前分支是 main-Windows，就停止并告诉我“当前安装源不可验证，不要在 zip/解压目录上继续安装”。

然后阅读：
1. README.md
2. docs/OPENCLAW_INSTALL_PROMPT.md
3. docs/OPENCLAW_RULE.md
4. docs/OPENCLAW_INTEGRATION.md

你当前只负责 OpenClaw 侧：
- 只执行 `py -3 install.py install-openclaw`
- 不要执行 `install-host`
- 不要调用仓库里的旧桥接入口
- 安装完成后只调用已安装的 `relay_openclaw_bridge.py`
- 不要删除、reset、重装或清空 AI 宿主侧 relay-hub 产物，除非我明确要求
```

## 完成态

当前分支统一按这 4 层判断：

1. **宿主侧共享安装完成**
   - `install-host` 成功
   - `status` 能看到 runtime / app / 宿主 Web 托管等共享产物
2. **当前宿主自举完成**
   - 当前宿主已经把长期规则、`agent_id`、`main_session_ref` 规则、pickup 启动链路、自动精确镜像机制真正落下并验证
3. **OpenClaw 侧接入完成**
   - `install-openclaw` 成功
   - OpenClaw 已安装自己的 bridge / skill / heartbeat block
4. **当前主对话已开启 Relay Hub**
   - 只有用户在当前主对话明确说了 `接入 Relay Hub`，这一步才成立

这 4 层互相独立。  
“当前主对话尚未开启 Relay Hub”不等于“宿主未完整接入”。  
“当前机器还没有 OpenClaw”也不等于“宿主侧共享安装失败”。

## 运行期口令

| 使用位置 | 命令 | 作用 |
| --- | --- | --- |
| AI 编程工具主窗口 | `接入 Relay Hub` | 把当前主会话接入 Relay Hub，并进入持续接单状态 |
| AI 编程工具主窗口 | `Relay Hub 状态` | 查看当前主会话是否 ready、是否有待处理 branch、是否有待合回主线的历史 branch |
| AI 编程工具主窗口 | `消息提醒状态` | 查看当前默认 OpenClaw 提醒渠道的开关状态 |
| AI 编程工具主窗口 | `开启<渠道>消息提醒` | 开启某一个已配置提醒渠道 |
| AI 编程工具主窗口 | `关闭<渠道>消息提醒` | 关闭某一个已配置提醒渠道 |
| AI 编程工具主窗口 | `合流上下文` | 把当前主会话下尚未合回主线的 branch 增量接回主窗口 |
| AI 编程工具主窗口 | `退出 Relay Hub` | 关闭当前主会话的 Relay Hub |
| OpenClaw | `打开 <agent> 入口` | 打开网页入口，或在已有 branch 时追问“复用入口 / 新建入口” |
| OpenClaw | `已录入` | 把网页里刚保存的输入正式入队 |
| OpenClaw | `状态` | 查看当前入口 / branch 状态 |
| OpenClaw | `relay help` | 返回 Relay Hub 固定命令大全 |
| OpenClaw | `复用入口` / `新建入口` | 回答上一条“复用还是新建”的追问 |

## 运行期行为

### 宿主侧完成后的可用行为

- 用户后续在当前主对话说 `接入 Relay Hub`，当前主会话才真正开启 Relay Hub。
- 开启后，当前主窗口的正常回复应自动镜像到 OpenClaw；如果仍需要每条回复手工补命令，说明宿主自举还没完成。
- branch 回主线的通用默认是：用户显式说 `合流上下文`。只有当前宿主已经真实落下可靠的前置 hook / pre-user 机制时，才允许自动先执行同样动作。

### 端到端目标流程

下面这条链路只有在真实 OpenClaw 实例、真实消息渠道、以及外部 AI 接单链路都联通后才成立；不要把它当成当前分支已经实机背书的结论：

1. 用户在 AI 主对话里说 `接入 Relay Hub`
2. OpenClaw 收到启动提醒，消息里带网页入口
3. 用户打开网页并保存第一条消息
4. 用户回到 OpenClaw 说 `已录入`
5. 外部 AI claim 这个 branch 并处理
6. OpenClaw 的发送泵把结果发回原消息渠道
7. 用户回到主窗口说 `合流上下文`，再继续主线对话

## 常用维护命令

查看共享安装状态：

```powershell
py -3 install.py status
```

只安装或更新宿主 Web 托管：

```powershell
py -3 install.py install-service --load-services
```

只安装或更新 OpenClaw 侧 bridge：

```powershell
py -3 install.py install-openclaw --delivery-channel <channel>=<target> --delivery-account <channel>=<accountId>
```

## 文档入口

- 给 AI 编程工具的安装提示：[docs/AI_INSTALL_PROMPT.md](/D:/work/Claude%20Code/relay-hub/docs/AI_INSTALL_PROMPT.md)
- 给 OpenClaw 的安装提示：[docs/OPENCLAW_INSTALL_PROMPT.md](/D:/work/Claude%20Code/relay-hub/docs/OPENCLAW_INSTALL_PROMPT.md)
- 安装章程：[docs/INSTALL_PLAYBOOK.md](/D:/work/Claude%20Code/relay-hub/docs/INSTALL_PLAYBOOK.md)
- 接入硬章程：[docs/INTEGRATION_CONTRACT.md](/D:/work/Claude%20Code/relay-hub/docs/INTEGRATION_CONTRACT.md)
- 通用宿主自举：[docs/GENERIC_HOST_BOOTSTRAP.md](/D:/work/Claude%20Code/relay-hub/docs/GENERIC_HOST_BOOTSTRAP.md)
- OpenClaw 接入映射：[docs/OPENCLAW_INTEGRATION.md](/D:/work/Claude%20Code/relay-hub/docs/OPENCLAW_INTEGRATION.md)
- OpenClaw 最小规则：[docs/OPENCLAW_RULE.md](/D:/work/Claude%20Code/relay-hub/docs/OPENCLAW_RULE.md)
- 外部 AI 最小入口：[docs/AGENT_ENTRY_RULE.md](/D:/work/Claude%20Code/relay-hub/docs/AGENT_ENTRY_RULE.md)
- 外部 AI 工作流：[docs/AGENT_WORKFLOW.md](/D:/work/Claude%20Code/relay-hub/docs/AGENT_WORKFLOW.md)
- 日常运维：[docs/RUNBOOK.md](/D:/work/Claude%20Code/relay-hub/docs/RUNBOOK.md)
- 卸载说明：[docs/UNINSTALL.md](/D:/work/Claude%20Code/relay-hub/docs/UNINSTALL.md)

## 边界

- Relay Hub 本身是通用产品层，但这个分支只交付 Windows 安装主路径。
- 消息渠道统一通过 OpenClaw 接入；Relay Hub 不直接读写原始消息渠道。
- 网页 branch 是主线对话的临时工作区，不是第二条主对话。
- `project_root` 只用于定位代码目录、开发日志和工作区；不用于控制主会话边界。
- 共享安装层允许原地更新；任何跨侧删除、reset、卸载或重建工作区，都必须先得到用户明确授权。
