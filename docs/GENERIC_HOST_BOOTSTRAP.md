# 通用宿主自举

这份文件定义的是：当仓库里没有当前宿主的现成 adapter 时，安装阶段最后一步应该怎么由当前 AI 宿主自己补齐。

安装阶段“宿主自举是否完成”的唯一验收标准，以这份文档为准。

## 1. 什么时候使用

满足下面任一条件时，就走这份文档：

- 仓库没有当前宿主的现成 adapter
- 当前宿主虽然能执行本地命令，但没有现成的会话解析优化实现
- 当前宿主可以自己长期保留最小规则，并能调用自己的 CLI 非交互执行

## 2. `install-host` 之后必须补齐什么

当前 AI 宿主在跑完：

```powershell
py -3 install.py install-host --load-services
```

之后，必须自己立刻完成并验证下面 5 件事：

1. 在自己的环境里落下一份持久生效的最小规则 / skill / guide
2. 明确自己的稳定 `agent_id`
3. 明确当前宿主如何生成并复用 `main_session_ref`
4. 明确持续接单时使用的 backend 命令
5. 落下一条“每次主窗口正常回复后自动执行精确镜像”的持久机制

如果这 5 件事都已经补齐，就不要再把自己报告成“宿主未完整接入”。

## 3. 允许的持久载体

允许的载体包括：

- 宿主自带的长期 rule / instruction / guide
- 宿主 skill
- 项目级 guide
- 宿主 automation / watcher / hook 配置

不允许把下面这些东西冒充成持久载体：

- memory
- session cache
- history
- 临时 transcript
- 临时 notes
- 安装时临时写出来的一次性验证文件

`docs/HOST_EXAMPLES/*` 只是在宿主特定文件路径 / 格式需要参考时使用。  
产品语义、完成标准和验收口径，始终以这份文档为准。

## 4. 先确定安装后脚本路径

通用 helper 应指向**安装后的 app 副本**，不是旧 clone、也不是来源不明的其他 checkout。

默认情况下：

- `installed_app_root = %LOCALAPPDATA%\RelayHub\app`

如果安装时使用了自定义根目录，就以：

```powershell
py -3 install.py status
```

输出里的 `app_root` 为准。

后面的命令示例统一使用：

- `<installed_app_root>\scripts\agent_relay.py`
- `<installed_app_root>\scripts\relay_after_reply_hook.py`

## 5. 自动精确镜像怎么落

优先顺序：

1. 当前宿主原生提供的 reply-end / stop / lifecycle hook
2. 宿主持久规则里可稳定复用的“回复收尾流程”
3. 当前宿主原生提供的 automation / watcher / post-response action

只要某个机制满足下面 3 条，就算有效自动镜像：

- 用户不需要每轮再提醒一次
- 每条主窗口正常回复都会自动触发
- 被排进镜像队列的正文，和最终真正发给用户的正文是同一份文本

如果宿主支持把 hook payload 传给本地命令，优先接通用 helper：

```powershell
py -3 "<installed_app_root>\scripts\relay_after_reply_hook.py" --agent <agent_id>
```

常见 JSON 风格 hook 配置骨架：

```json
{
  "event": "<reply_finished_event>",
  "command": [
    "py",
    "-3",
    "<installed_app_root>\\scripts\\relay_after_reply_hook.py",
    "--agent",
    "<agent_id>"
  ]
}
```

如果宿主拿不到原始 payload，但能在回复收尾阶段自动执行本地命令，也可以走保底路径：

1. 先把最终正文原样写入 `<exact_body_file>`
2. 再自动执行：

```powershell
py -3 "<installed_app_root>\scripts\relay_after_reply_hook.py" --agent <agent_id> --body-file "<exact_body_file>"
```

只有“出问题时手工补跑一次”不算完成。

如果你新增了 transcript / payload extractor，不能只测“脚本能跑通”；必须用“前一条 assistant 文本”和“最后一条 assistant 文本”不同的最小夹具验证它真的抓到最后一条回复，再报告完成。

## 6. `enable-relay` 的标准启动链路

通用主路径统一使用**一次**完整调用：

```powershell
py -3 "<installed_app_root>\scripts\agent_relay.py" --agent <agent_id> enable-relay --project-root "<project_root>" --snapshot-body "<snapshot_body>" --backend command --backend-command "<verified_backend_command_json>" --start-pickup
```

硬规则：

- 不要先裸跑 `enable-relay`
- 不要再在后面单独补跑一遍 `start-pickup`
- 第一次调用就带上 `--project-root`
- 第一次调用就带上 `--snapshot-body` 或 `--snapshot-file`
- backend 命令如果还没验证，宿主自举就还没完成

只有在当前宿主已经明确启用了某个可选增强组件、并且该组件确实提供了当前会话解析能力时，才允许在宿主增强路径里省略部分参数。通用主路径不要假设这一点。

## 7. 安装阶段不要偷跑运行期接入

- 安装阶段的目标是把“将来如何接入”和“将来如何自动镜像”持久落下
- 除非用户此刻明确要求执行 `接入 Relay Hub`，否则不要为了“验证 backend”而启动真实 pickup、开启真实 Relay、或偷跑业务对话
- 如果用户当前这条主对话还没说 `接入 Relay Hub`，安装汇报里的第 3 段应明确写“当前主对话尚未开启 Relay Hub”

## 8. 安装完成后应该怎么汇报

统一分成 3 段：

1. **共享安装状态**
   - 只汇报 `install-host`、`status`、`doctor` 对共享产物的结论
2. **当前宿主自举状态**
   - 只汇报长期规则、`agent_id`、`main_session_ref` 规则、backend 启动链路、自动精确镜像机制是否已经落下并验证
3. **当前主对话 Relay 开启状态**
   - 如果用户还没说 `接入 Relay Hub`，就明确写“当前主对话尚未开启 Relay Hub”

通用默认的 merge-back 标准是：

- 用户回到主窗口后先说 `合流上下文`
- 宿主收到后再执行 `resume-main`

只有当前宿主已经真实落下可靠的前置 hook / pre-user 机制时，才允许把这件事写成自动完成。
