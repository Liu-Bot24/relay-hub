# 通用宿主自举

这份文档定义的是：当仓库里还没有当前宿主的原生 adapter 时，安装阶段最后一步应该怎么由当前 AI 宿主自己补齐。

目标不是给某一个工具写特判，而是给任意 AI 编程工具一套通用落地法。

安装阶段“宿主自举是否完成”的唯一验收标准，以这份文档为准。
其他文档如果提到安装完成，只能做摘要提醒，不应再另写一套独立标准。

## 1. 什么时候使用

满足下面任一条件时，就走这份文档：

- 仓库没有当前宿主的原生 adapter
- 当前宿主虽然能执行本地命令，但没有现成的会话解析优化实现
- 当前宿主可以自己长期保留最小规则，并能调用自己的 CLI 非交互执行

## 2. 安装阶段必须补齐什么

当前 AI 宿主在跑完：

```bash
python3 install.py install-host --load-services
```

之后，必须自己立刻完成并验证下面 5 件事：

1. 在自己的环境里落下一份持久生效的最小规则 / skill / guide
2. 明确自己的稳定 `agent_id`
3. 明确当前宿主如何生成并复用 `main_session_ref`
4. 明确持续接单时使用的 `command` backend 命令
5. 落下一条“每次主窗口正常回复后自动执行精确镜像”的持久机制

如果这 5 件事都已经补齐，就不要再把自己报告成“宿主未完整接入”。

注意：

- 这里说的是“现在就完成”，不是“脑内记住以后再做”
- 至少要把规则真正写进宿主支持的持久载体里，并在安装阶段回读或等价验证一次
- 如果主窗口精确镜像还需要你后面每条回复手动补跑一次 `capture-main-output`，那不算已经补齐
- 如果需要现成模板，直接使用 `docs/GENERIC_HOST_RULE_TEMPLATE.md`

## 2.1 安装阶段必须真的把长期机制落下

允许的载体包括：

- 宿主自带的长期 rule / instruction / guide
- 宿主 skill
- 项目级 guide
- 宿主 automation / watcher

安装阶段必须做到：

1. 选择当前宿主真正会长期生效的载体
2. 把最小规则写进去，而不是只在当前回复里描述
3. 写完后回读、列出，或用宿主提供的等价方式确认它已经存在
4. 另外再为“主窗口正常回复后的自动精确镜像”选择一个真正会长期运行的触发载体，例如宿主 automation / watcher / reply hook，或宿主持久规则里的“回复收尾流程”
5. 验证这条触发机制不是单次手动命令，而是后续每条主窗口正常回复都会自动触发
6. 如果宿主支持 hooks / watcher，还必须把 helper 调用真正写进宿主的持久化设置文件或等价载体，并在安装阶段回读验证

优先顺序建议：

1. 优先使用当前宿主会自动加载的项目级 guide / rule / instruction 载体
2. 如果没有项目级自动加载载体，再使用宿主自己的全局持久规则载体
3. 如果前两者都没有，再退回宿主 automation / watcher 等可持续复用机制

光有一份文字规则还不够；如果主窗口镜像仍要靠人工在每条回复后手动补跑 `capture-main-output`，那说明自动机制没有落下，安装阶段自举仍未完成。

但如果宿主没有原生 after-reply hook，却支持“持久规则 + 本地命令执行”，那么把这条镜像链路写进宿主自己的回复收尾流程也算自动机制。关键不是事件名，而是：

- 用户不需要每轮再提醒一次
- 宿主自己会在每次主窗口正常回复前自动执行
- 被排进镜像队列的正文，和最终真正发给用户的正文是同一份文本

如果这一步没做，才算“当前宿主接入还没完成”。

## 2.2 安装阶段不要误报 pickup 未启动

如果用户当前这条主对话还没有说 `接入 Relay Hub`，那么：

