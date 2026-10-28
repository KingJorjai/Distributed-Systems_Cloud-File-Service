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
            <nav>
              <a href="/">Estado</a>
              <a href="/users">Usuarios</a>
              <a href="/shares">Shares</a>
              <a href="/settings">Ajustes</a>
              <form method="post" action="/logout" class="inline">
                <input type="hidden" name="csrf" value="{csrf}">
                <button type="submit">Salir</button>
              </form>
            </nav>
            """.format(csrf=html.escape(session["csrf"]))
        return """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; background: #f5f7fb; color: #1d2433; }}
header {{ background: #1f4fd1; color: white; padding: 14px 22px; }}
header h1 {{ margin: 0; font-size: 20px; }}
nav {{ background: white; padding: 10px 22px; border-bottom: 1px solid #dde3ee; }}
nav a, nav button {{ margin-right: 14px; color: #1f4fd1; text-decoration: none; }}
form.inline {{ display: inline; }}
main {{ max-width: 1100px; margin: 22px auto; padding: 0 16px; }}
.card {{ background: white; border: 1px solid #dde3ee; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #edf0f6; }}
input, button, select {{ padding: 7px 9px; margin: 3px 0; }}
button {{ cursor: pointer; }}
.error {{ color: #a40000; }}
.notice {{ background: #fff5d6; border: 1px solid #e6c65c; padding: 10px; border-radius: 6px; }}
</style>
</head>
<body>
<header><h1>Cloud File Service · Administración</h1></header>
{nav}
<main>{body}</main>
</body>
</html>""".format(title=html.escape(title), nav=nav, body=body)

    def _login_page(self, error=""):
        body = """
        <div class="card">
          <h2>Iniciar sesión</h2>
          {error}
          <form method="post" action="/login">
            <label>Usuario<br><input name="username" autocomplete="username"></label><br>
            <label>Contraseña<br><input type="password" name="password" autocomplete="current-password"></label><br>
            <button type="submit">Entrar</button>
          </form>
        </div>
        """.format(
            error='<p class="error">{}</p>'.format(html.escape(error)) if error else ""
        )
        self._send(self._page("Administración", body))

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
            self._error_page("Ruta no encontrada.", HTTPStatus.NOT_FOUND, session)

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
            self._error_page("Token CSRF inválido.", HTTPStatus.FORBIDDEN, session)
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
                    "La operación requiere el primario, pero no se conoce su URL.",
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
            notice = '<div class="notice">Este nodo es seguidor. Las acciones de escritura se redirigen al primario{}. </div>'.format(
                ' <a href="{}">{}</a>'.format(html.escape(target), html.escape(target))
                if target
                else ""
            )
        rows = "".join(
            "<tr><th>{}</th><td>{}</td></tr>".format(
                html.escape(str(key)), html.escape(str(value))
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
              <button type="submit">Simular caída del primario (demo)</button>
            </form>
            """.format(csrf=html.escape(session["csrf"]))
        body = """
        {notice}
        <div class="card"><h2>Estado de replicación</h2><table>{rows}</table></div>
        <div class="card"><h2>Acciones recientes</h2>
          <table><tr><th>Fecha</th><th>Admin</th><th>Acción</th><th>Objetivo</th></tr>{audit}</table>
          {step_down}
        </div>
        """.format(notice=notice, rows=rows, audit=audit or "<tr><td colspan='4'>Sin acciones</td></tr>", step_down=step_down)
        self._send(self._page("Estado", body, session))

    def _users_page(self, session):
        rows = []
        for user in self.service.users():
            name = html.escape(user["username"])
            quoted = quote(user["username"], safe="")
            toggle = "enable" if user["disabled"] else "disable"
            label = "Habilitar" if user["disabled"] else "Deshabilitar"
            rows.append(
                """<tr><td>{name}</td><td>{role}</td><td>{disabled}</td>
                <td>
                <form method="post" action="/users/{quoted}/{toggle}" class="inline">
                  <input type="hidden" name="csrf" value="{csrf}">
                  <button type="submit">{label}</button>
                </form>
                <form method="post" action="/users/{quoted}/password" class="inline">
                  <input type="hidden" name="csrf" value="{csrf}">
                  <input type="password" name="password" placeholder="Nueva contraseña">
                  <button type="submit">Resetear</button>
                </form>
                </td></tr>""".format(
                    name=name,
                    role=html.escape(user["role"]),
                    disabled="sí" if user["disabled"] else "no",
                    quoted=html.escape(quoted),
                    toggle=toggle,
                    label=label,
                    csrf=html.escape(session["csrf"]),
                )
            )
        body = """
        <div class="card"><h2>Crear usuario</h2>
          <form method="post" action="/users">
            <input type="hidden" name="csrf" value="{csrf}">
            <input name="username" placeholder="Usuario">
            <input type="password" name="password" placeholder="Contraseña">
            <button type="submit">Crear</button>
          </form>
        </div>
        <div class="card"><h2>Usuarios</h2>
          <table><tr><th>Usuario</th><th>Rol</th><th>Deshabilitado</th><th>Acciones</th></tr>{rows}</table>
        </div>
        """.format(csrf=html.escape(session["csrf"]), rows="".join(rows))
        self._send(self._page("Usuarios", body, session))

    def _shares_page(self, session):
        rows = "".join(
            """<tr><td>{owner}</td><td>{path}</td><td>{grantee}</td><td>{access}</td>
            <td><form method="post" action="/shares/revoke" class="inline">
              <input type="hidden" name="csrf" value="{csrf}">
              <input type="hidden" name="owner" value="{owner}">
              <input type="hidden" name="path" value="{path}">
              <input type="hidden" name="grantee" value="{grantee}">
              <button type="submit">Revocar</button>
            </form></td></tr>""".format(
                owner=html.escape(share["owner"]),
                path=html.escape(share["path"]),
                grantee=html.escape(share["grantee"]),
                access=html.escape(share["access"]),
                csrf=html.escape(session["csrf"]),
            )
            for share in self.service.shares()
        )
        body = '<div class="card"><h2>Shares</h2><table><tr><th>Propietario</th><th>Ruta</th><th>Usuario</th><th>Acceso</th><th></th></tr>{}</table></div>'.format(
            rows or "<tr><td colspan='5'>Sin shares</td></tr>"
        )
        self._send(self._page("Shares", body, session))

    def _settings_page(self, session):
        enabled = self.service.status().get("registration_enabled", False)
        body = """
        <div class="card"><h2>Ajustes</h2>
          <form method="post" action="/settings/registration">
            <input type="hidden" name="csrf" value="{csrf}">
            <label><input type="checkbox" name="registration" {checked}> Permitir registro abierto</label>
            <button type="submit">Guardar</button>
          </form>
        </div>
        """.format(
            csrf=html.escape(session["csrf"]),
            checked="checked" if enabled else "",
        )
        self._send(self._page("Ajustes", body, session))

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
                self._error_page("Acción de usuario no válida.", session=session)
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
            self._error_page("Ruta no encontrada.", HTTPStatus.NOT_FOUND, session)
