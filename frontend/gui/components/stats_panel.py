"""
Dashboard statistics panel for the GUI.
Auto-refreshing, cached, async. Includes a "Web App Access" card
at the bottom that shows the local and LAN URLs.
"""

import sys
import time
from pathlib import Path

import tkinter as tk
from tkinter import ttk

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from frontend.gui.api import Api
from frontend.gui.config import get_api_url
from frontend.gui.logger import get_logger
from frontend.gui.ui import async_call

log = get_logger(__name__)


def detect_lan_ip() -> str:
    import socket
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


def get_local_url(port: int = 5000) -> str:
    return f"http://127.0.0.1:{port}"


def get_lan_url(port: int = 5000) -> str:
    return f"http://{detect_lan_ip()}:{port}"


# ══════════════════
# WEB ACCESS CARD
# ══════════════════

class WebAccessCard(tk.Frame):

    ACCENT = '#2d6a4f'
    BG_SOFT = '#f0fdf4'
    BORDER = '#52b788'
    TEXT = '#1a1a2e'
    TEXT_MUTED = '#6c757d'
    DANGER = '#dc3545'

    def __init__(self, parent, port: int = 5000, **kwargs):
        super().__init__(parent, bg='#f0f4f8', **kwargs)
        self.port = port
        self._build()

    def _build(self):
        card = tk.Frame(
            self,
            bg=self.BG_SOFT,
            highlightbackground=self.BORDER,
            highlightthickness=2,
        )
        card.pack(fill='x', padx=4, pady=4)

        inner = tk.Frame(card, bg=self.BG_SOFT)
        inner.pack(fill='x', padx=20, pady=16)

        header = tk.Frame(inner, bg=self.BG_SOFT)
        header.pack(fill='x')

        tk.Label(
            header, text="📱  Web App Access",
            font=('Segoe UI Semibold', 13),
            bg=self.BG_SOFT, fg=self.TEXT,
        ).pack(side=tk.LEFT)

        tk.Label(
            header, text="Same WiFi only",
            font=('Segoe UI', 8, 'italic'),
            bg=self.BG_SOFT, fg=self.TEXT_MUTED,
        ).pack(side=tk.RIGHT)

        tk.Label(
            inner,
            text="Open this address in any browser on the same WiFi:",
            font=('Segoe UI', 9),
            bg=self.BG_SOFT, fg=self.TEXT_MUTED, anchor='w',
        ).pack(fill='x', pady=(10, 6))

        # ── Local URL row ──
        local_row = tk.Frame(inner, bg='#ffffff',
                             highlightbackground=self.BORDER,
                             highlightthickness=1)
        local_row.pack(fill='x', pady=(0, 6))

        tk.Label(local_row, text="Local:",
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg=self.TEXT_MUTED
                 ).pack(side=tk.LEFT, padx=(10, 4), pady=6)

        self.local_url_var = tk.StringVar(value=get_local_url(self.port))
        tk.Entry(
            local_row,
            textvariable=self.local_url_var,
            font=('Consolas', 12, 'bold'),
            bg='#ffffff', fg=self.ACCENT,
            relief='flat', bd=0,
            state='readonly',
            readonlybackground='#ffffff',
        ).pack(side=tk.LEFT, fill='x', expand=True, ipady=6, padx=(0, 8))

        tk.Button(
            local_row, text="📋",
            font=('Segoe UI', 9),
            bg=self.ACCENT, fg='white',
            relief='flat', bd=0, cursor='hand2',
            padx=10, pady=4,
            activebackground=self.ACCENT, activeforeground='white',
            command=self._copy_local,
        ).pack(side=tk.RIGHT, padx=(0, 6))

        # ── LAN URL row ──
        lan_row = tk.Frame(inner, bg='#ffffff',
                           highlightbackground=self.BORDER,
                           highlightthickness=1)
        lan_row.pack(fill='x')

        tk.Label(lan_row, text="LAN:",
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg=self.TEXT_MUTED
                 ).pack(side=tk.LEFT, padx=(10, 4), pady=6)

        self.lan_url_var = tk.StringVar(value=get_lan_url(self.port))
        tk.Entry(
            lan_row,
            textvariable=self.lan_url_var,
            font=('Consolas', 12, 'bold'),
            bg='#ffffff', fg=self.ACCENT,
            relief='flat', bd=0,
            state='readonly',
            readonlybackground='#ffffff',
        ).pack(side=tk.LEFT, fill='x', expand=True, ipady=6, padx=(0, 8))

        tk.Button(
            lan_row, text="📋",
            font=('Segoe UI', 9),
            bg=self.ACCENT, fg='white',
            relief='flat', bd=0, cursor='hand2',
            padx=10, pady=4,
            activebackground=self.ACCENT, activeforeground='white',
            command=self._copy_lan,
        ).pack(side=tk.RIGHT, padx=(0, 6))

        # ── Buttons ──
        btn_row = tk.Frame(inner, bg=self.BG_SOFT)
        btn_row.pack(fill='x', pady=(12, 0))

        self._button(btn_row, "🌐  Open in Browser", self._open,
                     bg='#0d6efd').pack(side=tk.LEFT, expand=True,
                                         fill='x', padx=(0, 4))
        self._button(btn_row, "🔄  Refresh URLs", self.refresh,
                     bg='#6c757d').pack(side=tk.LEFT, expand=True,
                                         fill='x', padx=(4, 0))

        # ── Status ──
        self.status = tk.Label(
            inner, text="",
            font=('Segoe UI', 8),
            bg=self.BG_SOFT, fg=self.ACCENT,
        )
        self.status.pack(fill='x', pady=(10, 0))

        self.refresh()

    def _button(self, parent, text, cmd, bg):
        return tk.Button(
            parent, text=text,
            font=('Segoe UI', 9, 'bold'),
            bg=bg, fg='white',
            activebackground=bg, activeforeground='white',
            relief='flat', bd=0, cursor='hand2',
            padx=10, pady=8, command=cmd,
        )

    def refresh(self):
        local = get_local_url(self.port)
        lan = get_lan_url(self.port)
        self.local_url_var.set(local)
        self.lan_url_var.set(lan)

        if lan.startswith("http://127.0.0.1"):
            self.status.config(
                text="⚠️  No LAN connection detected. "
                     "Connect to WiFi to enable remote access.",
                fg=self.DANGER,
            )
        else:
            self.status.config(
                text="✅  Ready — any device on this WiFi can connect.",
                fg=self.ACCENT,
            )

    def _copy_local(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.local_url_var.get())
            self.status.config(text="✅  Local URL copied!", fg=self.ACCENT)
            self.after(2500, self.refresh)
        except Exception as e:
            self.status.config(text=f"Copy failed: {e}", fg=self.DANGER)

    def _copy_lan(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.lan_url_var.get())
            self.status.config(text="✅  LAN URL copied!", fg=self.ACCENT)
            self.after(2500, self.refresh)
        except Exception as e:
            self.status.config(text=f"Copy failed: {e}", fg=self.DANGER)

    def _open(self):
        try:
            import webbrowser
            webbrowser.open(self.local_url_var.get())
            self.status.config(text="✅  Opening in browser...", fg=self.ACCENT)
            self.after(2500, self.refresh)
        except Exception as e:
            self.status.config(text=f"Open failed: {e}", fg=self.DANGER)


