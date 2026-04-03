# 通用宿主自举

这份文档定义的是：当仓库里还没有当前宿主的原生 adapter 时，安装阶段最后一步应该怎么由当前 AI 宿主自己补齐。

目标不是给某一个工具写特判，而是给任意 AI 编程工具一套通用落地法。

## 1. 什么时候使用

满足下面任一条件时，就走这份文档：

- 仓库没有当前宿主的原生 adapter
- 当前宿主虽然能执行本地命令，但没有现成的会话解析优化实现
- 当前宿主可以自己长期保留最小规则，并能调用自己的 CLI 非交互执行

## 2. 安装阶段必须补齐什么

当前 AI 宿主在跑完：

```bash
python3 install.py full --load-services
```

之后，必须自己补齐下面 4 件事：

1. 在自己的环境里落下一份持久生效的最小规则 / skill / guide
2. 明确自己的稳定 `agent_id`
3. 明确当前宿主如何生成并复用 `main_session_ref`
4. 明确持续接单时使用的 `command` backend 命令

如果这 4 件事都已经补齐，就不要再把自己报告成“宿主未完整接入”。

## 3. 最小长期规则必须记住什么

这份规则至少要记住：

- `agent_id`
- `main_session_ref` 的生成规则
- 主窗口产品口令：
  - `接入 Relay Hub`
  - `Relay Hub 状态`
  - `消息提醒状态`
  - `开启<渠道>消息提醒`
  - `关闭<渠道>消息提醒`
  - `合流上下文`
  - `退出 Relay Hub`
- 接单主链路：
  - `claim-next -> branch-context -> reply -> resume-main`
- 主窗口正常回复后的精确镜像规则：
  - 若宿主拿不到代码级原文，就把最终正文原样写入文件，再执行
    `python3 scripts/agent_relay.py --agent <agent_id> capture-main-output --body-file <exact_body_file>`

## 4. agent_id 规则

- 使用当前宿主稳定、可持续复用的产品名
- 不要为了示例临时起漂移名字
- 示例：
  - `claude-code`
  - `gemini-cli`
  - `cursor-cli`
  - `opencode`

## 5. main_session_ref 规则

- 优先使用当前宿主原生提供的 conversation / thread / session id
- 如果宿主没有暴露原生会话 id，就在该主对话第一次被 Relay Hub 接管时生成一个稳定 ref
- 同一主对话必须复用同一个 ref
- 只有用户明确开启新的主对话时才换新的 ref
- `project_root` 只能用来定位代码目录、开发日志和工作区，不能拿来冒充主会话 id

## 6. command backend 规则

若当前宿主没有仓库内置 backend，就统一走：

```bash
python3 scripts/agent_relay.py --agent <agent_id> start-pickup \
  --main-session-ref <main_session_ref> \
  --backend command \
  --backend-command '<json_string_array>'
```

其中 `<json_string_array>` 必须是：

- 当前宿主自己的非交互 CLI 调用
- 能从 stdin 读取 prompt，或等价地接受传入上下文
- 能把最终正文输出到 stdout，或写入 `RELAY_OUTPUT_FILE`

这一步由当前 AI 宿主自己根据自己的 CLI 形态补齐，不要因为仓库没点名当前工具就停在“还不能用”。

## 7. 安装完成后应该怎么汇报

安装完成时要区分下面两件事：

### 机器安装完成

表示：

- `doctor` 通过
- OpenClaw bridge / skill / heartbeat / web 已就位

### 宿主自举完成

表示：

- 当前宿主的最小长期规则已经落下
- `agent_id` 已明确
- `main_session_ref` 规则已明确
- `command` backend 命令已明确

### 当前主对话是否已开启 Relay Hub

这是第三件事，和前两件不同。

如果用户当前这条主对话还没有说 `接入 Relay Hub`，应报告为：

- 宿主已完成接入准备
- 但当前主对话尚未开启 Relay Hub

不要把这种状态误报成“宿主未完整接入”。

只有在下面这些情况，才应明确报告“当前宿主接入还没完成”：

- 无法落持久规则 / skill / guide
- 无法确定稳定 `agent_id`
- 无法确定 `main_session_ref` 规则
- 无法确定任何可工作的 `command` backend

## 8. 当前仓库提供的通用轮子

- `scripts/agent_relay.py`
- `scripts/relay_agent_daemon.py`
- `docs/AGENT_ENTRY_RULE.md`
- `docs/AGENT_WORKFLOW.md`

当前宿主应优先用这些轮子完成最后一步组装，而不是等仓库为自己新增专属会话解析。
