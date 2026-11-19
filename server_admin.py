"""HTTPS administration panel for the file service."""

import hmac
import html
import json
import logging
import secrets
import ssl
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit

from admin_service import AdminError
from replication import parse_peers

MAX_FORM_BYTES = 1024 * 1024


class AdminSessions:
    """Server-side admin sessions with CSRF tokens and expiry."""

    def __init__(self, timeout):
        self.timeout = float(timeout)
        self._sessions = {}
        self._lock = threading.RLock()

    def create(self, username):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = {
                "username": username,
                "csrf": csrf,
                "expires": time.monotonic() + self.timeout,
            }
        return token, csrf

    def get(self, token):
        if not token:
            return None
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if session["expires"] < time.monotonic():
                del self._sessions[token]
                return None
            return dict(session)

    def remove(self, token):
        with self._lock:
            self._sessions.pop(token, None)


class AdminServer:
    """Threading HTTPS server exposing the admin panel."""

    def __init__(self, config, admin_service, cluster):
        self.config = config
        self.admin_service = admin_service
        self.cluster = cluster
        self.sessions = AdminSessions(config.admin_session_timeout)
        self.httpd = None
        self.port = None
        self._thread = None
        self._admin_addresses = {
            peer.server_id: (peer.host, peer.port)
            for peer in parse_peers(config.admin_addresses)
        }

    def start(self):
        server = ThreadingHTTPServer(
            (self.config.admin_host, self.config.admin_port), AdminHandler
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(
            self.config.tls_cert_file, self.config.tls_key_file
        )
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.daemon_threads = True
        server.admin_service = self.admin_service
        server.sessions = self.sessions
        server.config = self.config
        server.admin_portal = self
        self.httpd = server
        self.port = server.server_address[1]
        self._thread = threading.Thread(
            target=server.serve_forever, name="admin-http", daemon=True
        )
        self._thread.start()

    def base_url(self):
        host = self.config.admin_host
        if host in {"", "0.0.0.0", "::"}:
            host = "localhost"
        return "https://{}:{}/".format(host, self.port)

    def primary_url(self):
        leader = self.cluster.current_leader
        if leader is None:
            return None
        if leader == self.config.server_id:
            return self.base_url()
        location = self._admin_addresses.get(leader)
        if location is None:
            return None
        return "https://{}:{}/".format(location[0], location[1])

    def stop(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None


logger = logging.getLogger(__name__)


class AdminHandler(BaseHTTPRequestHandler):
    """Request router for the admin panel."""

    server_version = "CloudFileService/1.0"

    def log_message(self, format, *args):
        logger.info("admin %s", format % args)

    @property
    def service(self):
        return self.server.admin_service

    @property
    def config(self):
        return self.server.config

    @property
    def portal(self):
        return self.server.admin_portal

    def _cookie_token(self):
        raw = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            return None
        morsel = cookie.get("cloudfs_admin")
        return morsel.value if morsel is not None else None

    def _session(self):
        return self.server.sessions.get(self._cookie_token())

    def _send(self, body, status=HTTPStatus.OK, content_type="text/html; charset=utf-8", headers=None):
        encoded = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect(self, location, status=HTTPStatus.SEE_OTHER, headers=None):
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _read_form(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > MAX_FORM_BYTES:
            raise ValueError("Form is too large.")
        body = self.rfile.read(length) if length else b""
        return parse_qs(body.decode("utf-8"), keep_blank_values=True)

    def _form_value(self, form, key, default=""):
        values = form.get(key)
        return values[0] if values else default

    def _page(self, title, body, session=None):
        nav = ""
        if session is not None:
            nav = """
            <aside class="sidebar">
              <a href="/"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="icon"><path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>Status</a>
              <a href="/users"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="icon"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>Users</a>
              <a href="/shares"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="icon"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8M16 6l-4-4-4 4M12 2v13"/></svg>Shares</a>
              <a href="/settings"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="icon"><path d="M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>Settings</a>
              <form method="post" action="/logout">
                <input type="hidden" name="csrf" value="{csrf}">
                <button type="submit" class="secondary"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="icon"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/></svg>Sign out</button>
              </form>
            </aside>
            """.format(csrf=html.escape(session["csrf"]))
        return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --ehu-blue: #1565C0;
  --ehu-blue-dark: #2E5AAC;
  --ehu-green: #5FD790;
  --ehu-green-dark: #3B8719;
  --ehu-dark: #212121;
  --ehu-cream: #F5F5F0;
  --ehu-danger: #E42719;
  --ehu-warning: #C75200;
  --ehu-gray: #6B6C7E;
  --ehu-gray-light: #CDCED9;
  --bg: var(--ehu-cream);
  --fg: var(--ehu-dark);
  --card: #ffffff;
  --border: var(--ehu-gray-light);
  --radius: 10px;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1a1b22;
    --fg: #e7e7ed;
    --card: #272833;
    --border: #393a4a;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ font-family: "EHUSans", system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; background: var(--bg); color: var(--fg); line-height: 1.5; }}
header {{ background: var(--ehu-blue); color: #fff; padding: 16px 24px; display: flex; align-items: center; gap: 14px; }}
header svg {{ height: 34px; width: auto; }}
header h1 {{ margin: 0; font-size: 20px; font-weight: 600; }}
header .subtitle {{ opacity: 0.85; font-size: 13px; margin-left: 4px; }}
nav {{ background: var(--card); padding: 10px 24px; border-bottom: 1px solid var(--border); display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }}
nav a, nav button {{ margin-right: 6px; color: var(--ehu-blue); text-decoration: none; padding: 6px 10px; border-radius: 6px; font-size: 14px; }}
nav a:hover, nav button:hover {{ background: rgba(21,101,192,0.08); }}
form.inline {{ display: inline; }}
.layout {{ display: flex; gap: 24px; max-width: 1180px; margin: 24px auto; padding: 0 20px; }}
.sidebar {{ width: 200px; flex-shrink: 0; display: flex; flex-direction: column; gap: 4px; padding: 12px; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); height: fit-content; position: sticky; top: 16px; }}
.sidebar a, .sidebar button {{ display: block; padding: 8px 12px; border-radius: 6px; color: var(--fg); text-decoration: none; font-size: 14px; background: transparent; border: none; text-align: left; cursor: pointer; width: 100%; }}
.sidebar a:hover, .sidebar button:hover {{ background: rgba(21,101,192,0.08); color: var(--ehu-blue); }}
.sidebar form {{ margin: 0; }}
.sidebar svg.icon {{ width: 16px; height: 16px; margin-right: 8px; vertical-align: -3px; }}
main {{ flex: 1; min-width: 0; }}
@media (max-width: 720px) {{
  .layout {{ flex-direction: column; }}
  .sidebar {{ width: 100%; position: static; flex-direction: row; flex-wrap: wrap; }}
  .sidebar a, .sidebar button {{ width: auto; }}
}}
.card {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 18px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }}
.card h2 {{ margin: 0 0 12px; font-size: 18px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 14px; }}
th {{ font-weight: 600; color: var(--ehu-gray); text-transform: uppercase; font-size: 12px; letter-spacing: 0.04em; }}
tbody tr:hover {{ background: rgba(21,101,192,0.04); }}
input, button, select, textarea {{ padding: 8px 10px; margin: 4px 0; font: inherit; border: 1px solid var(--border); border-radius: 6px; background: var(--card); color: var(--fg); }}
input:focus, select:focus, textarea:focus {{ outline: 2px solid var(--ehu-blue); outline-offset: 1px; border-color: var(--ehu-blue); }}
button {{ cursor: pointer; background: var(--ehu-blue); color: #fff; border: none; font-weight: 600; }}
button.secondary {{ background: transparent; color: var(--ehu-blue); border: 1px solid var(--border); }}
.error {{ color: var(--ehu-danger); font-weight: 600; }}
.notice {{ background: #fff5d6; border: 1px solid #e6c65c; padding: 12px; border-radius: 6px; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
.badge-leader {{ background: var(--ehu-green); color: #1a1b22; }}
.badge-follower {{ background: var(--ehu-gray-light); color: var(--ehu-dark); }}
.badge-ro {{ background: #e7e7ed; color: var(--ehu-dark); }}
.badge-rw {{ background: var(--ehu-green); color: #1a1b22; }}
.empty {{ color: var(--ehu-gray); font-style: italic; padding: 12px 0; }}
@media (max-width: 720px) {{
  nav {{ padding: 8px 12px; }}
  main {{ margin: 12px auto; padding: 0 12px; }}
  .card {{ padding: 14px; }}
  header h1 {{ font-size: 17px; }}
}}
</style>
</head>
<body>
<header>
  <svg viewBox="0 0 362.83 362.83" xmlns="http://www.w3.org/2000/svg" aria-label="EHU">
    <g fill="#ffffff">
      <path d="M100.56,244.04h42.89v9.01h-32.46v15.6h30.04v8.51h-30.04v17.44h33.04v9.01h-43.47v-59.58h0Z"/>
      <path d="M152.88,244.04h10.43v23.7h27.12v-23.7h10.43v59.58h-10.43v-26.87h-27.12v26.87h-10.43v-59.58Z"/>
      <path d="M210.84,244.04h10.43v50.57h29.46v9.01h-39.89v-59.58Z"/>
      <path d="M260.36,244.04h43.47v9.01h-33.04v16.1h30.54v8.51h-30.54v25.96h-10.43v-59.58Z"/>
    </g>
  </svg>
  <h1>Cloud File Service <span class="subtitle">· Administration</span></h1>
</header>
<div class="layout">
  {nav}
  <main>{body}</main>
</div>
</body>
</html>""".format(title=html.escape(title), nav=nav, body=body)

    def _login_page(self, error=""):
        body = """
        <div class="card">
          <h2>Sign in</h2>
          {error}
          <form method="post" action="/login">
            <label>Username<br><input name="username" autocomplete="username"></label><br>
            <label>Password<br><input type="password" name="password" autocomplete="current-password"></label><br>
            <button type="submit">Sign in</button>
          </form>
        </div>
        """.format(
            error='<p class="error">{}</p>'.format(html.escape(error)) if error else ""
        )
        self._send(self._page("Administration", body))

    def _require_session(self):
        session = self._session()
        if session is None:
            self._redirect("/login")
            return None
        return session

    def _error_page(self, message, status=HTTPStatus.BAD_REQUEST, session=None):
        body = '<div class="card error">{}</div>'.format(html.escape(message))
        self._send(self._page("Error", body, session), status)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/login":
            self._login_page()
            return
        if path == "/healthz":
            self._send("OK", content_type="text/plain; charset=utf-8")
            return
        session = self._require_session()
        if session is None:
            return
        if path == "/":
            self._dashboard(session)
        elif path == "/users":
            self._users_page(session)
        elif path == "/shares":
            self._shares_page(session)
        elif path == "/settings":
            self._settings_page(session)
        elif path == "/api/status":
            self._json(self.service.status())
        elif path == "/api/users":
            self._json(self.service.users())
        elif path == "/api/shares":
            self._json(self.service.shares())
        else:
            self._error_page("Route not found.", HTTPStatus.NOT_FOUND, session)

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            form = self._read_form()
        except ValueError as error:
            self._error_page(str(error), HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        if path == "/login":
            self._login(form)
            return
        session = self._require_session()
        if session is None:
            return
        if not self._valid_csrf(form, session):
            self._error_page("Invalid CSRF token.", HTTPStatus.FORBIDDEN, session)
            return
        if path == "/logout":
            self.server.sessions.remove(self._cookie_token())
            self._redirect("/login")
            return
        if not self.service.status().get("is_primary"):
            target = self.portal.primary_url()
            if target is not None:
                self._redirect(target)
            else:
                self._error_page(
                    "This operation requires the primary, but its URL is unknown.",
                    HTTPStatus.CONFLICT,
                    session,
                )
            return
        try:
            self._action(path, form, session)
        except AdminError as error:
            self._error_page(str(error), HTTPStatus.BAD_REQUEST, session)
        except Exception as error:
            name = error.__class__.__name__
            if name == "NotPrimaryError":
                target = self.portal.primary_url()
                if target is not None:
                    self._redirect(target)
                else:
                    self._error_page(str(error), HTTPStatus.CONFLICT, session)
            elif name == "NoQuorumError":
                self._error_page(str(error), HTTPStatus.SERVICE_UNAVAILABLE, session)
            else:
                self._error_page(str(error), HTTPStatus.BAD_REQUEST, session)

    def _valid_csrf(self, form, session):
        return hmac.compare_digest(
            self._form_value(form, "csrf"), session["csrf"]
        )

    def _login(self, form):
        username = self._form_value(form, "username").strip()
        password = self._form_value(form, "password")
        try:
            user = self.service.authenticate(username, password)
        except AdminError as error:
            self._login_page(str(error))
            return
        token, _ = self.server.sessions.create(user.username)
        cookie = (
            "cloudfs_admin={}; Path=/; HttpOnly; SameSite=Strict; Secure; "
            "Max-Age={}".format(token, int(self.config.admin_session_timeout))
        )
        self._redirect("/", headers={"Set-Cookie": cookie})

    def _dashboard(self, session):
        status = self.service.status()
        notice = ""
        if not status.get("is_primary"):
            target = self.portal.primary_url()
            notice = '<div class="notice">This node is a follower. Write actions are redirected to the primary{}. </div>'.format(
                ' <a href="{}">{}</a>'.format(html.escape(target), html.escape(target))
                if target
                else ""
            )
        rows = "".join(
            "<tr><th>{}</th><td>{}</td></tr>".format(
                html.escape(str(key)),
                (
                    '<span class="badge badge-{}">{}</span>'.format(
                        "leader" if str(value) == "leader" else "follower",
                        html.escape(str(value)),
                    )
                    if key == "role"
                    else html.escape(str(value))
                ),
            )
            for key, value in status.items()
        )
        audit = "".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html.escape(item["time"]),
                html.escape(item["actor"]),
                html.escape(item["action"]),
                html.escape(item["target"]),
            )
            for item in self.service.audit()
        )
        step_down = ""
        if status.get("is_primary") and self.config.allow_admin_failover:
            step_down = """
            <form method="post" action="/admin/step-down" class="inline">
              <input type="hidden" name="csrf" value="{csrf}">
              <button type="submit">Simulate primary failure (demo)</button>
            </form>
            """.format(csrf=html.escape(session["csrf"]))
        body = """
        {notice}
        <div class="card"><h2>Replication status</h2><table>{rows}</table></div>
        <div class="card"><h2>Recent actions</h2>
          <table><tr><th>Date</th><th>Admin</th><th>Action</th><th>Target</th></tr>{audit}</table>
          {step_down}
        </div>
        """.format(notice=notice, rows=rows, audit=audit or "<tr><td colspan='4'>No actions</td></tr>", step_down=step_down)
        self._send(self._page("Status", body, session))

    def _users_page(self, session):
        rows = []
        for user in self.service.users():
            name = html.escape(user["username"])
            quoted = quote(user["username"], safe="")
            toggle = "enable" if user["disabled"] else "disable"
            label = "Enable" if user["disabled"] else "Disable"
            rows.append(
                """<tr><td>{name}</td><td>{role}</td><td>{disabled}</td>
                <td>
                <form method="post" action="/users/{quoted}/{toggle}" class="inline">
                  <input type="hidden" name="csrf" value="{csrf}">
                  <button type="submit">{label}</button>
                </form>
                <form method="post" action="/users/{quoted}/password" class="inline">
                  <input type="hidden" name="csrf" value="{csrf}">
                  <input type="password" name="password" placeholder="New password">
                  <button type="submit">Reset</button>
                </form>
                </td></tr>""".format(
                    name=name,
                    role=html.escape(user["role"]),
                    disabled='<span class="badge badge-{}">{}</span>'.format(
                        "follower" if user["disabled"] else "leader",
                        "yes" if user["disabled"] else "no",
                    ),
                    quoted=html.escape(quoted),
                    toggle=toggle,
                    label=label,
                    csrf=html.escape(session["csrf"]),
                )
            )
        body = """
        <div class="card"><h2>Create user</h2>
          <form method="post" action="/users">
            <input type="hidden" name="csrf" value="{csrf}">
            <input name="username" placeholder="Username">
            <input type="password" name="password" placeholder="Password">
            <button type="submit">Create</button>
          </form>
        </div>
        <div class="card"><h2>Users</h2>
          <table><tr><th>Username</th><th>Role</th><th>Disabled</th><th>Actions</th></tr>{rows}</table>
        </div>
        """.format(csrf=html.escape(session["csrf"]), rows="".join(rows))
        self._send(self._page("Users", body, session))

    def _shares_page(self, session):
        rows = "".join(
            """<tr><td>{owner}</td><td>{path}</td><td>{grantee}</td><td>{access}</td>
            <td><form method="post" action="/shares/revoke" class="inline">
              <input type="hidden" name="csrf" value="{csrf}">
              <input type="hidden" name="owner" value="{owner}">
              <input type="hidden" name="path" value="{path}">
              <input type="hidden" name="grantee" value="{grantee}">
              <button type="submit">Revoke</button>
            </form></td></tr>""".format(
                owner=html.escape(share["owner"]),
                path=html.escape(share["path"]),
                grantee=html.escape(share["grantee"]),
                access='<span class="badge badge-{}">{}</span>'.format(
                    html.escape(share["access"]), html.escape(share["access"])
                ),
                csrf=html.escape(session["csrf"]),
            )
            for share in self.service.shares()
        )
        body = '<div class="card"><h2>Shares</h2><table><tr><th>Owner</th><th>Path</th><th>User</th><th>Access</th><th></th></tr>{}</table></div>'.format(
            rows or "<tr><td colspan='5'>No shares</td></tr>"
        )
        self._send(self._page("Shares", body, session))

    def _settings_page(self, session):
        enabled = self.service.status().get("registration_enabled", False)
        body = """
        <div class="card"><h2>Settings</h2>
          <form method="post" action="/settings/registration">
            <input type="hidden" name="csrf" value="{csrf}">
            <label><input type="checkbox" name="registration" {checked}> Allow open registration</label>
            <button type="submit">Save</button>
          </form>
        </div>
        """.format(
            csrf=html.escape(session["csrf"]),
            checked="checked" if enabled else "",
        )
        self._send(self._page("Settings", body, session))

    def _json(self, data):
        self._send(
            json.dumps(data, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
        )

    def _action(self, path, form, session):
        actor = session["username"]
        if path == "/users":
            self.service.create_user(
                self._form_value(form, "username").strip(),
                self._form_value(form, "password"),
                actor,
            )
            self._redirect("/users")
        elif path.startswith("/users/"):
            parts = [unquote(item) for item in path.split("/") if item]
            if len(parts) == 3 and parts[2] in {"disable", "enable"}:
                self.service.set_user_disabled(
                    parts[1], parts[2] == "disable", actor
                )
                self._redirect("/users")
            elif len(parts) == 3 and parts[2] == "password":
                self.service.reset_password(
                    parts[1], self._form_value(form, "password"), actor
                )
                self._redirect("/users")
            else:
                self._error_page("Invalid user action.", session=session)
        elif path == "/shares/revoke":
            self.service.revoke_share(
                self._form_value(form, "owner"),
                self._form_value(form, "path"),
                self._form_value(form, "grantee"),
                actor,
            )
            self._redirect("/shares")
        elif path == "/settings/registration":
            self.service.set_registration(
                self._form_value(form, "registration") == "on", actor
            )
            self._redirect("/settings")
        elif path == "/admin/step-down":
            self.service.step_down(actor)
            self._redirect("/")
        else:
            self._error_page("Route not found.", HTTPStatus.NOT_FOUND, session)
