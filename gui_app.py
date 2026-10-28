"""Tkinter desktop interface for the synchronization daemon."""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from app_logging import default_log_file
from autostart import disable as disable_autostart
from autostart import enable as enable_autostart
from autostart import is_enabled
from config import default_config_path, load_config

try:
    from tray import TrayIcon
except ImportError:
    TrayIcon = None


def _open_path(path):
    target = str(path)
    if os.name == "nt":
        os.startfile(target)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


class GuiApp:
    """Main Tk application, all widget access stays on the main thread."""

    def __init__(self, root, controller, config_path=None, start_minimized=False):
        self.root = root
        self.controller = controller
        self.config_path = Path(config_path or default_config_path())
        self.config = load_config(self.config_path).client
        self.results = queue.Queue()
        self.running = False
        self.logged_in = False
        self.tray = None
        self.login_frame = None
        self.main_frame = None

        root.title("Cloud File Service")
        root.geometry("820x620")
        root.protocol("WM_DELETE_WINDOW", self.hide)
        self.controller.subscribe()
        self._build_login()
        self._start_tray()
        if start_minimized and self.tray is not None and self.tray.available:
            root.withdraw()
        self.root.after(200, self._poll)

    def _start_tray(self):
        if TrayIcon is None:
            self.tray = None
            return
        self.tray = TrayIcon(
            self.root,
            on_show=self.show,
            on_open_folder=self.open_folder,
            on_toggle=self.toggle_sync,
            on_quit=self.quit,
        )
        try:
            self.tray.start()
        except Exception:
            self.tray = None
        self.root.after(1500, self._check_tray)

    def _check_tray(self):
        if self.tray is None or self.tray.docked:
            return
        self.tray.stop()
        self.tray = None
        if self.root.state() == "withdrawn":
            self.show()
        self._log("Bandeja del sistema no disponible; la ventana se minimizará.")

    def _clear(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def _build_login(self):
        self._clear()
        self.login_frame = ttk.Frame(self.root, padding=20)
        self.login_frame.pack(fill="both", expand=True)
        ttk.Label(
            self.login_frame,
            text="Cloud File Service",
            font=("TkDefaultFont", 18, "bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(0, 15), sticky="w")

        self.server_var = tk.StringVar(value=self.config.server)
        self.port_var = tk.StringVar(value=str(self.config.port))
        self.folder_var = tk.StringVar(value=self.config.local_path)
        self.ca_var = tk.StringVar(value=self.config.tls_ca_file)
        self.user_var = tk.StringVar()
        self.password_var = tk.StringVar()

        fields = [
            ("Servidor", self.server_var, None),
            ("Puerto", self.port_var, None),
            ("Carpeta local", self.folder_var, "folder"),
            ("CA TLS (opcional)", self.ca_var, "file"),
            ("Usuario", self.user_var, None),
            ("Contraseña", self.password_var, "password"),
        ]
        for row, (label, variable, kind) in enumerate(fields, start=1):
            ttk.Label(self.login_frame, text=label).grid(
                row=row, column=0, sticky="w", pady=4
            )
            entry = ttk.Entry(
                self.login_frame,
                textvariable=variable,
                show="*" if kind == "password" else "",
            )
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            if kind in {"folder", "file"}:
                ttk.Button(
                    self.login_frame,
                    text="Elegir",
                    command=lambda v=variable, k=kind: self._choose(v, k),
                ).grid(row=row, column=2, padx=(6, 0))
        self.login_frame.columnconfigure(1, weight=1)

        self.login_status = ttk.Label(self.login_frame, text="")
        self.login_status.grid(row=8, column=0, columnspan=3, pady=10, sticky="w")
        buttons = ttk.Frame(self.login_frame)
        buttons.grid(row=9, column=0, columnspan=3, pady=8, sticky="w")
        ttk.Button(buttons, text="Iniciar sesión", command=self.login).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="Registrarse", command=self.register).pack(
            side="left"
        )

    def _choose(self, variable, kind):
        if kind == "folder":
            value = filedialog.askdirectory()
        else:
            value = filedialog.askopenfilename(
                filetypes=[("Certificados", "*.crt *.pem"), ("Todos", "*.*")]
            )
        if value:
            variable.set(value)

    def _values(self):
        return {
            "server": self.server_var.get().strip(),
            "port": self.port_var.get().strip(),
            "local_path": self.folder_var.get().strip(),
            "tls_ca_file": self.ca_var.get().strip(),
        }

    def login(self):
        values = self._values()
        username = self.user_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            self.login_status.configure(text="Introduce usuario y contraseña.")
            return
        self.login_status.configure(text="Conectando…")
        self._run(
            lambda: self._login_with(values, username, password),
            self._logged_in,
            self._login_failed,
        )

    def _login_with(self, values, username, password):
        self.controller.save_settings(**values)
        return self.controller.login(username, password)

    def _logged_in(self, status):
        self.logged_in = True
        self.running = bool(status.get("running"))
        self.password_var.set("")
        self._build_main()
        self.refresh_shares()
        self.refresh_users()

    def _login_failed(self, error):
        if self.login_frame is not None:
            self.login_status.configure(text=str(error))

    def register(self):
        values = self._values()
        username = self.user_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            self.login_status.configure(text="Introduce usuario y contraseña.")
            return
        self.login_status.configure(text="Registrando…")
        self._run(
            lambda: self._register_with(values, username, password),
            lambda result: self.login_status.configure(
                text="Cuenta creada. Ya puedes iniciar sesión."
            ),
            self._login_failed,
        )

    def _register_with(self, values, username, password):
        self.controller.save_settings(**values)
        return self.controller.register(username, password)

    def _build_main(self):
        self._clear()
        self.main_frame = ttk.Frame(self.root, padding=10)
        self.main_frame.pack(fill="both", expand=True)
        top = ttk.Frame(self.main_frame)
        top.pack(fill="x")
        self.status_var = tk.StringVar(value="Conectado")
        self.endpoint_var = tk.StringVar(value="")
        self.pending_var = tk.StringVar(value="0 cambios pendientes")
        ttk.Label(top, textvariable=self.status_var, font=("TkDefaultFont", 13, "bold")).pack(side="left")
        ttk.Label(top, textvariable=self.endpoint_var).pack(side="left", padx=12)
        ttk.Label(top, textvariable=self.pending_var).pack(side="right")

        actions = ttk.Frame(self.main_frame)
        actions.pack(fill="x", pady=6)
        self.pause_button = ttk.Button(
            actions, text="Pausar sincronización", command=self.toggle_sync
        )
        self.pause_button.pack(side="left")
        ttk.Button(actions, text="Abrir carpeta", command=self.open_folder).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="Cambiar contraseña", command=self.change_password).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="Abrir logs", command=self.open_logs).pack(
            side="left", padx=6
        )
        ttk.Button(actions, text="Cerrar sesión", command=self.logout).pack(
            side="right"
        )

        notebook = ttk.Notebook(self.main_frame)
        notebook.pack(fill="both", expand=True, pady=6)
        self._build_sync_tab(notebook)
        self._build_shares_tab(notebook)
        self._build_settings_tab(notebook)
        self._build_log_tab(notebook)
        self._update_status(
            {
                "running": self.running,
                "username": self.user_var.get(),
                "pending": 0,
            }
        )

    def _build_sync_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="Sincronización")
        ttk.Label(
            frame,
            text="La sincronización se ejecuta en el daemon y continúa al cerrar la ventana.",
            wraplength=700,
        ).pack(anchor="w")
        self.sync_log = tk.Text(frame, height=18, state="disabled")
        self.sync_log.pack(fill="both", expand=True, pady=8)

    def _build_shares_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="Compartidos")
        self.share_tree = ttk.Treeview(
            frame,
            columns=("owner", "path", "grantee", "access"),
            show="headings",
            height=8,
        )
        for column, title in (
            ("owner", "Propietario"),
            ("path", "Ruta"),
            ("grantee", "Usuario"),
            ("access", "Acceso"),
        ):
            self.share_tree.heading(column, text=title)
            self.share_tree.column(column, width=150)
        self.share_tree.pack(fill="both", expand=True)
        ttk.Button(frame, text="Actualizar", command=self.refresh_shares).pack(
            anchor="w", pady=4
        )
        form = ttk.Frame(frame)
        form.pack(fill="x", pady=4)
        ttk.Label(form, text="Ruta").pack(side="left")
        self.share_path = ttk.Entry(form, width=24)
        self.share_path.pack(side="left", padx=4)
        ttk.Label(form, text="Usuario").pack(side="left")
        self.share_user = ttk.Combobox(form, width=18, state="readonly")
        self.share_user.pack(side="left", padx=4)
        ttk.Label(form, text="Acceso").pack(side="left")
        self.share_access = ttk.Combobox(
            form, values=("ro", "rw"), width=5, state="readonly"
        )
        self.share_access.current(0)
        self.share_access.pack(side="left", padx=4)
        ttk.Button(form, text="Compartir", command=self.share).pack(
            side="left", padx=4
        )
        ttk.Button(form, text="Revocar seleccionado", command=self.unshare).pack(
            side="left", padx=4
        )

    def _build_settings_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="Ajustes")
        ttk.Label(
            frame,
            text="Las variables de entorno siguen teniendo prioridad sobre estos valores.",
            wraplength=700,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        entries = [
            ("Servidor", "server"),
            ("Puerto", "port"),
            ("Carpeta local", "local_path"),
            ("CA TLS", "tls_ca_file"),
            ("Peers", "peers"),
        ]
        self.setting_vars = {}
        for row, (label, key) in enumerate(entries, start=1):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            variable = tk.StringVar(value=str(getattr(self.config, key)))
            self.setting_vars[key] = variable
            ttk.Entry(frame, textvariable=variable).grid(
                row=row, column=1, sticky="ew", pady=4
            )
        frame.columnconfigure(1, weight=1)
        self.autostart_var = tk.BooleanVar(value=is_enabled())
        ttk.Checkbutton(
            frame,
            text="Arrancar al iniciar el sistema",
            variable=self.autostart_var,
            command=self.toggle_autostart,
        ).grid(row=7, column=1, sticky="w", pady=8)
        ttk.Button(frame, text="Guardar ajustes", command=self.save_settings).grid(
            row=8, column=1, sticky="w"
        )

    def _build_log_tab(self, notebook):
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="Registro")
        self.log_text = tk.Text(frame, height=18, state="disabled")
        self.log_text.pack(fill="both", expand=True)

    def _append(self, widget, text):
        widget.configure(state="normal")
        widget.insert("end", text + "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def _log(self, text):
        if hasattr(self, "log_text"):
            self._append(self.log_text, text)

    def _update_status(self, data):
        if not hasattr(self, "status_var"):
            return
        if isinstance(data, dict):
            self.running = bool(data.get("running", self.running))
            self.status_var.set("Sincronizando" if self.running else "Pausado")
            self.endpoint_var.set(data.get("endpoint") or "")
            self.pending_var.set("{} cambios pendientes".format(data.get("pending", 0)))
            if hasattr(self, "pause_button"):
                self.pause_button.configure(
                    text="Pausar sincronización" if self.running else "Reanudar sincronización"
                )
            if self.tray is not None:
                self.tray.set_paused(not self.running)
            if data.get("last_error"):
                self._log("Error: {}".format(data["last_error"]))

    def refresh_shares(self):
        self._run(self.controller.shares, self._render_shares)

    def _render_shares(self, shares):
        if not hasattr(self, "share_tree"):
            return
        for item in self.share_tree.get_children():
            self.share_tree.delete(item)
        for share in shares:
            self.share_tree.insert(
                "",
                "end",
                values=(share["owner"], share["path"], share["grantee"], share["access"]),
            )

    def refresh_users(self):
        self._run(self.controller.users, self._render_users)

    def _render_users(self, users):
        if hasattr(self, "share_user"):
            self.share_user["values"] = tuple(users)

    def share(self):
        path = self.share_path.get().strip()
        grantee = self.share_user.get().strip()
        access = self.share_access.get().strip() or "ro"
        if not path or not grantee:
            messagebox.showwarning("Compartir", "Indica ruta y usuario.")
            return
        self._run(
            lambda: self.controller.share(path, grantee, access),
            self._render_shares,
        )

    def unshare(self):
        selected = self.share_tree.selection()
        if not selected:
            messagebox.showwarning("Revocar", "Selecciona un share.")
            return
        values = self.share_tree.item(selected[0], "values")
        owner, path, grantee, access = values
        if owner != (self.controller.status().get("username") or ""):
            messagebox.showwarning("Revocar", "Solo el propietario puede revocar.")
            return
        self._run(
            lambda: self.controller.unshare(path, grantee),
            self._render_shares,
        )

    def change_password(self):
        old = simpledialog.askstring("Contraseña", "Contraseña actual:", show="*")
        if old is None:
            return
        new = simpledialog.askstring("Contraseña", "Contraseña nueva:", show="*")
        if not new:
            return
        self._run(
            lambda: self.controller.change_password(old, new),
            lambda _: messagebox.showinfo("Contraseña", "Contraseña actualizada."),
        )

    def logout(self):
        self._run(self.controller.logout, self._logged_out)

    def _logged_out(self, status):
        self.logged_in = False
        self.running = False
        self.user_var.set("")
        self._build_login()

    def toggle_sync(self):
        action = self.controller.stop_sync if self.running else self.controller.start_sync
        self._run(action, self._update_status)

    def open_folder(self):
        path = Path(self.controller.status().get("local_path") or self.folder_var.get())
        if path.exists():
            _open_path(path)

    def open_logs(self):
        path = default_log_file("gui").resolve().parent
        path.mkdir(parents=True, exist_ok=True)
        _open_path(path)

    def save_settings(self):
        values = {
            key: variable.get() for key, variable in self.setting_vars.items()
        }
        self._run(
            lambda: self.controller.save_settings(**values),
            lambda updated: self._log("Ajustes guardados en {}".format(self.config_path)),
        )

    def toggle_autostart(self):
        try:
            if self.autostart_var.get():
                enable_autostart()
            else:
                disable_autostart()
        except Exception as error:
            messagebox.showerror("Autostart", str(error))

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        if self.tray is not None and self.tray.available:
            self.root.withdraw()
        else:
            self.root.iconify()

    def quit(self):
        self.controller.shutdown()
        if self.tray is not None:
            self.tray.stop()
        self.root.destroy()

    def _run(self, function, on_ok=None, on_error=None):
        def worker():
            try:
                result = function()
            except Exception as error:
                self.results.put(("error", error, on_error))
            else:
                self.results.put(("ok", result, on_ok))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, value, callback = self.results.get_nowait()
                if kind == "error":
                    if callback is not None:
                        callback(value)
                    else:
                        self._log("Error: {}".format(value))
                        messagebox.showerror("Cloud File Service", str(value))
                elif callback is not None:
                    callback(value)
        except queue.Empty:
            pass
        for event, data in self.controller.poll_events():
            if event == "status":
                self._update_status(data)
            elif event == "worker":
                self._log(str(data))
            elif event == "disconnected":
                self._log("Daemon desconectado; reintentando…")
        self.root.after(250, self._poll)
