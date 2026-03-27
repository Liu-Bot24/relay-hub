# Relay Hub 接入硬章程

这份文件定义的是“接入方必须做到什么”，不是安装步骤，也不是协议细节补充。

它回答 4 件事：

1. 什么叫“完整支持 Relay Hub”
2. 外部 AI 应该如何持续接单
3. `main_session_ref` 应该怎么取
4. `OpenClaw` 应该如何从当前入站上下文取渠道信息

## 0. 安装完成 vs 完整接入

这两个概念不是一回事。

### 安装完成

表示：

- 仓库文件已安装
- OpenClaw bridge / skill / web 服务已就位
- `doctor / status` 通过

### 完整接入

表示在“安装完成”之外，还满足：

- 外部 AI 已在自己的环境里建立最小长期机制
- 外部 AI 已有稳定的 `main_session_ref` 规则
- 外部 AI 在 `ready` 时能持续接单

如果只装好了文件，但外部 AI 还没有持续接单机制，那它只能算：

- 已安装

还不能算“完整接入”。

## 1. 什么叫“完整支持”

一个 AI 编程工具如果声称自己“已接入 Relay Hub”，至少要满足下面 4 条：

1. 能在自己的环境里长期保留一份最小规则或 skill
2. 能执行 `scripts/agent_relay.py`
3. 能在用户说“接入 Relay Hub”时进入可接单状态
4. 能在进入可接单状态后，持续监控并接走分配给自己的 branch

如果只能手动执行命令、不能持续接单，它仍然可以使用这套仓库，但只能算：

- `manual-only`

不能算“完整接入”。

## 2. 外部 AI 的接入硬要求

### 2.1 必须创建宿主侧最小长期机制

仓库提供通用持续接单轮子，但不会替任何特定 AI 内置专属宿主实现。

因此，外部 AI 在第一次接入时，必须在自己的环境里落一个最小长期机制，例如：

- skill
- rule
- bootstrap prompt
- 项目级 guide
- 宿主自带的 automation / watcher

这份机制至少要记住：

- `agent_id`
- `main_session_ref` 的生成规则
- “接入 Relay Hub / Relay Hub 状态 / 退出 Relay Hub”这 3 个用户口令
- 接单后如何 `claim-next -> branch-context -> reply -> resume-main`
- 当 OpenClaw 先开入口时，第一次正式接单要补齐哪些信息

### 2.2 开启和关闭

当用户说：

- `接入 Relay Hub`

外部 AI 必须按这个顺序做：

1. 定位当前项目根目录
2. 优先复用当前项目已有的 `DEVELOPMENT_LOG.md`（默认项目根；如果宿主环境已有该项目自己的日志路径，就继续用那份）；只有没有时，才在项目根目录创建
3. 立刻写一条主线快照
4. 执行 `enable-relay`
5. 为当前主对话执行一次 `start-pickup`
6. 只有在持续接单机制真的运行后，才能把自己视为完整 `ready`

当用户说：

- `退出 Relay Hub`

外部 AI 必须：

1. 关闭持续接单机制
2. 执行 `stop-pickup`
3. 把自己标记为 `offline`

### 2.3 持续接单的最低标准

完整支持模式下，外部 AI 不能只会手动执行一次 `claim-next`。

它应在自己环境里持续做这件事：

1. 只要自己是 `ready`
2. 就周期性检查是否有 `queued` branch
3. 一旦有，就立即 `claim-next`
4. 补齐 `main_session_ref / main_context / project_root / development_log`
5. 再继续 `branch-context -> reply`

一个足够通用的最低模板是：

1. 只要自己是 `ready`
2. 就周期性检查 `agent-status`
3. 如果发现 `queued_count > 0`
4. 就立刻 `claim-next`
5. 若 branch 缺少主线摘要，再立刻补写
6. 然后执行 `branch-context -> reply`

仓库已经提供通用轮子：

- `scripts/relay_agent_daemon.py`
- `scripts/agent_relay.py start-pickup / pickup-status / stop-pickup`

你可以直接使用这套轮子，或者在宿主环境里做等价实现；但不能退化成“每次靠用户重新教一次”。

如果宿主环境完全做不到这件事，外部 AI 应明确告诉用户：

- “当前环境只支持 manual-only，不支持完整接单模式”

不要假装已经完整接入。

## 3. main_session_ref 规范

`main_session_ref` 是 branch 能否安全合流回主线的核心字段。

### 3.1 基本规则

同一条 AI 主对话窗口，必须稳定复用同一个 `main_session_ref`。

只有在用户明确开启一条新的主对话时，才应该换新的 `main_session_ref`。

### 3.2 取值优先级

优先级从高到低：

1. 宿主环境原生提供的稳定主会话标识
   - 例如 conversation id / thread id / session id
2. 如果宿主没有暴露原生会话标识
   - 就在当前主对话第一次“接入 Relay Hub”时自行生成一个稳定 ref
   - 并在该主对话范围内持续复用

### 3.3 生成值的要求

如果是自生成的 `main_session_ref`，要求是：

- 在当前主对话范围内稳定不变
- 不和别的主对话混淆
- 不依赖用户每次手工输入
- 必须存放在当前主对话可持续复用的宿主载体里，而不是只存在单条回复或短暂上下文里

推荐形态：

- `<agent_id>:<stable-local-main-session-id>`

但具体格式不强制。

## 4. OpenClaw 的入站上下文硬要求

`OpenClaw` 不是主记忆体，但它必须正确拿到当前入站消息上下文。

### 4.1 当前渠道与目标怎么取

默认规则：

- 从“当前这条入站消息 / 当前会话”的宿主上下文里直接取

不要：

- 使用文档示例值
- 沿用上一次无关会话的渠道或目标
- 让用户自己手工重复输入本来宿主已经知道的信息

### 4.2 取不到时怎么办

顺序必须是：

1. 先用宿主已经提供的上下文能力取
2. 仍然取不到，再查询宿主可用的当前会话信息
3. 只有在宿主真的拿不到时，才回问用户

### 4.3 已有 branch 时的行为

如果当前渠道对象已经有 branch：

- `OpenClaw` 必须主动询问用户“复用入口”还是“新建入口”
- 不能静默替用户决定
- 一旦问出了这个问题，就必须把当时的 `agent / channel / target` 作为“当前待确认入口”保留下来
- 如果用户下一句只说“复用”或“新建”，仍然要按同一组参数重调，不要在第二轮丢失待确认上下文

## 5. 开发日志软约束

开发日志不做硬门槛，但它是推荐工作流的一部分。

最少应做到：

1. 接入 Relay Hub 时写主线快照
2. branch 处理中出现实质性进展时补写日志
3. merge-back 前把开发日志增量一起纳入参考

如果接入方模型在规则清楚的前提下仍长期做不到这些，说明它本身就不适合承担这套仓库下的稳定开发任务。
