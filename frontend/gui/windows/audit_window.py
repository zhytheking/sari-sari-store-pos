"""
Audit Log window for the GUI.

Owner-only. Fetches from /api/v1/audit/logs and displays in a
Treeview with filters.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from frontend.gui.api import Api
from frontend.gui.config import get_api_url
from frontend.gui.ui import async_call, toast


class AuditWindow(tk.Frame):
    ACCENT = '#2d6a4f'
    ACCENT_DARK = '#1b4332'

    def __init__(self, parent, api_url, token):
        super().__init__(parent)
        self.parent = parent
        base = api_url or get_api_url()
        self.api_url = base.replace("localhost", "127.0.0.1")
        self.token = token
        self._page = 1
        self._per_page = 30
        self._loading = False
        self._filters = {
            'start_date': '',
            'end_date': '',
            'category': '',
            'result': '',
            'search': '',
        }

        self.setup_ui()
        self.after(100, lambda: self.load_logs(1))

    def _alive(self):
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    # ═════════════════════════════════════════════════════════
    # UI
    # ═════════════════════════════════════════════════════════
    def setup_ui(self):
        self.configure(bg='#f0f4f8')
        self.pack(fill=tk.BOTH, expand=True)

        # Header
        top = tk.Frame(self, bg='#f0f4f8')
        top.pack(fill='x', padx=16, pady=12)

        tk.Label(top, text="📜  Audit Log",
                 font=('Segoe UI', 16, 'bold'),
                 bg='#f0f4f8', fg='#1a1a2e').pack(side=tk.LEFT)

        self.count_label = tk.Label(top, text="",
                                     font=('Segoe UI', 9),
                                     bg='#f0f4f8', fg='#8a94a0')
        self.count_label.pack(side=tk.LEFT, padx=12)

        tk.Button(top, text="🔄  Refresh",
                  font=('Segoe UI', 9),
                  bg='#ffffff', fg='#495057',
                  relief='flat', bd=0, cursor='hand2',
                  padx=14, pady=6,
                  activebackground='#e9ecef',
                  command=self.refresh).pack(side=tk.RIGHT)

        # Filters
        filters = tk.Frame(self, bg='#ffffff',
                            highlightbackground='#e9ecef',
                            highlightthickness=1)
        filters.pack(fill='x', padx=16, pady=(0, 12))
        fi = tk.Frame(filters, bg='#ffffff')
        fi.pack(fill='x', padx=16, pady=12)

        tk.Label(fi, text="From:",
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg='#495057').pack(side=tk.LEFT)
        self.from_entry = tk.Entry(fi, width=12, font=('Segoe UI', 10))
        self.from_entry.pack(side=tk.LEFT, padx=(4, 12))
        week_ago = datetime.now() - timedelta(days=7)
        self.from_entry.insert(0, week_ago.strftime('%Y-%m-%d'))

        tk.Label(fi, text="To:",
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg='#495057').pack(side=tk.LEFT)
        self.to_entry = tk.Entry(fi, width=12, font=('Segoe UI', 10))
        self.to_entry.pack(side=tk.LEFT, padx=(4, 12))
        self.to_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))

        tk.Label(fi, text="Category:",
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg='#495057').pack(side=tk.LEFT)
        self.category_var = tk.StringVar(value='All')
        cat_combo = ttk.Combobox(
            fi, textvariable=self.category_var,
            values=['All', 'auth', 'sale', 'stock',
                    'product', 'user', 'settings', 'system'],
            state='readonly', width=12, font=('Segoe UI', 9))
        cat_combo.pack(side=tk.LEFT, padx=(4, 12))

        tk.Label(fi, text="Result:",
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg='#495057').pack(side=tk.LEFT)
        self.result_var = tk.StringVar(value='All')
        res_combo = ttk.Combobox(
            fi, textvariable=self.result_var,
            values=['All', 'success', 'failure'],
            state='readonly', width=10, font=('Segoe UI', 9))
        res_combo.pack(side=tk.LEFT, padx=(4, 12))

        tk.Button(fi, text="🔍  Apply",
                  font=('Segoe UI', 9, 'bold'),
                  bg=self.ACCENT, fg='white',
                  relief='flat', bd=0, cursor='hand2',
                  padx=12, pady=6,
                  activebackground=self.ACCENT_DARK,
                  activeforeground='white',
                  command=self.apply_filters).pack(side=tk.LEFT)

        tk.Button(fi, text="↺  Reset",
                  font=('Segoe UI', 9),
                  bg='#e9ecef', fg='#495057',
                  relief='flat', bd=0, cursor='hand2',
                  padx=12, pady=6,
                  command=self.reset_filters).pack(side=tk.LEFT, padx=(6, 0))

        # Treeview
        wrapper = tk.Frame(self, bg='#ffffff',
                            highlightbackground='#e9ecef',
                            highlightthickness=1)
        wrapper.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        style = ttk.Style()
        try:
            style.configure("Audit.Treeview",
                            background="#ffffff",
                            fieldbackground="#ffffff",
                            foreground="#212529",
                            rowheight=26,
                            font=('Segoe UI', 9))
            style.configure("Audit.Treeview.Heading",
                            background="#f8f9fa",
                            foreground="#495057",
                            font=('Segoe UI', 9, 'bold'),
                            relief='flat')
            style.map("Audit.Treeview",
                      background=[('selected', '#d8f3dc')],
                      foreground=[('selected', '#1b4332')])
        except Exception:
            pass

        self.tree = ttk.Treeview(
            wrapper,
            columns=('Time', 'User', 'Category', 'Action',
                     'Details', 'Result', 'IP'),
            show='headings', style="Audit.Treeview")

        for col, w, anchor in [
            ('Time', 140, 'w'),
            ('User', 110, 'w'),
            ('Category', 90, 'center'),
            ('Action', 150, 'w'),
            ('Details', 420, 'w'),
            ('Result', 80, 'center'),
            ('IP', 110, 'w'),
        ]:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor=anchor,
                             stretch=(col == 'Details'))

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(wrapper, orient=tk.VERTICAL,
                            command=self.tree.yview)
        sb.pack(side=tk.RIGHT, fill='y')
        self.tree.configure(yscrollcommand=sb.set)

        self.tree.tag_configure('failure', foreground='#dc3545')
        self.tree.tag_configure('success', foreground='#198754')

        # Pagination footer
        footer = tk.Frame(self, bg='#ffffff',
                           highlightbackground='#e9ecef',
                           highlightthickness=1)
        footer.pack(fill='x', padx=16, pady=(0, 16))
        fin = tk.Frame(footer, bg='#ffffff')
        fin.pack(fill='x', padx=16, pady=10)

        self.pagination_label = tk.Label(fin, text="",
                                          font=('Segoe UI', 9),
                                          bg='#ffffff', fg='#6c757d')
        self.pagination_label.pack(side=tk.LEFT)

        self.prev_btn = tk.Button(fin, text="◀  Prev",
                                    font=('Segoe UI', 9),
                                    bg='#e9ecef', fg='#495057',
                                    relief='flat', bd=0, cursor='hand2',
                                    padx=12, pady=4,
                                    command=self.prev_page)
        self.prev_btn.pack(side=tk.RIGHT)

        self.next_btn = tk.Button(fin, text="Next  ▶",
                                    font=('Segoe UI', 9),
                                    bg='#e9ecef', fg='#495057',
                                    relief='flat', bd=0, cursor='hand2',
                                    padx=12, pady=4,
                                    command=self.next_page)
        self.next_btn.pack(side=tk.RIGHT, padx=(0, 6))

    # ═════════════════════════════════════════════════════════
    # ACTIONS
    # ═════════════════════════════════════════════════════════
    def refresh(self):
        self.load_logs(self._page)

    def apply_filters(self):
        self._filters['start_date'] = self.from_entry.get().strip()
        self._filters['end_date'] = self.to_entry.get().strip()
        cat = self.category_var.get()
        res = self.result_var.get()
        self._filters['category'] = '' if cat == 'All' else cat
        self._filters['result'] = '' if res == 'All' else res
        self.load_logs(1)

    def reset_filters(self):
        week_ago = datetime.now() - timedelta(days=7)
        self.from_entry.delete(0, tk.END)
        self.from_entry.insert(0, week_ago.strftime('%Y-%m-%d'))
        self.to_entry.delete(0, tk.END)
        self.to_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))
        self.category_var.set('All')
        self.result_var.set('All')
        self._filters = {
            'start_date': self.from_entry.get().strip(),
            'end_date': self.to_entry.get().strip(),
            'category': '',
            'result': '',
            'search': '',
        }
        self.load_logs(1)

    def prev_page(self):
        if self._page > 1:
            self.load_logs(self._page - 1)

    def next_page(self):
        self.load_logs(self._page + 1)

    # ═════════════════════════════════════════════════════════
    # DATA
    # ═════════════════════════════════════════════════════════
    def load_logs(self, page):
        if self._loading or not self._alive():
            return
        self._loading = True
        self._page = page

        try:
            self.tree.delete(*self.tree.get_children())
            self.tree.insert('', 'end', iid='__loading__',
                             values=('⏳ Loading...', '', '', '', '', '', ''))
        except Exception:
            pass

        params = {
            'page': page,
            'per_page': self._per_page,
        }
        if self._filters['start_date']:
            params['start_date'] = self._filters['start_date']
        if self._filters['end_date']:
            params['end_date'] = self._filters['end_date']
        if self._filters['category']:
            params['category'] = self._filters['category']
        if self._filters['result']:
            params['result'] = self._filters['result']
        if self._filters['search']:
            params['search'] = self._filters['search']

        def task():
            return Api.get(self.api_url, '/audit/logs',
                           token=self.token, params=params, timeout=20)

        def ok(data):
            self._loading = False
            if not self._alive():
                return
            if data.get('success'):
                payload = data.get('data') or {}
                self._render(payload.get('items') or [])
                self._update_pagination(payload.get('pagination') or {})
            else:
                toast(self, data.get('message', 'Failed to load'), 'error')

        def err(exc):
            self._loading = False
            if not self._alive():
                return
            toast(self, f"Failed: {exc}", 'error')

        async_call(widget=self, task=task, on_success=ok, on_error=err)

    def _render(self, items):
        if not self._alive():
            return
        try:
            self.tree.delete(*self.tree.get_children())
        except Exception:
            return

        if not items:
            self.tree.insert('', 'end',
                             values=('No entries found', '', '', '', '', '', ''))
            self.count_label.config(text="0 entries")
            return

        for e in items:
            time_str = self._format_time(e.get('timestamp'))
            user = e.get('username') or 'System'
            cat = e.get('category') or 'system'
            action = e.get('action') or ''
            details = e.get('details') or ''
            result = e.get('result') or 'success'
            ip = e.get('ip_address') or '—'

            if len(details) > 80:
                details = details[:77] + '...'

            tag = 'failure' if result == 'failure' else 'success'
            self.tree.insert('', 'end',
                             values=(time_str, user, cat, action,
                                     details, result, ip),
                             tags=(tag,))

        self.count_label.config(text=f"{len(items)} entries on this page")

    def _format_time(self, ts):
        if not ts:
            return ''
        try:
            s = str(ts).replace(' ', 'T')
            if 'Z' not in s and '+' not in s:
                s += 'Z'
            d = datetime.fromisoformat(s.replace('Z', '+00:00'))
            return d.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return str(ts)

    def _update_pagination(self, pagination):
        if not self._alive():
            return
        page = pagination.get('page', 1)
        pages = pagination.get('pages', 1)
        total = pagination.get('total', 0)
        per_page = pagination.get('per_page', self._per_page)

        start = (page - 1) * per_page + 1 if total > 0 else 0
        end = min(page * per_page, total)

        self.pagination_label.config(
            text=f"Showing {start}-{end} of {total} entries  ·  Page {page} of {pages}"
        )

        try:
            self.prev_btn.config(state='normal' if page > 1 else 'disabled')
            self.next_btn.config(state='normal' if page < pages else 'disabled')
        except Exception:
            pass