- 持续接单守护进程此刻还没运行，不应单独算成缺项
- 真正需要完成的是：把将来如何启动 `start-pickup` 的链路持久记住
- 只有当你连可工作的 `start-pickup --backend command --backend-command ...` 方案都确定不了时，才应报告“当前宿主接入还没完成”

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
  - 必须在宿主环境里持久落下一条“每次主窗口正常回复后自动触发”的机制
  - 若宿主拿不到代码级原文，就把最终正文原样写入文件，再自动执行
    `python3 scripts/agent_relay.py --agent <agent_id> capture-main-output --body-file <exact_body_file>`
  - 只在出错补救时手动补跑一条，不算安装完成

## 3.1 自动镜像触发载体的选择顺序

优先顺序：

1. 当前宿主原生提供的 after-reply / stop / lifecycle hook
2. 宿主持久规则里可稳定复用的“回复收尾流程”
3. 当前宿主原生提供的 automation / watcher / post-response action
4. 宿主明确支持的本地 transcript watcher

判断规则：

- 只要某个 hook / event 是在“本轮回复结束时”触发，并且 payload 里能拿到最终正文，它就应被视为可用的 after-reply 载体
- 不要求宿主字面上必须叫 `after-reply`
- 例如 `stop` / `completion` / `response-finished` 一类事件，只要满足上面两条，就不能再说“宿主没有 after-reply hook”

安装当前宿主的 AI 必须先自己检查：

- 宿主当前版本的本地设置 / 配置文件
- 宿主官方文档里当前版本可用的 hooks / automation / watcher

只有在这些都确认不存在时，才允许报告“当前宿主无法自动镜像，所以安装阶段自举未完成”。

如果宿主能把原始 hook payload 管道给本地命令，优先复用仓库自带的通用 helper：

```bash
python3 "<app_root>/scripts/relay_after_reply_hook.py" --agent <agent_id>
```

这个 helper 会：

- 在 Relay Hub 已附着时自动读取当前 `main_session_ref`
- 从原始 hook payload 里提取最终正文
- 把正文排进精确镜像队列

宿主只需要把自己的 after-reply hook / watcher 接到这个 helper，而不是自己重拼 `capture-main-output` 参数。

如果宿主支持 hooks / watcher，但安装阶段还没有把这条 helper 调用真实写进宿主设置并回读验证，就不能报告“宿主自举已完成”。

如果宿主没有可用原生 hook，但支持持久规则 / skill / guide，并且能在正常回复过程中执行本地命令，那么可以改走“宿主内回复收尾流程”：

1. 先把即将发给用户的最终正文原样写进临时文件
2. 再执行：

```bash
python3 "<app_root>/scripts/relay_after_reply_hook.py" --agent <agent_id> --body-file <exact_body_file>
```

3. 最后把同一份 `<exact_body_file>` 的内容作为真正的最终回复发给用户

这条路径同样算自动精确镜像，因为：

- 它由宿主自己的持久规则自动触发
- 不需要用户再额外提醒
- 镜像出去的正文与最终回复完全一致

只有“需要用户每轮提醒你补跑一次命令”才算手动补跑；宿主按持久规则在回复收尾阶段自动执行，不算手动。

## 3.2 通用 hook 宿主最小可抄样例

如果宿主的“回复结束”hook 能把原始 payload 直接传给本地命令，最小接法就是：

```bash
python3 /absolute/path/to/relay-hub/scripts/relay_after_reply_hook.py --agent <agent_id>
```

常见的 JSON 风格 hook 配置，可以直接抄成下面这个骨架，再把事件名替换成当前宿主自己的“回复结束”事件：

```json
{
  "event": "<reply_finished_event>",
  "command": [
    "python3",
    "/absolute/path/to/relay-hub/scripts/relay_after_reply_hook.py",
    "--agent",
    "<agent_id>"
  ]
}
```

如果宿主不会把 payload 走 stdin，而是先落到临时文件，再执行本地命令，最小接法改成：

```json
{
  "event": "<reply_finished_event>",
  "command": [
    "python3",
    "/absolute/path/to/relay-hub/scripts/relay_after_reply_hook.py",
    "--agent",
    "<agent_id>",
    "--payload-file",
    "<payload_file>"
  ]
}
```

