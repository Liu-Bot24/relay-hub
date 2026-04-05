# Relay Hub 接入硬章程

这份文件定义的是接入边界，不是安装步骤。

## 0. 4 个状态

当前分支统一按下面 4 层判断：

1. **宿主侧共享安装完成**
   - `install-host` 成功
   - `status` 能看到 runtime / app / 宿主 Web 托管等共享产物
2. **当前宿主自举完成**
   - 当前宿主已经把长期规则、`agent_id`、`main_session_ref` 规则、pickup 启动链路、自动精确镜像机制真正落下并验证
3. **OpenClaw 侧接入完成**
   - `install-openclaw` 成功
   - OpenClaw bridge / skill / heartbeat block 已安装
4. **当前主对话已开启 Relay Hub**
   - 用户在当前主对话明确说了 `接入 Relay Hub`

这些状态互相独立：

- 宿主侧共享安装完成，不等于 OpenClaw 侧已经具备
- 当前宿主自举完成，不等于当前主对话已经开启 Relay Hub
- OpenClaw 侧接入完成，不等于真实消息渠道端到端已经实机验证完成

## 1. 侧边界和所有权

Relay Hub 接入有 3 类产物：

1. 共享安装层
   - `install.py` 安装出来的 runtime / app / 宿主 Web 托管等共享产物
2. 宿主侧产物
   - 当前 AI 宿主自己的长期规则 / skill / guide / automation / adapter
3. OpenClaw 侧产物
   - OpenClaw 工作区里的 bridge、config、skill、heartbeat block

硬规则：

- AI 宿主默认只执行 `install-host`
- OpenClaw 默认只执行 `install-openclaw`
- `full` 只保留给用户明确授权的组合安装 / 运维场景
- `install-openclaw` 不负责补装共享层；共享层缺失时应直接报错并要求先执行 `install-host`
- AI 宿主不得擅自删除、reset、重装或清空 OpenClaw 侧现有 relay-hub 产物
- OpenClaw 不得擅自删除、reset、重装或清空 AI 宿主侧现有 relay-hub 产物
- 任何跨侧清理、卸载、重建工作区、删除目录或清空旧版本动作，都必须先得到用户明确授权

## 2. 外部 AI 的接入硬要求

如果一个 AI 宿主声称自己“已接入 Relay Hub”，至少要满足这些要求：

1. 能在自己的环境里长期保留一份最小规则 / skill / guide
2. 能稳定维护 `agent_id`
3. 能稳定维护 `main_session_ref`
4. 用户说 `接入 Relay Hub` 时，能用**一次** `enable-relay --start-pickup` 把当前主对话接入
5. 接入完成后，能持续接走分配给自己的 `queued` branch
6. 接入状态下，主窗口正常回复后能自动精确镜像到 OpenClaw

如果只是能手动跑命令、不能持续接单，或每条主窗口回复都要人工补跑 `capture-main-output`，那只能算：

- 共享层已安装
- 或宿主仍未完整接入

## 3. 宿主开启 Relay Hub 的标准序列

当用户在主窗口说 `接入 Relay Hub` 时，通用主路径必须按这个顺序：

1. 确定当前项目根目录
2. 复用或创建当前项目的 `DEVELOPMENT_LOG.md`
3. 写入一条主线快照
4. 以完整参数执行一次 `enable-relay --start-pickup`
5. pickup 真正运行后，才把自己视为 `ready`

通用主路径里，不要写成：

- 先裸跑 `enable-relay`
- 再单独补跑一遍 `start-pickup`

如果某个宿主优化实现已经明确把这些动作封装进自己的原生入口，那只是宿主增强；产品主路径仍以这一套通用顺序为准。

## 4. `main_session_ref` 规则

`main_session_ref` 是 branch 能否安全合回主线的核心字段。

硬规则：

- 同一条 AI 主对话必须稳定复用同一个 `main_session_ref`
- 只有用户明确进入一条新的主对话时，才换新的 `main_session_ref`
- 优先使用宿主原生提供的 conversation / thread / session id
- 如果宿主没有暴露原生会话标识，就在该主对话第一次被 Relay Hub 接管时生成一个稳定 ref
- 这个 ref 必须保存在当前主对话可持续复用的宿主载体里，而不是只存在单条回复或短暂上下文里

## 5. merge-back 默认标准

通用默认是：

- 用户回到主窗口后，如需先接回 branch 增量，应显式说 `合流上下文`
- 宿主收到这条命令后，再执行 `resume-main`

只有当前宿主已经真实落下可靠的前置 hook / pre-user 机制时，才允许把相同动作写成自动触发。

## 6. OpenClaw 的入站上下文硬要求

OpenClaw 不是主记忆体，但它必须正确拿到当前入站消息上下文。

硬规则：

- 当前渠道和当前目标，默认从当前入站消息 / 当前会话上下文里直接取
- 只有宿主真的拿不到时，才回问用户
- 如果当前渠道对象已经有 branch，而这次调用没有显式指定“复用”或“新建”，OpenClaw 必须主动追问用户，不能静默替用户决定
- OpenClaw 只调用已安装 bridge，不直接翻 `routes.json`、`state.json`、`messages/*.md`
