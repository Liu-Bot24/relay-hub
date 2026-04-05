# 宿主示例文件

这些文件不是产品主路径，也不是验收标准来源。

它们只在下面这种场景使用：

- 当前宿主刚好命中一个现有示例
- 你需要参考这个宿主的文件路径、配置格式或 hook 载体写法

真正的产品语义、完成标准和验收口径，始终以：

- [docs/GENERIC_HOST_BOOTSTRAP.md](/D:/work/Claude%20Code/relay-hub/docs/GENERIC_HOST_BOOTSTRAP.md)

为准。

当前这 4 份示例都已经收成 Windows 安全版：

- Codex（可选宿主增强）：`docs/HOST_EXAMPLES/codex.AGENTS.example.md`
- Claude Code：`docs/HOST_EXAMPLES/claude-code.CLAUDE.example.md`
- Gemini CLI：`docs/HOST_EXAMPLES/gemini-cli.GEMINI.example.md`
- Cursor CLI：`docs/HOST_EXAMPLES/cursor-cli.relay-hub.example.mdc`

使用时仍然要遵守这 4 条：

1. 示例不是产品定义
2. 示例里的 backend / hook / transcript 规则，只有在当前宿主版本已经真实验证过时，才允许写成已完成
3. 通用默认的 merge-back 方式仍然是用户显式说 `合流上下文`
4. 所有最终发给用户的正文与被镜像出去的正文必须是同一份文本
