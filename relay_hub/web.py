from __future__ import annotations

import html
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from .store import RelayHub, session_key_from_public_token, session_public_token


HTML_STYLE = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #111827; background: #f8fafc; }
a { color: #1d4ed8; text-decoration: none; }
a:hover { text-decoration: underline; }
.page { max-width: 1100px; margin: 0 auto; }
.card { background: white; border: 1px solid #e5e7eb; border-radius: 16px; padding: 18px 20px; margin: 16px 0; box-shadow: 0 8px 30px rgba(15, 23, 42, 0.05); }
.muted { color: #6b7280; }
.pill { display: inline-block; padding: 4px 10px; border-radius: 999px; background: #eff6ff; color: #1d4ed8; font-size: 12px; margin-right: 8px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.msg { border-left: 4px solid #cbd5e1; padding-left: 12px; margin: 18px 0; }
.msg.user { border-left-color: #2563eb; }
.msg.progress { border-left-color: #d97706; }
.msg.final { border-left-color: #059669; }
.msg.error { border-left-color: #dc2626; }
textarea { width: 100%; min-height: 180px; font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; border: 1px solid #cbd5e1; border-radius: 12px; padding: 14px; box-sizing: border-box; }
button { background: #111827; color: white; border: 0; padding: 11px 16px; border-radius: 10px; cursor: pointer; }
pre { white-space: pre-wrap; word-break: break-word; background: #f8fafc; border-radius: 12px; padding: 14px; border: 1px solid #e5e7eb; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
"""


def html_page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>{HTML_STYLE}</style>
</head>
<body>
  <div class="page">
    {body}
  </div>
</body>
</html>
""".encode("utf-8")


def escape(text: str | None) -> str:
    return html.escape(text or "")


def development_log_notice(development_log: dict[str, object]) -> str:
    if not (development_log.get("attached") and development_log.get("readable") is False):
        return ""
    path = str(development_log.get("path") or "")
    error = str(development_log.get("error") or "")
    try:
        resolved = Path(path).expanduser().resolve()
        home = Path.home().resolve()
        desktop = (home / "Desktop").resolve()
        documents = (home / "Documents").resolve()
        desktop_hit = desktop == resolved or desktop in resolved.parents
        documents_hit = documents == resolved or documents in resolved.parents
    except Exception:
        desktop_hit = False
        documents_hit = False
    if desktop_hit or documents_hit:
        reason = "这份开发日志位于 macOS 受保护目录（桌面或文稿）里；Relay Hub 的常驻 Web 服务由 launchd 在后台运行，通常没有读取这类目录的权限。"
    else:
        reason = "当前常驻 Web 服务暂时没有权限读取这份开发日志。"
    fix = "解决办法：把项目或开发日志移到非受保护目录继续使用，或者给运行 Relay Hub Web 服务的宿主进程授予相应文件访问权限。"
    return (
        f'<div class="muted" style="margin-top: 10px;">'
        f'{escape(reason)}<br>{escape(fix)}<br>'
        f'{escape("当前错误：")}<code>{escape(error)}</code>'
        f'</div>'
    )


def session_url(session_key: str, notice: str | None = None) -> str:
    path = f"/s/{session_public_token(session_key)}"
    if not notice:
        return path
    return f"{path}?{urlencode({'notice': notice})}"


def render_index(hub: RelayHub) -> bytes:
    sessions = hub.list_sessions()
    cards = []
    for session in sessions:
        cards.append(
            f"""
            <div class="card">
              <div><a href="{escape(session_url(session['session_key']))}"><strong>{escape(session['session_key'])}</strong></a></div>
              <div class="muted">agent={escape(session.get('agent'))} channel={escape(session.get('channel'))} target={escape(session.get('target'))}</div>
              <div style="margin-top: 8px;">
                <span class="pill">{escape(session.get('status'))}</span>
                <span class="pill">{escape(session.get('mode'))}</span>
                <span class="muted">{session.get('message_count', 0)} messages</span>
              </div>
            </div>
            """
        )
    if not cards:
        cards.append(
            """
            <div class="card">
              <strong>还没有 session。</strong>
              <div class="muted" style="margin-top: 8px;">先用 relayctl 打开一个 session，再回来这里浏览和录入。</div>
            </div>
            """
        )
    body = f"""
    <h1>Relay Hub</h1>
    <p class="muted">这里是本地网页入口。它负责浏览会话和写入用户消息，不直接给渠道发消息。</p>
    {''.join(cards)}
    """
    return html_page("Relay Hub", body)


def render_session(hub: RelayHub, session_key: str, notice: str | None = None) -> bytes:
    bundle = hub.get_session(session_key)
    meta = bundle["meta"]
    state = bundle["state"]
    main_context = bundle.get("main_context") or {}
    development_log = bundle.get("development_log") or {}
    if not meta:
        return html_page("Session Not Found", f"<h1>Session 不存在</h1><p><code>{escape(session_key)}</code></p>")
    messages_html = []
    for message in reversed(bundle["messages"]):
        role = message["meta"].get("role", "unknown")
        kind = message["meta"].get("kind", role)
        css_class = role if role == "user" else kind
        messages_html.append(
            f"""
            <div class="msg {escape(css_class)}">
              <div><strong>{escape(kind)}</strong> <span class="muted">id={escape(str(message['meta'].get('id')))} agent={escape(message['meta'].get('agent'))}</span></div>
              <div class="muted" style="margin: 6px 0 10px;">created_at={escape(message['meta'].get('created_at'))}</div>
              <pre>{escape(message['body'])}</pre>
            </div>
            """
        )
    notice_html = f'<div class="card"><strong>{escape(notice)}</strong></div>' if notice else ""
    relay_open = state.get("mode") == "relay"
    entry_open = relay_open and state.get("status") == "entry_open"
    write_panel = (
        f"""
        <div class="card">
          <strong>写入新消息</strong>
          <div class="muted" style="margin: 8px 0 10px;">{escape('branch 会在你第一次保存网页消息时正式开始。' if entry_open else '当前 branch 已开始；继续在这里写入后续网页消息。')}</div>
          <form method="post" action="{escape(session_url(session_key))}/commit" style="margin-top: 12px;" onsubmit="const btn=this.querySelector('button'); btn.disabled=true; btn.textContent='正在保存...';">
            <textarea name="body" placeholder="在这里写入本轮输入内容。"></textarea>
            <div style="margin-top: 12px;">
              <button type="submit">保存为 committed 用户消息</button>
            </div>
          </form>
        </div>
        """
        if relay_open
        else """
        <div class="card">
          <strong>写入新消息</strong>
          <div class="muted" style="margin-top: 10px;">当前 branch 已关闭。请回到 OpenClaw 重新执行“打开 &lt;agent&gt; 入口”后，再继续在这里录入。</div>
        </div>
        """
    )
    body = f"""
    <div style="margin-bottom: 18px;"><a href="/">返回全部 session</a></div>
    <h1>{escape(session_key)}</h1>
    <p class="muted">网页入口是主对话窗口派生出来的分支工作区。链接发出时只是入口打开；用户第一次保存网页消息时，branch 才正式开始。真正的“已录入”与对外发送，仍然应该由 OpenClaw 或 relayctl 触发。</p>
    {notice_html}
    <div class="grid">
      <div class="card">
        <strong>Meta</strong>
        <pre>{escape(str(meta))}</pre>
      </div>
      <div class="card">
        <strong>State</strong>
        <pre>{escape(str(state))}</pre>
      </div>
    </div>
    <div class="card">
      <strong>主对话快照</strong>
      <div class="muted" style="margin: 8px 0 10px;">branch 不是主对话本身；这里显示的是它继承下来的主线快照。</div>
      <pre>{escape(main_context.get('body') or '当前还没有记录主对话快照。')}</pre>
    </div>
    <div class="card">
      <strong>开发日志参考</strong>
      <div class="muted" style="margin: 8px 0 10px;">从入口打开到 branch 开始之间，以及 branch 期间的重要上下文，应优先由项目开发日志托底。</div>
      <pre>{escape(development_log.get('path') or '当前还没有附加开发日志。')}</pre>
      {development_log_notice(development_log)}
    </div>
    {write_panel}
    <div class="card">
      <strong>消息历史</strong>
      {''.join(messages_html) if messages_html else '<p class="muted">还没有消息。</p>'}
    </div>
    """
    return html_page(session_key, body)


def create_handler(root: Path):
    def resolve_session_key_from_path(path: str) -> str | None:
        if path.startswith("/s/"):
            token = unquote(path.removeprefix("/s/"))
            if not token:
                return None
            try:
                return session_key_from_public_token(token)
            except Exception:
                return None
        if path.startswith("/session/"):
            return unquote(path.removeprefix("/session/"))
        return None

    class RelayHandler(BaseHTTPRequestHandler):
        def _hub(self) -> RelayHub:
            return RelayHub(root)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                payload = render_index(self._hub())
                self._send(HTTPStatus.OK, payload)
                return
            if (parsed.path.startswith("/s/") or parsed.path.startswith("/session/")) and parsed.path.endswith("/commit"):
                target_path = parsed.path.removesuffix("/commit").rstrip("/")
                session_key = resolve_session_key_from_path(target_path)
                self._redirect(session_url(session_key) if session_key else "/")
                return
            if parsed.path.startswith("/s/") or parsed.path.startswith("/session/"):
                session_key = resolve_session_key_from_path(parsed.path)
                if not session_key:
                    self._send(HTTPStatus.NOT_FOUND, html_page("Not Found", "<h1>404</h1>"))
                    return
                notice = parse_qs(parsed.query).get("notice", [None])[0]
                payload = render_session(self._hub(), session_key, notice=notice)
                self._send(HTTPStatus.OK, payload)
                return
            self._send(HTTPStatus.NOT_FOUND, html_page("Not Found", "<h1>404</h1>"))

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if (not parsed.path.startswith("/s/") and not parsed.path.startswith("/session/")) or not parsed.path.endswith("/commit"):
                self._send(HTTPStatus.NOT_FOUND, html_page("Not Found", "<h1>404</h1>"))
                return
            session_key = resolve_session_key_from_path(parsed.path.removesuffix("/commit"))
            if not session_key:
                self._send(HTTPStatus.NOT_FOUND, html_page("Not Found", "<h1>404</h1>"))
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            form = parse_qs(raw_body)
            body = (form.get("body") or [""])[0].strip()
            if not body:
                self._redirect(session_url(session_key, "内容为空，未写入"))
                return
            try:
                self._hub().commit_user_message(session_key, body)
            except (FileNotFoundError, ValueError) as exc:
                self._redirect(session_url(session_key, str(exc)))
                return
            self._redirect(session_url(session_key, "已写入一条 committed 用户消息"))

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _redirect(self, location: str) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            self.end_headers()

        def _send(self, status: HTTPStatus, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return RelayHandler


def serve(root: Path, host: str = "127.0.0.1", port: int = 4317) -> None:
    server = ThreadingHTTPServer((host, port), create_handler(root))
    print(f"Relay Hub web listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
