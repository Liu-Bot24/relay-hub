# 发给 AI 编程工具的安装提示

把下面整段直接发给当前 AI 编程工具：

```text
这是 Relay Hub 的 Windows 分支安装任务。

你先只做两件事：
1. 确认当前安装源是可验证的 `main-Windows` git 副本
2. 只执行宿主侧共享安装和当前宿主自举

安装源规则：

- 如果本机还没有这个仓库的 git 副本，执行：
  git clone -b main-Windows https://github.com/Liu-Bot24/relay-hub.git
  cd relay-hub
- 如果本机已经有这个仓库的 git 副本，先进入那份仓库根目录，再执行：
  git fetch origin
  git switch main-Windows
- 如果当前目录不是 git 副本，或无法确认当前分支就是 `main-Windows`，就停止并告诉用户：
  “当前安装源不可验证；不要在 zip、解压目录或来源不明的本地副本上继续安装。”

然后阅读：
1. README.md
2. RELAY_PROTOCOL.md
3. docs/INTEGRATION_CONTRACT.md
4. docs/GENERIC_HOST_BOOTSTRAP.md
5. docs/AGENT_ENTRY_RULE.md

如果当前宿主刚好有对应示例文件，只把它当参考，不要把示例当产品定义：
- Codex：docs/HOST_EXAMPLES/codex.AGENTS.example.md
- Claude Code：docs/HOST_EXAMPLES/claude-code.CLAUDE.example.md
- Gemini CLI：docs/HOST_EXAMPLES/gemini-cli.GEMINI.example.md
- Cursor CLI：docs/HOST_EXAMPLES/cursor-cli.relay-hub.example.mdc

重要边界：

- 你当前是 AI 宿主；只执行 `py -3 install.py install-host ...`
- 不要执行 `install-openclaw`
- 不要使用 `full`
- 不要删除、reset、重装或清空 OpenClaw 侧已有 relay-hub 产物
- 不要动别的 AI 宿主产物，除非用户明确要求
- 不要把 zip、解压目录或无法验证分支的本地副本当成安装源

直接执行：
- `py -3 install.py install-host --load-services`

如果仓库里已经提供了与你当前宿主匹配的可选 adapter，且用户明确同意启用它，再追加对应参数；否则保持通用宿主路径，并按 `docs/GENERIC_HOST_BOOTSTRAP.md` 自己补齐最后一步宿主自举。

安装后再执行：
1. `py -3 install.py status`
2. `py -3 install.py doctor`

汇报时必须分成 3 段：
1. 共享安装状态
2. 当前宿主自举状态
3. 当前主对话 Relay 开启状态

判断标准：

- 共享安装完成：
  - `install-host` 成功
  - `status` 能看到 runtime / app / 宿主 Web 托管等共享产物
- 当前宿主自举完成：
  - 当前宿主已经把长期规则、`agent_id`、`main_session_ref` 规则、pickup 启动链路、自动精确镜像机制真正落下并验证
- 当前主对话 Relay 开启状态：
  - 只有用户在这条主对话明确说了 `接入 Relay Hub`，才算“已开启”
  - 如果用户还没说，就明确写“当前主对话尚未开启 Relay Hub”

额外规则：

- 如果当前机器还没有 OpenClaw，`doctor` 可能因为 `openclaw_cli` 缺失而不是 `ok=true`；这时应明确报告“当前只完成了宿主侧共享安装”，不要把它误报成宿主侧安装失败
- 安装阶段不要偷跑真实业务对话，不要为了“验证 backend”而擅自开启当前主对话的 Relay
- 自动精确镜像必须是真正持久的自动机制；人工补跑 `capture-main-output` 不算完成
- 通用默认的 merge-back 方式是：用户显式说 `合流上下文`
- 只有当前宿主确实已经落下可靠的前置 hook / pre-user 机制时，才允许把“回主窗口自动先合流”报告为已完成
- 如果你新增了 transcript / payload extractor，必须用“前一条 assistant 文本”和“最后一条 assistant 文本”不同的最小夹具验证它真的抓到最后一条，再报告完成
- 当用户后续说 `接入 Relay Hub` 时，不要先裸跑 `enable-relay`；第一次调用就带完整参数，并统一使用 `enable-relay --start-pickup`
```
