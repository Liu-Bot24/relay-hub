# Relay Hub 接入硬章程

这份文件定义的是“接入方必须做到什么”，不是安装步骤，也不是协议细节补充。

它回答 4 件事：

1. 什么叫“完整支持 Relay Hub”
2. 外部 AI 应该如何持续接单
3. `main_session_ref` 应该怎么取
4. `OpenClaw` 应该如何从当前入站上下文取渠道信息

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

仓库不会替任何特定 AI 内置专属后台接单器。

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

### 2.2 开启和关闭

当用户说：

- `接入 Relay Hub`

外部 AI 必须按这个顺序做：

1. 定位当前项目根目录
2. 查找或创建 `DEVELOPMENT_LOG.md`
3. 立刻写一条主线快照
4. 把自己标记为 `ready`
5. 启动或恢复“持续接单”机制

当用户说：

- `退出 Relay Hub`

外部 AI 必须：

1. 关闭持续接单机制
2. 把自己标记为 `offline`

### 2.3 持续接单的最低标准

完整支持模式下，外部 AI 不能只会手动执行一次 `claim-next`。

它应在自己环境里持续做这件事：

1. 只要自己是 `ready`
2. 就周期性检查是否有 `queued` branch
3. 一旦有，就立即 `claim-next`
4. 补齐 `main_session_ref / main_context / project_root / development_log`
5. 再继续 `branch-context -> reply`

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

## 5. 开发日志软约束

开发日志不做硬门槛，但它是推荐工作流的一部分。

最少应做到：

1. 接入 Relay Hub 时写主线快照
2. branch 处理中出现实质性进展时补写日志
3. merge-back 前把开发日志增量一起纳入参考

如果接入方模型在规则清楚的前提下仍长期做不到这些，说明它本身就不适合承担这套仓库下的稳定开发任务。