如果宿主给出的不是整段 payload，而是“最终正文文件路径”，则改成：

```json
{
  "event": "<reply_finished_event>",
  "command": [
    "python3",
    "/absolute/path/to/relay-hub/scripts/relay_after_reply_hook.py",
    "--agent",
    "<agent_id>",
    "--body-file",
    "<exact_body_file>"
  ]
}
```

如果 payload 里的正文不在 helper 默认字段里，再额外补 `--field`：

```bash
python3 /absolute/path/to/relay-hub/scripts/relay_after_reply_hook.py \
  --agent <agent_id> \
  --field finalText
```

最低要求只有两条：

- 事件必须真的是“本轮回复结束后”触发
- 最终接进宿主设置的命令，必须是 `relay_after_reply_hook.py` 或等价自动镜像链路，而不是人工补跑一次 `capture-main-output`

如果当前宿主正好是 `Codex`、`Claude Code`、`Gemini CLI`、`Cursor CLI`，可再参考 `docs/HOST_EXAMPLES.md` 里的对应示例文件。

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
- 不能是占位符、`echo`、`printf`、`true`、`false`、`sleep` 之类的假命令

这一步由当前 AI 宿主自己根据自己的 CLI 形态补齐，不要因为仓库没点名当前工具就停在“还不能用”。

## 6.1 启用 Relay Hub 时不要裸跑 enable-relay

对通用宿主，推荐直接一次性执行：

```bash
python3 scripts/agent_relay.py --agent <agent_id> enable-relay \
  --project-root <project_root> \
  --development-log-path <development_log_path> \
  --main-session-ref <main_session_ref> \
  --snapshot-body "<snapshot_body>" \
  --backend command \
  --backend-command '<json_string_array>' \
  --start-pickup
```

注意：

- 不要先用裸的 `enable-relay` 探路
- 对通用宿主，`--project-root` 必填
- 对通用宿主，`--snapshot-body` 或 `--snapshot-file` 也必须从第一次调用就带上
- 只有 `codex` 这种仓库内置了当前会话解析的宿主，才可能在特定路径下自动省略其中一部分参数

## 7. 安装完成后应该怎么汇报

安装完成时要区分下面两件事：

### 机器安装完成

表示：

- `doctor` 通过
- OpenClaw bridge / skill / heartbeat / web 已就位

### 宿主自举完成

表示：

- 当前宿主的最小长期规则已经落下
- 并且已经回读或等价验证过
- `agent_id` 已明确
- `main_session_ref` 规则已明确
- `command` backend 命令已明确
- 主窗口正常回复后的自动精确镜像机制已落下，并确认后续每条回复都会自动触发

### 当前主对话是否已开启 Relay Hub

这是第三件事，和前两件不同。

如果用户当前这条主对话还没有说 `接入 Relay Hub`，应报告为：

- 宿主已完成接入准备
- 但当前主对话尚未开启 Relay Hub

不要把这种状态误报成“宿主未完整接入”。

## 7.1 安装汇报默认只关注当前宿主

安装汇报时：

- 只评估当前正在执行安装的宿主
- 默认不要提本机上其他 AI 工具已有的 adapter、home 目录或宿主产物
- 除非用户明确追问，否则不要把无关宿主当作当前结论的一部分
- 最好固定分成“共享安装状态 / 当前宿主自举状态 / 当前主对话 Relay 开启状态”三段汇报

只有在下面这些情况，才应明确报告“当前宿主接入还没完成”：

- 无法落持久规则 / skill / guide
- 无法确定稳定 `agent_id`
- 无法确定 `main_session_ref` 规则
- 无法确定任何可工作的 `command` backend
- 无法在宿主环境里落下“每条主窗口正常回复后自动执行精确镜像”的持久机制

## 8. 当前仓库提供的通用轮子

- `scripts/agent_relay.py`
- `scripts/relay_agent_daemon.py`
- `docs/AGENT_ENTRY_RULE.md`
- `docs/AGENT_WORKFLOW.md`

当前宿主应优先用这些轮子完成最后一步组装，而不是等仓库为自己新增专属会话解析。
