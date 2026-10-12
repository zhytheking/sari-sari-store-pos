"""
Main window — application shell.

Changes vs original:
  1. show_*() methods print full tracebacks instead of swallowing
     exceptions. Silent failures were hiding GUI bugs.
  2. Header still shows only store name + role + Logout.
  3. Sidebar includes "📜 Audit Log" for owners.
  4. Settings page is editable and includes Network info.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import socket
import sys
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from frontend.gui.api import Api, ApiError
from frontend.gui.config import get_api_url
from frontend.gui.logger import get_logger
from frontend.gui.ui import async_call, toast

log = get_logger(__name__)


# ══════════════════════════════════════════════════════════════
# NETWORK HELPERS
# ══════════════════════════════════════════════════════════════

def detect_lan_ip() -> str:
    """Return the machine's LAN IP. Falls back to 127.0.0.1."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        try:
            s.close()
        except Exception:
            pass
    return ip


def detect_public_ip() -> str:
    """Return the machine's public IP or 'Unavailable'."""
    try:
        req = urllib.request.Request(
            "https://api.ipify.org",
            headers={"User-Agent": "SariSariPOS-GUI/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8").strip()
            return data if data else "Unavailable"
    except Exception as e:
        log.debug("public IP detection failed: %s", e)
        return "Unavailable"


def get_local_url(port: int = 5000) -> str:
    return f"http://127.0.0.1:{port}"


def get_lan_url(port: int = 5000) -> str:
    return f"http://{detect_lan_ip()}:{port}"


# ══════════════════════════════════════════════════════════════
# MAIN WINDOW
# ══════════════════════════════════════════════════════════════

class MainWindow(tk.Frame):
    ACCENT = '#2d6a4f'
    ACCENT_DARK = '#1b4332'
    BG = '#f0f4f8'
    SIDEBAR_BG = '#e9ecef'
    SIDEBAR_HOVER = '#dee2e6'

    def __init__(self, parent, user, on_logout):
        super().__init__(parent)
        self.parent = parent
        self.user = user or {}
        self.on_logout = on_logout
        self.api_url = get_api_url()
        self.token = getattr(parent, 'token', None)

        self.role = self.user.get('role', 'cashier')
        self.is_owner = (self.role == 'owner')

        self._clock_job = None
        self._url_refresh_job = None
        self._current_page = None
        self._nav_buttons = {}

        self._store_info = {
            'store_name': 'Loading...',
            'store_address': '',
            'store_phone': '',
            'store_email': '',
            'tax_rate': '',
            'currency_symbol': '',
            'low_stock_threshold': '',
            'receipt_footer': '',
        }

        self._header_title_label = None

        self._local_url = get_local_url(5000)
        self._lan_url = get_lan_url(5000)
        self._public_ip = None

        self._startup_notified = False

        self.setup_ui()
        self.show_dashboard()
        self.after(200, self._load_store_info_from_api)
        self.after(300, self._refresh_public_ip_async)
        self.after(1200, self._show_startup_notification_once)

    # ═════════════════════════════════════════════════════════
    # LIFECYCLE
    # ═════════════════════════════════════════════════════════
    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def destroy(self):
        for job_attr in ('_clock_job', '_url_refresh_job'):
            job = getattr(self, job_attr, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                setattr(self, job_attr, None)
        try:
            super().destroy()
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════
    # STORE INFO
    # ═════════════════════════════════════════════════════════
    def _load_store_info_from_api(self):
        if not self._alive():
            return

        def task():
            return Api.get(self.api_url, '/settings/public',
                           token=self.token, timeout=10)

        def done(data):
            if not self._alive():
                return
            if data.get('success'):
                d = data['data']
                self._store_info = {
                    'store_name': d.get('store_name', 'Store'),
                    'store_address': d.get('store_address', ''),
                    'store_phone': d.get('store_phone', ''),
                    'store_email': d.get('store_email', ''),
                    'tax_rate': d.get('tax_rate', ''),
                    'currency_symbol': d.get('currency_symbol', '₱'),
                    'low_stock_threshold': d.get('low_stock_threshold', ''),
                    'receipt_footer': d.get('receipt_footer', ''),
                }
                self._refresh_header_store_name()

        async_call(widget=self, task=task, on_success=done,
                   on_error=lambda e: log.warning(
                       "Store info load failed: %s", e))

    def _refresh_header_store_name(self):
        if not self._alive() or self._header_title_label is None:
            return
        try:
            if not self._header_title_label.winfo_exists():
                return
            user_name = self.user.get('full_name', 'User')
            store_name = self._store_info.get('store_name', 'Store')
            self._header_title_label.config(
                text=f"🏪 {store_name} - {user_name}")
        except Exception:
            pass

    def _refresh_public_ip_async(self):
        if not self._alive():
            return

        async_call(
            widget=self,
            task=detect_public_ip,
            on_success=self._on_public_ip_ready,
            on_error=lambda e: None,
        )

    def _on_public_ip_ready(self, ip):
        if not self._alive():
            return
        self._public_ip = ip

    def _refresh_web_urls(self):
        if not self._alive():
            return
        self._lan_url = get_lan_url(5000)
        try:
            self._url_refresh_job = self.after(
                300_000, self._refresh_web_urls)
        except Exception:
            self._url_refresh_job = None

    # ═════════════════════════════════════════════════════════
    # STARTUP ALERT
    # ═════════════════════════════════════════════════════════
    def _show_startup_notification_once(self):
        if self._startup_notified:
            return
        self._startup_notified = True
        if not self._alive():
            return

        def task():
            return Api.get(self.api_url, '/products',
                           token=self.token,
                           params={'per_page': 500}, timeout=15)

        def done(data):
            if not self._alive():
                return
            if not data.get('success'):
                return
            items = (data.get('data') or {}).get('items') or []
            out_of_stock, low_stock = [], []
            for p in items:
                stock = p.get('stock_quantity', 0) or 0
                min_stock = p.get('min_stock_level', 10) or 10
                if stock <= 0:
                    out_of_stock.append(p)
                elif stock <= min_stock:
                    low_stock.append(p)
            if out_of_stock or low_stock:
                self._show_alerts_dialog(out_of_stock, low_stock)

        async_call(widget=self, task=task, on_success=done,
                   on_error=lambda e: log.warning(
                       "Startup check failed: %s", e))

    def _show_alerts_dialog(self, out_of_stock, low_stock):
        if not self._alive():
            return

        dialog = tk.Toplevel(self)
        dialog.title("Inventory Notification")
        dialog.transient(self)
        dialog.configure(bg='#ffffff')
        dialog.resizable(False, False)

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 260
        y = (dialog.winfo_screenheight() // 2) - 280
        dialog.geometry(f"520x560+{x}+{y}")

        header = tk.Frame(dialog, bg='#dc3545')
        header.pack(fill='x')
        hi = tk.Frame(header, bg='#dc3545')
        hi.pack(fill='x', padx=20, pady=16)

        tk.Label(hi, text="⚠️  Inventory Alerts",
                 font=('Segoe UI', 16, 'bold'),
                 bg='#dc3545', fg='white').pack(anchor='w')
        total = len(out_of_stock) + len(low_stock)
        tk.Label(hi, text=f"{total} product(s) need your attention",
                 font=('Segoe UI', 10),
                 bg='#dc3545', fg='#ffd6d6').pack(anchor='w', pady=(2, 0))

        body_outer = tk.Frame(dialog, bg='#ffffff')
        body_outer.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(body_outer, bg='#ffffff', highlightthickness=0)
        sb = ttk.Scrollbar(body_outer, orient=tk.VERTICAL,
                           command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill='y')

        body = tk.Frame(canvas, bg='#ffffff')
        bw = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>',
                  lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',
                    lambda e: canvas.itemconfig(bw, width=e.width))

        pad = tk.Frame(body, bg='#ffffff')
        pad.pack(fill='both', expand=True, padx=20, pady=16)

        if out_of_stock:
            tk.Label(pad, text=f"❌  Out of Stock ({len(out_of_stock)})",
                     font=('Segoe UI', 11, 'bold'),
                     bg='#ffffff', fg='#dc3545').pack(anchor='w',
                                                       pady=(0, 6))
            oos = tk.Frame(pad, bg='#fce8e6',
                           highlightbackground='#f5c2c7',
                           highlightthickness=1)
            oos.pack(fill='x', pady=(0, 14))
            oi = tk.Frame(oos, bg='#fce8e6')
            oi.pack(fill='x', padx=12, pady=10)
            for p in out_of_stock[:10]:
                tk.Label(oi,
                         text=f"• {p.get('name', 'Unknown')}  —  0 left",
                         font=('Segoe UI', 9), bg='#fce8e6',
                         fg='#721c24', anchor='w',
                         justify='left').pack(fill='x', pady=1)
            if len(out_of_stock) > 10:
                tk.Label(oi,
                         text=f"... and {len(out_of_stock) - 10} more",
                         font=('Segoe UI', 9, 'italic'),
                         bg='#fce8e6', fg='#721c24',
                         anchor='w').pack(fill='x', pady=(4, 0))

        if low_stock:
            tk.Label(pad, text=f"⚠️  Low Stock ({len(low_stock)})",
                     font=('Segoe UI', 11, 'bold'),
                     bg='#ffffff', fg='#e37400').pack(anchor='w',
                                                       pady=(0, 6))
            ls = tk.Frame(pad, bg='#fef7e0',
                          highlightbackground='#ffe69c',
                          highlightthickness=1)
            ls.pack(fill='x', pady=(0, 14))
            li = tk.Frame(ls, bg='#fef7e0')
            li.pack(fill='x', padx=12, pady=10)
            for p in low_stock[:10]:
                stock = p.get('stock_quantity', 0) or 0
                min_stock = p.get('min_stock_level', 10) or 10
                tk.Label(li,
                         text=(f"• {p.get('name', 'Unknown')}  —  "
                               f"{stock} left (min: {min_stock})"),
                         font=('Segoe UI', 9), bg='#fef7e0',
                         fg='#856404', anchor='w',
                         justify='left').pack(fill='x', pady=1)
            if len(low_stock) > 10:
                tk.Label(li,
                         text=f"... and {len(low_stock) - 10} more",
                         font=('Segoe UI', 9, 'italic'),
                         bg='#fef7e0', fg='#856404',
                         anchor='w').pack(fill='x', pady=(4, 0))

        footer = tk.Frame(dialog, bg='#f8f9fa',
                          highlightbackground='#e9ecef',
                          highlightthickness=1)
        footer.pack(fill='x', side=tk.BOTTOM)
        fi = tk.Frame(footer, bg='#f8f9fa')
        fi.pack(fill='x', padx=20, pady=12)

        tk.Button(fi, text="Understood",
                  font=('Segoe UI', 10, 'bold'),
                  bg=self.ACCENT, fg='white',
                  relief='flat', bd=0, cursor='hand2',
                  padx=24, pady=8,
                  activebackground=self.ACCENT_DARK,
                  activeforeground='white',
                  command=dialog.destroy).pack(side=tk.RIGHT)

        tk.Button(fi, text="View Products",
                  font=('Segoe UI', 10),
                  bg='#e9ecef', fg='#495057',
                  relief='flat', bd=0, cursor='hand2',
                  padx=20, pady=8,
                  command=lambda: (dialog.destroy(),
                                   self._goto("products",
                                              self.show_products))
                  ).pack(side=tk.RIGHT, padx=(0, 8))

    # ═════════════════════════════════════════════════════════
    # UI
    # ═════════════════════════════════════════════════════════
    def setup_ui(self):
        self.configure(bg=self.BG)
        self.pack(fill=tk.BOTH, expand=True)
        self.setup_header()
        self.content_frame = tk.Frame(self, bg=self.BG)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        self.setup_sidebar()
        self.main_content = tk.Frame(self.content_frame, bg='#ffffff')
        self.main_content.pack(side=tk.RIGHT, fill=tk.BOTH,
                               expand=True, padx=(10, 0))

    def setup_header(self):
        """Header: store name + role badge + Logout. Nothing else."""
        header = tk.Frame(self, bg=self.ACCENT, height=62)
        header.pack(fill='x')
        header.pack_propagate(False)

        user_name = self.user.get('full_name', 'User')
        user_role = self.user.get('role', '')

        self._header_title_label = tk.Label(
            header, text=f"🏪 Saliga Sari-Sari Store - {user_name}",
            font=('Segoe UI', 13, 'bold'),
            bg=self.ACCENT, fg='white')
        self._header_title_label.pack(side=tk.LEFT, padx=(16, 8))

        if user_role:
            tk.Label(header, text=f"👑 {user_role.title()}",
                     font=('Segoe UI', 9),
                     bg=self.ACCENT_DARK, fg='#ffb703',
                     padx=10, pady=2).pack(side=tk.LEFT, padx=5)

        tk.Button(header, text="Logout",
                  font=('Segoe UI', 10),
                  bg='#dc3545', fg='white',
                  relief='flat', cursor='hand2',
                  padx=14, pady=4,
                  activebackground='#b02a37',
                  activeforeground='white',
                  command=self.confirm_logout).pack(side=tk.RIGHT, padx=14)

    # ═════════════════════════════════════════════════════════
    # SIDEBAR — this is where the Audit Log is added
    # ═════════════════════════════════════════════════════════
    def setup_sidebar(self):
        sidebar = tk.Frame(self.content_frame, bg=self.SIDEBAR_BG, width=200)
        sidebar.pack(side=tk.LEFT, fill='y')
        sidebar.pack_propagate(False)

        buttons = [
            ("dashboard", "📊  Dashboard", self.show_dashboard),
            ("pos", "🛒  POS", self.show_pos),
            ("products", "📦  Products", self.show_products),
            ("sales", "🧾  Sales History", self.show_sales_history),
        ]
        if self.is_owner:
            buttons += [
                ("reports", "📈  Reports", self.show_reports),
                ("accounts", "ℹ️  Accounts", self.show_informations),
                ("audit", "📜  Audit Log", self.show_audit),
                ("settings", "⚙️  Settings", self.show_settings),
            ]

        for key, text, command in buttons:
            btn = tk.Button(
                sidebar, text=text, font=('Segoe UI', 10),
                bg=self.SIDEBAR_BG, fg='#212529',
                relief='flat', anchor='w',
                padx=16, pady=10, cursor='hand2',
                activebackground=self.SIDEBAR_HOVER,
                command=lambda k=key, c=command: self._goto(k, c))
            btn.pack(fill='x', pady=1)

            def _on_enter(event, b=btn):
                try:
                    if b.winfo_exists():
                        b.config(bg=self.SIDEBAR_HOVER)
                except Exception:
                    pass

            def _on_leave(event, b=btn):
                try:
                    if b.winfo_exists():
                        b.config(bg=self.SIDEBAR_BG)
                except Exception:
                    pass

            btn.bind('<Enter>', _on_enter)
            btn.bind('<Leave>', _on_leave)
            self._nav_buttons[key] = btn

    def _goto(self, key, command):
        if not self._alive():
            return
        for k, b in self._nav_buttons.items():
            try:
                if not b.winfo_exists():
                    continue
                b.config(bg=self.SIDEBAR_HOVER if k == key
                         else self.SIDEBAR_BG)
            except Exception:
                continue
        self._current_page = key
        if not self._alive():
            return
        try:
            command()
        except tk.TclError:
            pass
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(f"{e}")

    def clear_main_content(self):
        if not self._alive():
            return
        for w in self.main_content.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

    def _show_loading(self, message):
        if not self._alive():
            return
        self.clear_main_content()
        tk.Label(self.main_content, text=f"⏳ {message}",
                 font=('Segoe UI', 14),
                 bg='#ffffff', fg='#6c757d').pack(expand=True)

    def _show_error(self, message):
        if not self._alive():
            return
        self.clear_main_content()
        tk.Label(self.main_content, text=f"❌ {message}",
                 font=('Segoe UI', 12),
                 bg='#ffffff', fg='#dc3545',
                 wraplength=800, justify='center').pack(expand=True)
        tk.Button(self.main_content, text="🔄  Retry",
                  bg=self.ACCENT, fg='white',
                  font=('Segoe UI', 10, 'bold'),
                  padx=20, pady=10, relief='flat', bd=0,
                  command=self.show_dashboard).pack(pady=10)

    # ═════════════════════════════════════════════════════════
    # VIEWS
    # ═════════════════════════════════════════════════════════
    def show_dashboard(self):
        if not self._alive():
            return
        self.clear_main_content()
        try:
            from frontend.gui.components.stats_panel import StatsPanel
            panel = StatsPanel(self.main_content, self.api_url,
                               self.token, user=self.user)
            panel.pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(f"Dashboard error: {e}")

    def show_pos(self):
        if not self._alive():
            return
        self.clear_main_content()
        self._show_loading("Loading POS...")
        try:
            from frontend.gui.windows.pos_window import POSWindow
            pos = POSWindow(self.main_content, self.api_url, self.token)
            pos.pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(f"POS error: {e}")

    def show_products(self):
        if not self._alive():
            return
        self.clear_main_content()
        self._show_loading("Loading products...")
        try:
            from frontend.gui.components.product_grid import ProductGrid
            grid = ProductGrid(self.main_content, self.api_url, self.token)
            grid.pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(f"Products error: {e}")

    def show_sales_history(self):
        if not self._alive():
            return
        self.clear_main_content()
        self._show_loading("Loading sales history...")
        try:
            from frontend.gui.windows.sales_history_window import (
                SalesHistoryWindow,
            )
            sh = SalesHistoryWindow(
                self.main_content, self.api_url, self.token,
                current_user=self.user, is_owner=self.is_owner)
            sh.pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(f"Sales history error: {e}")

    def show_reports(self):
        if not self._alive():
            return
        if not self.is_owner:
            messagebox.showwarning("Access Denied",
                                   "Only owners can view reports.")
            return
        self.clear_main_content()
        try:
            from frontend.gui.windows.admin_window import AdminWindow
            admin = AdminWindow(
                self.main_content, self.api_url, self.token,
                initial_tab='reports', single_tab=True)
            admin.pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(f"Reports error: {e}")

    def show_informations(self):
        if not self._alive():
            return
        if not self.is_owner:
            messagebox.showwarning("Access Denied",
                                   "Only owners can view accounts.")
            return
        self.clear_main_content()
        try:
            from frontend.gui.windows.admin_window import AdminWindow
            admin = AdminWindow(
                self.main_content, self.api_url, self.token,
                initial_tab='users', single_tab=True)
            admin.pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(f"Accounts error: {e}")

    # ═════════════════════════════════════════════════════════
    # AUDIT LOG — new view
    # ═════════════════════════════════════════════════════════
    def show_audit(self):
        if not self._alive():
            return
        if not self.is_owner:
            messagebox.showwarning("Access Denied",
                                   "Only owners can view the audit log.")
            return
        self.clear_main_content()
        self._show_loading("Loading audit log...")
        try:
            from frontend.gui.windows.audit_window import AuditWindow
            view = AuditWindow(self.main_content, self.api_url, self.token)
            view.pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(f"Audit log error: {e}")

    # ═════════════════════════════════════════════════════════
    # SETTINGS
    # ═════════════════════════════════════════════════════════
    def show_settings(self):
        if not self._alive():
            return
        if not self.is_owner:
            messagebox.showwarning("Access Denied",
                                   "Only owners can change settings.")
            return
        self.clear_main_content()

        outer = tk.Frame(self.main_content, bg='#ffffff')
        outer.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(outer, bg='#ffffff', highlightthickness=0)
        vscroll = ttk.Scrollbar(outer, orient=tk.VERTICAL,
                                command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll.pack(side=tk.RIGHT, fill='y')

        wrapper = tk.Frame(canvas, bg='#ffffff')
        window_id = canvas.create_window((0, 0), window=wrapper,
                                          anchor='nw')

        def _on_wrapper_configure(event=None):
            try:
                canvas.configure(scrollregion=canvas.bbox('all'))
            except Exception:
                pass

        def _on_canvas_configure(event):
            try:
                canvas.itemconfig(window_id, width=event.width)
            except Exception:
                pass

        wrapper.bind('<Configure>', _on_wrapper_configure)
        canvas.bind('<Configure>', _on_canvas_configure)

        def _on_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
            except Exception:
                pass

        canvas.bind_all('<MouseWheel>', _on_mousewheel)
        self.bind('<Destroy>', lambda e: self._safe_unbind_wheel())

        pad = tk.Frame(wrapper, bg='#ffffff')
        pad.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)

        tk.Label(pad, text="⚙️  Settings",
                 font=('Segoe UI', 20, 'bold'),
                 bg='#ffffff', fg='#1a1a2e').pack(anchor='w')
        tk.Label(pad,
                 text="Edit your store information. Changes save to "
                      "the server immediately.",
                 font=('Segoe UI', 10),
                 bg='#ffffff', fg='#6c757d').pack(anchor='w', pady=(4, 20))
        tk.Frame(pad, bg='#e9ecef', height=1).pack(fill='x', pady=10)

        form_card = tk.Frame(pad, bg='#f8f9fa',
                             highlightbackground='#e9ecef',
                             highlightthickness=1)
        form_card.pack(fill='x', pady=10)
        form_inner = tk.Frame(form_card, bg='#f8f9fa')
        form_inner.pack(fill='x', padx=24, pady=20)

        tk.Label(form_inner, text="Store Information",
                 font=('Segoe UI', 13, 'bold'),
                 bg='#f8f9fa', fg='#1a1a2e').pack(anchor='w',
                                                    pady=(0, 12))

        def field(parent, label, initial=''):
            row = tk.Frame(parent, bg='#f8f9fa')
            row.pack(fill='x', pady=6)
            tk.Label(row, text=label, width=16, anchor='w',
                     font=('Segoe UI', 9, 'bold'),
                     bg='#f8f9fa', fg='#495057').pack(side=tk.LEFT)
            e = tk.Entry(row, font=('Segoe UI', 10),
                         bg='#ffffff', relief='flat', bd=0,
                         highlightthickness=1,
                         highlightbackground='#dee2e6',
                         highlightcolor=self.ACCENT)
            e.pack(side=tk.LEFT, fill='x', expand=True,
                   ipady=8, ipadx=6, padx=(0, 4))
            if initial:
                e.insert(0, str(initial))
            return e

        name_e = field(form_inner, "Store Name",
                       self._store_info['store_name'])
        addr_e = field(form_inner, "Address",
                       self._store_info['store_address'])
        phone_e = field(form_inner, "Phone",
                        self._store_info['store_phone'])
        email_e = field(form_inner, "Email",
                        self._store_info['store_email'])
        tax_e = field(form_inner, "Tax Rate (%)",
                      self._store_info['tax_rate'])
        low_e = field(form_inner, "Low Stock Alert",
                      self._store_info['low_stock_threshold'])
        footer_e = field(form_inner, "Receipt Footer",
                         self._store_info['receipt_footer'])

        status_label = tk.Label(form_inner, text="",
                                font=('Segoe UI', 9),
                                bg='#f8f9fa', fg='#6c757d',
                                anchor='w')
        status_label.pack(fill='x', pady=(10, 0))

        def save_store_settings():
            new_name = name_e.get().strip()
            if not new_name:
                status_label.config(
                    text="Store Name cannot be empty.", fg='#dc3545')
                return

            payload = {
                'store_name': new_name,
                'store_address': addr_e.get().strip(),
                'store_phone': phone_e.get().strip(),
                'store_email': email_e.get().strip(),
                'tax_rate': tax_e.get().strip(),
                'low_stock_threshold': low_e.get().strip(),
                'receipt_footer': footer_e.get().strip(),
            }

            status_label.config(text="Saving…", fg='#0d6efd')

            def task():
                return Api.put(self.api_url, '/admin/settings',
                               token=self.token,
                               json={'settings': payload},
                               timeout=15)

            def ok(data):
                if data.get('success'):
                    status_label.config(
                        text="✓ Saved successfully.", fg='#198754')
                    toast(self, "Store info saved", "success")
                    self._store_info['store_name'] = new_name
                    self._store_info['store_address'] = payload['store_address']
                    self._store_info['store_phone'] = payload['store_phone']
                    self._store_info['store_email'] = payload['store_email']
                    self._refresh_header_store_name()
                else:
                    status_label.config(
                        text=(f"Save failed: "
                              f"{data.get('message', 'Unknown error')}"),
                        fg='#dc3545')

            def err(exc):
                status_label.config(text=f"Save failed: {exc}",
                                    fg='#dc3545')

            async_call(widget=self, task=task,
                       on_success=ok, on_error=err)

        save_row = tk.Frame(form_inner, bg='#f8f9fa')
        save_row.pack(fill='x', pady=(14, 0))

        tk.Button(save_row, text="💾  Save Changes",
                  font=('Segoe UI', 10, 'bold'),
                  bg=self.ACCENT, fg='white',
                  relief='flat', bd=0, cursor='hand2',
                  padx=22, pady=10,
                  activebackground=self.ACCENT_DARK,
                  activeforeground='white',
                  command=save_store_settings).pack(side=tk.LEFT)

        # ── Network info card ──
        tk.Frame(pad, bg='#e9ecef', height=1).pack(fill='x', pady=18)

        net_card = tk.Frame(pad, bg='#f8f9fa',
                            highlightbackground='#e9ecef',
                            highlightthickness=1)
        net_card.pack(fill='x', pady=10)
        net_inner = tk.Frame(net_card, bg='#f8f9fa')
        net_inner.pack(fill='x', padx=24, pady=20)

        tk.Label(net_inner, text="Network Information",
                 font=('Segoe UI', 13, 'bold'),
                 bg='#f8f9fa', fg='#1a1a2e').pack(anchor='w',
                                                    pady=(0, 12))

        net_rows = [
            ("Local URL", self._local_url),
            ("LAN URL", self._lan_url),
            ("Public IP", self._public_ip or "Detecting…"),
            ("Logged in as", self.user.get('username', 'Unknown')),
            ("Role", self.user.get('role', 'unknown').title()),
        ]
        for label, value in net_rows:
            row = tk.Frame(net_inner, bg='#f8f9fa')
            row.pack(fill='x', pady=4)
            tk.Label(row, text=label, width=16, anchor='w',
                     font=('Segoe UI', 9, 'bold'),
                     bg='#f8f9fa', fg='#495057').pack(side=tk.LEFT)
            tk.Label(row, text=str(value), anchor='w',
                     font=('Segoe UI', 9),
                     bg='#f8f9fa', fg='#212529',
                     wraplength=560, justify='left'
                     ).pack(side=tk.LEFT, fill='x', expand=True)

        tk.Frame(pad, bg='#e9ecef', height=1).pack(fill='x', pady=18)
        tk.Label(pad, text="Quick Actions",
                 font=('Segoe UI', 13, 'bold'),
                 bg='#ffffff', fg='#1a1a2e').pack(anchor='w',
                                                    pady=(0, 10))

        actions_row = tk.Frame(pad, bg='#ffffff')
        actions_row.pack(fill='x')

        def action_btn(text, bg, cmd):
            return tk.Button(actions_row, text=text,
                             font=('Segoe UI', 10),
                             bg=bg, fg='white',
                             relief='flat', bd=0, cursor='hand2',
                             padx=20, pady=10,
                             activebackground='#495057',
                             activeforeground='white',
                             command=cmd)

        action_btn("🌐  Open Web App", '#198754',
                   lambda: webbrowser.open(self._lan_url)
                   ).pack(side=tk.LEFT, padx=(0, 8))
        action_btn("🚪  Logout", '#dc3545',
                   self.confirm_logout).pack(side=tk.LEFT, padx=8)

        tk.Frame(pad, bg='#ffffff', height=30).pack(fill='x')

        pad.update_idletasks()
        _on_wrapper_configure()

    def _safe_unbind_wheel(self):
        try:
            self.unbind_all('<MouseWheel>')
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════
    # LOGOUT
    # ═════════════════════════════════════════════════════════
    def confirm_logout(self):
        if not messagebox.askyesno("Logout",
                                   "Are you sure you want to logout?"):
            return
        try:
            self.on_logout()
        except Exception as e:
            log.error("Logout failed: %s", e, exc_info=True)