# ════════════
# STATS PANEL
# ════════════

class StatsPanel(tk.Frame):
    CACHE_TTL = 25
    AUTO_REFRESH_MS = 30000

    def __init__(self, parent, api_url=None, token=None, user=None):
        super().__init__(parent)

        self.parent = parent
        base = api_url or get_api_url()
        self.api_url = base.replace("localhost", "127.0.0.1")
        self.token = token
        self.user = user or {}
        self.user_role = self.user.get('role', 'owner')

        self._loading = False
        self._cached_stats = None
        self._cached_at = 0.0
        self._refresh_job = None

        self.setup_ui()

        # ── Schedule the initial load + auto-refresh ──
        self.after(50, self.load_stats_async)
        self._schedule_refresh()

    # ═══════════
    # LIFECYCLE
    # ═══════════

    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def destroy(self):
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        try:
            super().destroy()
        except Exception:
            pass

    def _schedule_refresh(self):
        if not self._alive():
            return
        try:
            self._refresh_job = self.after(
                self.AUTO_REFRESH_MS, self._auto_refresh)
        except Exception:
            self._refresh_job = None

    def _auto_refresh(self):
        self._refresh_job = None
        if not self._alive():
            return
        self._cached_at = 0.0
        self.load_stats_async()
        self._schedule_refresh()

    def refresh(self):
        if not self._alive():
            return
        now = time.time()
        if (self._cached_stats is not None
                and (now - self._cached_at) < self.CACHE_TTL):
            self._render(self._cached_stats)
            return
        self.load_stats_async()

    # ════
    # UI
    # ════

    def setup_ui(self):
        self.configure(bg='#f0f4f8')

        # ── Scrollable container ──
        outer = tk.Frame(self, bg='#f0f4f8')
        outer.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(outer, bg='#f0f4f8', highlightthickness=0)
        sb = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill='y')

        container = tk.Frame(canvas, bg='#f0f4f8')
        window_id = canvas.create_window((0, 0), window=container, anchor='nw')

        def _update_sr(event=None):
            try:
                canvas.configure(scrollregion=canvas.bbox('all'))
            except Exception:
                pass

        def _resize(event):
            try:
                canvas.itemconfig(window_id, width=event.width)
            except Exception:
                pass

        container.bind('<Configure>', _update_sr)
        canvas.bind('<Configure>', _resize)

        def _on_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
            except Exception:
                pass

        canvas.bind_all('<MouseWheel>', _on_mousewheel)

        # ── Content ──
        pad = tk.Frame(container, bg='#f0f4f8')
        pad.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tk.Label(pad, text="📊  Dashboard",
                 font=('Segoe UI', 16, 'bold'),
                 bg='#f0f4f8', fg='#1a1a2e'
                 ).pack(anchor='w', pady=(0, 4))

        tk.Label(pad, text="Live overview of your store",
                 font=('Segoe UI', 9),
                 bg='#f0f4f8', fg='#6c757d'
                 ).pack(anchor='w', pady=(0, 16))

        # ── Stat cards ──
        card_frame = tk.Frame(pad, bg='#f0f4f8')
        card_frame.pack(fill='x', pady=(0, 20))

        self.stats_cards = {}
        stats = [
            ("📈  Today's Sales",    'today_sales',    '#2d6a4f'),
            ("💰  Monthly Revenue",  'month_revenue',  '#198754'),
            ("📦  Total Products",   'total_products', '#0dcaf0'),
            ("⚠️  Low Stock Items",  'low_stock',      '#ffc107'),
        ]

        for i, (title, key, color) in enumerate(stats):
            card = tk.Frame(card_frame, bg='#ffffff',
                            highlightbackground='#e9ecef',
                            highlightthickness=1)
            card.grid(row=0, column=i,
                      padx=(0 if i == 0 else 10, 0),
                      sticky='nsew')
            card_frame.grid_columnconfigure(i, weight=1)

            tk.Label(card, text=title, font=('Segoe UI', 9),
                     bg='#ffffff', fg='#6c757d'
                     ).pack(anchor='w', padx=16, pady=(14, 2))

            value_label = tk.Label(card, text='—',
                                    font=('Segoe UI', 22, 'bold'),
                                    fg=color, bg='#ffffff')
            value_label.pack(anchor='w', padx=16, pady=(0, 16))
            self.stats_cards[key] = value_label

        # ── Web Access card ──
        try:
            web_card = WebAccessCard(pad, port=5000)
            web_card.pack(fill='x', pady=(10, 0))
        except Exception as e:
            log.warning("WebAccessCard failed: %s", e)

    # ═════════════════════════════════════════════════════════
    # DATA — this is the method your traceback said was missing
    # ═════════════════════════════════════════════════════════

    def load_stats_async(self):
        """Kick off an async fetch of dashboard stats."""
        if self._loading or not self._alive():
            return
        self._loading = True

        if self.user_role == 'owner':
            task = self._fetch_owner_stats
        else:
            task = self._fetch_cashier_stats

        async_call(
            widget=self,
            task=task,
            on_success=self._on_stats_loaded,
            on_error=self._on_stats_error,
            on_finally=self._reset_loading,
        )

    def _reset_loading(self):
        self._loading = False

    def _fetch_owner_stats(self):
        data = Api.get(self.api_url, '/reports/analytics',
                        token=self.token, timeout=15)
        if not data.get('success'):
            raise RuntimeError(data.get('message', 'Failed to load stats'))
        return data.get('data', {}) or {}

    def _fetch_cashier_stats(self):
        s = Api.get(self.api_url, '/sales/stats',
                    token=self.token, params={'period': 'today'},
                    timeout=10)
        p = Api.get(self.api_url, '/products',
                    token=self.token, params={'per_page': 500},
                    timeout=10)

        today_count = 0
        today_revenue = 0.0
        if s.get('success'):
            d = s.get('data', {}) or {}
            today_count = d.get('total_sales', 0)
            today_revenue = d.get('total_revenue', 0)

        total = 0
        low = 0
        if p.get('success'):
            items = (p.get('data') or {}).get('items') or []
            total = len(items)
            low = sum(1 for x in items
                      if 0 < (x.get('stock_quantity') or 0)
                      <= (x.get('min_stock_level') or 10))

        return {
            'today': {'sales_count': today_count,
                       'revenue': today_revenue},
            'month': {'revenue': today_revenue},
            'inventory': {
                'total_products': total,
                'low_stock_products': low,
            },
        }

    # ═══════
    # RENDER
    # ═══════

    def _on_stats_loaded(self, stats):
        self._cached_stats = stats
        self._cached_at = time.time()
        self._render(stats)

    def _on_stats_error(self, exc):
        if not self._alive():
            return
        msg = f"⚠ {exc}" if str(exc) else "⚠ Failed"
        for k, lbl in self.stats_cards.items():
            try:
                lbl.config(text=msg[:24], fg='#dc3545')
            except Exception:
                pass

    def _render(self, stats):
        if not self._alive():
            return

        today = stats.get('today', {}) or {}
        month = stats.get('month', {}) or {}
        inv = stats.get('inventory', {}) or {}

        def setval(key, text, fg=None):
            lbl = self.stats_cards.get(key)
            if not lbl:
                return
            try:
                if fg:
                    lbl.config(text=text, fg=fg)
                else:
                    lbl.config(text=text)
            except Exception:
                pass

        setval('today_sales', str(today.get('sales_count', 0)))
        setval('month_revenue', f"₱{(month.get('revenue', 0) or 0):,.2f}")
        setval('total_products', str(inv.get('total_products', 0)))

        low = inv.get('low_stock_products', 0) or 0
        setval('low_stock', str(low),
                '#dc3545' if low > 0 else '#198754')