# 宿主示例文件

这些文件不是产品主路径，只是给常见宿主一个“最小可抄”的落地参考。

真正的安装完成标准，仍然只看：

- `docs/GENERIC_HOST_BOOTSTRAP.md`

当当前宿主正好是下面 4 个时，可优先参考对应示例：

- Codex（可选宿主增强）: `docs/HOST_EXAMPLES/codex.AGENTS.example.md`
- Claude Code: `docs/HOST_EXAMPLES/claude-code.CLAUDE.example.md`
- Gemini CLI: `docs/HOST_EXAMPLES/gemini-cli.GEMINI.example.md`
- Cursor CLI: `docs/HOST_EXAMPLES/cursor-cli.relay-hub.example.mdc`

这几份示例都遵守同一个原则：

1. 优先使用宿主原生 hook / watcher
2. 如果没有现成 after-reply hook，但宿主持久规则能在回复收尾阶段自动执行本地命令，也允许把“写 exact body 文件 -> 调 `relay_after_reply_hook.py` -> 发送同一份正文”作为自动镜像机制
3. 只有用户每轮都要提醒你补跑命令，才算手动补跑
4. branch 合流默认仍然走产品命令 `合流上下文`；只有宿主确实支持可靠的前置 hook / pre-prompt 机制时，才把自动合流当成可选增强
