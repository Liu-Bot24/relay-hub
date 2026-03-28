from __future__ import annotations

DELIVERY_DIVIDER = "--------------------"


def command_guide(agent: str | None) -> str:
    return f"常用指令：打开 {agent or '<agent>'} 入口 / 已录入 / 状态 / 退出 / relay help"


def relay_help_text(agent: str | None) -> str:
    resolved = agent or "<agent>"
    return "\n".join(
        [
            "Relay Hub 命令大全",
            "",
            "在编程工具主窗口：",
            f"- 接入 Relay Hub：把当前主对话接入 Relay Hub，并启动持续接单/镜像",
            f"- Relay Hub 状态：查看当前主对话是否 ready、是否有待处理 branch、是否有未合流旧 branch",
            "- 消息提醒状态：查看当前所有 OpenClaw 消息渠道的提醒开关状态",
            "- 开启<渠道>消息提醒：开启某一个 OpenClaw 消息渠道的提醒",
            "- 关闭<渠道>消息提醒：关闭某一个 OpenClaw 消息渠道的提醒",
            f"- 合流上下文：把当前主会话下尚未合流的旧 branch 增量接回主窗口",
            f"- 退出 Relay Hub：关闭当前主对话的 Relay Hub",
            "",
            "在 OpenClaw：",
            f"- 打开 {resolved} 入口：打开网页入口；如已有旧 branch，会先询问复用还是新建",
            "- 已录入：把网页里刚保存的输入正式入队",
            "- 状态：查看当前入口 / branch 状态",
            "- 退出：退出当前 relay branch",
            "- relay help：查看这份命令大全",
            "- 复用入口 / 新建入口：在 OpenClaw 追问时，明确选择继续旧 branch 还是创建新 branch",
        ]
    )


def delivery_footer(web_url: str, agent: str | None) -> str:
    return "\n".join(
        [
            DELIVERY_DIVIDER,
            f"网页入口：{web_url}",
            command_guide(agent),
        ]
    )
