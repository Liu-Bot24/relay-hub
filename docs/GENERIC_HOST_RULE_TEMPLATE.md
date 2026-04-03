# 通用宿主最小规则模板

当仓库里没有当前宿主的原生 adapter 时，安装它的 AI 应该立刻把下面这份模板改成适合自己宿主的持久规则，并落到自己真正会长期生效的位置。

可选载体包括：

- 宿主自带的长期 rule / instruction / guide
- 宿主 skill
- 项目级 guide
- 宿主 automation / watcher

优先使用当前宿主会自动加载的项目级 guide / rule；如果没有，再用宿主自己的全局持久规则载体。

安装阶段不要只说“后续我会记住这些”，而要真正写下去，并在写完后回读或等价验证一次。

可直接改写的最小模板如下：

```text
你支持 Relay Hub。

固定记住：

1. agent_id = <当前宿主稳定名字>
2. main_session_ref 规则：
   - 优先复用宿主原生 conversation / thread / session id
   - 若宿主没有原生会话 id，就在该主对话第一次接入 Relay Hub 时生成稳定 ref
   - 同一主对话复用同一个 ref
   - 用户明确开启新主对话时才更换 ref
3. project_root 只能用于定位代码目录、开发日志和工作区，不能冒充 main_session_ref
4. 主窗口产品口令：
   - 接入 Relay Hub
   - Relay Hub 状态
   - 消息提醒状态
   - 开启<渠道>消息提醒
   - 关闭<渠道>消息提醒
   - 合流上下文
   - 退出 Relay Hub
5. branch 主链路：
   - claim-next -> branch-context -> reply -> resume-main
6. 主窗口正常回复后的精确镜像：
   - 若没有宿主专属正文捕获实现，就把最终正文原样写入文件
   - 再执行：
     python3 scripts/agent_relay.py --agent <agent_id> capture-main-output --body-file <exact_body_file>
7. 启用 Relay Hub 时的启动链路：
   - 先写 DEVELOPMENT_LOG.md 主线快照
   - 再执行 enable-relay
   - 再执行 start-pickup
8. start-pickup 默认模板：
   python3 scripts/agent_relay.py --agent <agent_id> start-pickup --main-session-ref <main_session_ref> --backend command --backend-command '<json_string_array>'
9. <json_string_array> 必须替换成当前宿主自己的非交互 CLI 调用
10. 只有在用户真的说了“接入 Relay Hub”并且 pickup 已运行后，才报告 ready

安装阶段额外规则：

1. 现在就把这份规则落到持久载体里，不要停在口头说明
2. 写完后回读或等价验证，确认后续会持续生效
3. 安装汇报时只关注当前宿主，不提无关宿主或本机上别的 adapter，除非用户明确问
4. 如果当前主对话还没说“接入 Relay Hub”，不要把“pickup 现在还没运行”误报成缺项；只需要确认将来如何启动它已经被持久记住
5. 安装汇报固定分成三段：
   - 共享安装状态
   - 当前宿主自举状态
   - 当前主对话 Relay 开启状态
```
