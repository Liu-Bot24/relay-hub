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
- `scripts/relayctl.py`

### 仓库自带的后台 worker

当前不完全通用。

现成打包好的“自动轮询并处理队列”的后台 worker，目前只附带了：

- `Claude Code`

对应脚本是：

- `scripts/relay_agent_worker.py`

当前这个 worker 后端只实现了 `claude-code`。  
所以结论是：

- `Claude Code`：协议层可用，现成自动 worker 也可用
- `Codex / Gemini CLI / Cursor CLI / Opencode`：协议层可用，但默认没有内置后台 worker

这不代表它们不能接入，只代表：

- 可以通过 `scripts/agent_relay.py` 手动参与
- 或者自己再加一层很薄的专属 worker

## 2. 消息渠道通用性

### 是否只支持飞书 / 微信

不是。

真正的边界是：

- 只要该渠道是 `OpenClaw` 已支持、并且能通过 `openclaw message send` 发出的消息渠道，就可以接

也就是说，协议层不是写死飞书 / 微信。  
飞书 / 微信只是当前仓库里最先验证过、并且安装器提供了快捷参数的例子。

### 为什么 README 里总出现飞书 / 微信

因为安装器提供了这两个快捷参数：

- `--feishu-target`
- `--weixin-target`
- `--weixin-account-id`

但这只是快捷写法，不是能力边界。

真正通用的写法是：

- `--delivery-channel channel=target`
- `--delivery-account channel=accountId`

例如：

```bash
python3 install.py full \
  --web-base-url http://YOUR_LAN_IP:4317 \
  --delivery-channel some-channel=target_id \
  --worker-agent claude-code \
  --worker-backend claude-code \
  --load-services
```

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
- 对 `Claude Code` 提供了现成后台 worker

Relay Hub 现在还不是：

- 对所有 AI CLI 都内置现成自动 worker
- 对所有操作系统都内置现成服务托管
- 对所有消息网关都通用

如果你只关心“拿给 Claude Code 和 OpenClaw 能不能自己部署并进入可用状态”，答案是：

- 可以

如果你关心“是不是已经对所有 AI CLI 和所有消息系统都零改动通用”，答案是：

- 还没有
