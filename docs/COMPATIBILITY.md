# Relay Hub 通用性审计

这份文件明确说明：什么地方是通用的，什么地方还不是。

## 1. AI 编程工具通用性

### 协议层

支持通用。

只要一个对象满足下面 3 个条件，就可以接入：

1. 能执行本地命令
2. 能长期保留一小段最小规则
3. 能读写普通文件

所以在协议层，下面这些都可以接：

- `Codex`
- `Claude Code`
- `Gemini CLI`
- `Cursor CLI`
- `Opencode`
- 其他同类对象

它们共用的是：

- `RELAY_PROTOCOL.md`
- `docs/AGENT_ENTRY_RULE.md`
- `docs/AGENT_WORKFLOW.md`
- `scripts/agent_relay.py`
- `scripts/relay_agent_daemon.py`
- `scripts/relayctl.py`

### 默认安装会不会替 AI 自动补最后一步

当前不完全自动。

当前仓库的产品边界是：

- AI 宿主默认执行 `install-host`
- OpenClaw 默认执行 `install-openclaw`
- 外部 AI 再借助通用轮子把自己的宿主接入补齐
- 仓库可以附带少量宿主 adapter，但它们不是产品主路径

所以结论是：

- 协议层对任意稳定宿主标识都开放
- 仓库默认不会在产品主路径里假定某个特定宿主享有特殊地位
- 如果仓库里附带了个别宿主的可选 adapter 或优化 backend，它们只能作为下层实现细节显式启用，不能改变产品主路径

这不代表其他宿主不能接入，只代表：

- 应优先复用 `scripts/agent_relay.py`、`scripts/relay_agent_daemon.py` 这些通用轮子完成接入
- 若某个宿主当前还需要额外补钩子或自动化，属于该宿主接入尚未补齐，不是产品价值观本身

对“主窗口回复如何精确镜像到 OpenClaw”这件事，当前仓库提供的是两层：

- 通用主路径：精确正文捕获队列，先把已经产出的最终正文写入文件，再执行 `scripts/agent_relay.py capture-main-output --body-file ...`
- 可选优化路径：仓库内允许存在个别宿主的原生正文捕获实现，但它们只是附加优化，不代表产品主路径

更准确地说：

- 能在自己的环境里建立持续接单机制，才算接入完成
- 如果某个宿主当前还只能手动参与，说明该宿主接入未完成，不是产品目标状态

仓库当前提供的是：

- 一个通用控制入口：`scripts/agent_relay.py`
- 一个通用持续接单守护轮子：`scripts/relay_agent_daemon.py`
- 多种 backend 接法，其中 `command` 是面向任意 CLI 的通用方式；仓库里如果存在其他内置 backend，也只应视作可选实现细节

### 宿主与 OpenClaw 的边界

- AI 宿主负责共享安装层的正常安装/升级，以及自己宿主侧的长期机制
- OpenClaw 负责自己的渠道网关动作和 OpenClaw 侧 relay-hub 产物
- OpenClaw 侧安装不负责补装共享层；共享层缺失时应要求先执行 `install-host`
- 默认只允许原地更新，不允许任何一侧擅自删除、reset、重装或清空另一侧已有产物
- 任何跨侧清理或破坏性重装，都必须先得到用户明确授权

## 2. 消息渠道通用性

### 是否只支持少数预设渠道

不是。

真正的边界是：

- 只要该渠道是 `OpenClaw` 已支持、并且能通过 `openclaw message send` 发出的消息渠道，就可以接

也就是说，协议层不是写死某几个渠道。

真正通用的安装写法是：

- `--delivery-channel channel=target`
- `--delivery-account channel=accountId`

例如：

```bash
python3 install.py install-openclaw \
  --delivery-channel some-channel=target_id \
```

这些默认提醒渠道不会替代当前来源渠道：

- branch 回包仍保留原始触发渠道
- 主窗口提醒优先复用当前主会话已绑定的来源渠道；首次从宿主主窗口开启时，若还没有绑定来源对象，就默认发送到所有已启用的 OpenClaw 渠道

### 当前渠道层真正的边界

- 支持：`OpenClaw` 已支持的消息渠道
- 不支持：绕过 `OpenClaw` 直接读写原始渠道
- 不支持：没有 `OpenClaw` 的独立网关模式

换句话说，Relay Hub 的消息网关是：

- 通用到“任意 OpenClaw 渠道”
- 不通用到“任意非 OpenClaw 渠道系统”

## 3. 平台通用性

### 协议和脚本本身

大体是通用的：

- Python 脚本
- 普通文件目录
- 普通命令调用

### 一键安装与后台托管

当前不完全通用。

现在现成打包的是：

- `macOS`
- `launchd`

所以：

- 在 macOS 上，仓库可以直接进入“安装后可用”的状态
- 在其他系统上，协议和脚本仍可复用，但后台服务托管需要重新适配

## 4. OpenClaw 通用性

OpenClaw 这一层的职责是固定的：

- 打开入口
- 收“已录入”
- 查状态
- 退出 relay
- 渠道外发回包

这一层不是模型绑定的，也不是工具绑定的。  
但它是：

- 明确绑定 `OpenClaw` 的

所以结论是：

- 支持：任意 OpenClaw 实例接入
- 不支持：把 OpenClaw 替换成别的网关却完全不改桥接层

## 5. 主线 / branch 语义通用性

这部分是通用且明确的：

- AI 主对话窗口是主线
- 网页 / md 是 branch
- OpenClaw 不是主记忆体
- branch 结束后需要 merge-back 回主线

这套心智模型不依赖某个具体模型或渠道。

## 6. 当前最准确的总结

Relay Hub 现在是：

- 对 AI 协议层通用
- 对 OpenClaw 渠道层通用
- 对 macOS 安装与托管友好

Relay Hub 现在还不是：

- 对所有 AI CLI 都内置统一现成的自动接单进程
- 对所有操作系统都内置现成服务托管
- 对所有消息网关都通用

如果你只关心“拿给某个 AI 编程工具和 OpenClaw 能不能自己部署并进入可用状态”，答案是：

- 可以

如果你关心“是不是已经对所有 AI CLI 和所有消息系统都零改动通用”，答案是：

- 还没有
