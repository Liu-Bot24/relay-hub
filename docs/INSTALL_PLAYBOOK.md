# Relay Hub 安装章程

这份文件只讲 Windows 分支的安装主路径，不讲协议细节。

## 1. 安装源

Windows 分支只接受**可验证的 `main-Windows` git 副本**。

新 clone：

```powershell
git clone -b main-Windows https://github.com/Liu-Bot24/relay-hub.git
cd relay-hub
```

已有 git 副本：

```powershell
git fetch origin
git switch main-Windows
```

硬规则：

- 不要在 zip、解压目录或来源不明的本地副本上继续安装
- 不要因为“桌面目录不是 git clone”就额外再下载一份
- 不要把仓库 clone 到 `%TEMP%`、`%LOCALAPPDATA%\Temp` 或其他临时/缓存目录
- 如果当前目录不是 git 副本，或无法确认当前分支是 `main-Windows`，就停止并告诉用户当前安装源不可验证

## 2. 宿主侧共享安装

这一步只由 AI 宿主执行。

```powershell
py -3 install.py install-host --load-services
```

安装后检查：

```powershell
py -3 install.py status
py -3 install.py doctor
```

判断标准：

- `status` 只用于确认共享安装产物
- 如果当前机器还没有 OpenClaw，`doctor` 可能因为 `openclaw_cli` 缺失而不是 `ok=true`
- 这时只能说明“OpenClaw 侧尚未具备”，不等于宿主侧共享安装失败

## 3. OpenClaw 侧安装

这一步只由 OpenClaw 执行，而且必须在共享层已经存在之后再做。

```powershell
py -3 install.py install-openclaw
```

如果需要覆盖自动发现的默认提醒渠道，再显式传参：

```powershell
py -3 install.py install-openclaw --delivery-channel <channel>=<target> --delivery-account <channel>=<accountId>
```

硬规则：

- 不要由 AI 宿主代跑 `install-openclaw`
- 不要由 OpenClaw 代跑 `install-host`
- 不要使用 `full` 作为默认委托路径
- 如果 `install-openclaw` 报“请先执行 install-host”，就直接停下并回报，不要跨侧代装

## 4. 推荐把哪份提示发给谁

- 发给 AI 编程工具：使用 [docs/AI_INSTALL_PROMPT.md](/D:/work/Claude%20Code/relay-hub/docs/AI_INSTALL_PROMPT.md)
- 发给 OpenClaw：使用 [docs/OPENCLAW_INSTALL_PROMPT.md](/D:/work/Claude%20Code/relay-hub/docs/OPENCLAW_INSTALL_PROMPT.md)

这两份提示就是主入口。  
不要再从这里手工抽一段旧话术拼成另一版 prompt。

## 5. 安装完成时怎么判断

当前分支统一按下面 4 层判断：

1. **宿主侧共享安装完成**
   - `install-host` 成功
   - `status` 能看到共享产物
2. **当前宿主自举完成**
   - 由安装它的 AI 按 [docs/GENERIC_HOST_BOOTSTRAP.md](/D:/work/Claude%20Code/relay-hub/docs/GENERIC_HOST_BOOTSTRAP.md) 判断
3. **OpenClaw 侧接入完成**
   - `install-openclaw` 成功
   - OpenClaw bridge / skill / heartbeat block 已安装
4. **当前主对话已开启 Relay Hub**
   - 只有用户在当前主对话明确说了 `接入 Relay Hub`，这一步才成立

不要混淆这些状态：

- “当前主对话尚未开启 Relay Hub”不等于“宿主未完整接入”
- “当前机器还没有 OpenClaw”不等于“宿主侧共享安装失败”
- “OpenClaw 侧已安装”也不等于“真实消息渠道端到端已经实机验证完成”

## 6. 不要做什么

- 不要在未验证分支来源的目录里继续安装
- 不要让宿主 AI 去执行 `install-openclaw`
- 不要让 OpenClaw 去执行 `install-host`
- 不要把 README / prompt / 示例里的宿主示例文件当成产品定义
- 不要把“消息命令能返回”写成“端到端已验证”
- 不要擅自删除、reset、卸载、重建另一侧已有 relay-hub 产物
