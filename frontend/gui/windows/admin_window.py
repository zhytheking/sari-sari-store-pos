"""
Admin window — Reports, Accounts (Users), Products tabs.
Owner-only. Reusable with `single_tab=True` + `initial_tab='users'`.

Fixes:
  - Added delete_user(), reset_user_password() methods that were
    referenced by buttons but never defined.
  - Add Product dialog: button row is now packed with side=BOTTOM
    BEFORE the form, so Save/Cancel are always visible.
  - Reports user dropdown is now populated correctly on load.
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from frontend.gui.api import Api
from frontend.gui.config import get_api_url
from frontend.gui.ui import async_call, toast


class AdminWindow(tk.Frame):

    ACCENT = '#2d6a4f'
    ACCENT_DARK = '#1b4332'

    def __init__(self, parent, api_url=None, token=None,
                 initial_tab='reports', single_tab=False):
        super().__init__(parent)
        self.parent = parent
        self.api_url = api_url or get_api_url()
        self.token = token
        self.initial_tab = initial_tab
        self.single_tab = single_tab

        self._loading_users = False
        self._loading_products = False

        self.users = []
        self.products = []
        self.products_by_id = {}

        self.setup_ui()

    # ═══════════
    # LIFECYCLE
    # ═══════════

    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    # ═══
    # UI
    # ═══

    def setup_ui(self):
        self.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Reports tab
        if not self.single_tab or self.initial_tab == 'reports':
            self.reports_tab = tk.Frame(self.notebook, bg='#f8f9fa')
            self.notebook.add(self.reports_tab, text="📊  Reports")
            self.setup_reports_tab()
        else:
            self.reports_tab = None

        # Users tab
        if not self.single_tab or self.initial_tab == 'users':
            self.users_tab = tk.Frame(self.notebook, bg='#f8f9fa')
            self.notebook.add(self.users_tab, text="ℹ️  Accounts")
            self.setup_users_tab()
        else:
            self.users_tab = None

        # Products tab
        if not self.single_tab or self.initial_tab == 'products':
            self.products_tab = tk.Frame(self.notebook, bg='#f8f9fa')
            self.notebook.add(self.products_tab, text="📦  Products")
            self.setup_products_tab()
        else:
            self.products_tab = None

        # Load users in background (needed for the reports dropdown)
        self.after(120, self._load_users_async)

        if self.initial_tab == 'users' and self.users_tab:
            self.notebook.select(self.users_tab)
        elif self.initial_tab == 'products' and self.products_tab:
            self.notebook.select(self.products_tab)

    def select_tab(self, name):
        mapping = {
            'reports': getattr(self, 'reports_tab', None),
            'users': getattr(self, 'users_tab', None),
            'products': getattr(self, 'products_tab', None),
        }
        tab = mapping.get(name)
        if tab:
            try:
                self.notebook.select(tab)
            except Exception:
                pass

    # ════════════
    # REPORTS TAB
    # ════════════

    def setup_reports_tab(self):
        filters = tk.Frame(self.reports_tab, bg='#f8f9fa')
        filters.pack(fill='x', pady=10, padx=10)

        row1 = tk.Frame(filters, bg='#f8f9fa')
        row1.pack(fill='x')

        tk.Label(row1, text="Date Range:",
                 font=('Segoe UI', 10, 'bold'),
                 bg='#f8f9fa').pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(row1, text="From:", bg='#f8f9fa').pack(side=tk.LEFT)
        self.start_date = tk.Entry(row1, width=14, font=('Segoe UI', 10))
        self.start_date.pack(side=tk.LEFT, padx=(4, 12))
        default_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        self.start_date.insert(0, default_start)

        tk.Label(row1, text="To:", bg='#f8f9fa').pack(side=tk.LEFT)
        self.end_date = tk.Entry(row1, width=14, font=('Segoe UI', 10))
        self.end_date.pack(side=tk.LEFT, padx=(4, 12))
        self.end_date.insert(0, datetime.now().strftime('%Y-%m-%d'))

        tk.Label(row1, text="User:", bg='#f8f9fa').pack(side=tk.LEFT)
        self.report_user_filter = tk.StringVar(value='All Users')
        self.report_user_dropdown = ttk.Combobox(
            row1, textvariable=self.report_user_filter,
            state='readonly', width=26, font=('Segoe UI', 9))
        self.report_user_dropdown['values'] = ['All Users']
        self.report_user_dropdown.pack(side=tk.LEFT, padx=(4, 12))

        tk.Button(
            row1, text="Generate Report",
            font=('Segoe UI', 10, 'bold'),
            bg=self.ACCENT, fg='white',
            relief='flat', bd=0, cursor='hand2',
            padx=16, pady=6,
            activebackground=self.ACCENT_DARK,
            activeforeground='white',
            command=self.generate_report
        ).pack(side=tk.LEFT)

        tk.Button(
            row1, text="📤  Export CSV",
            font=('Segoe UI', 10, 'bold'),
            bg='#0d6efd', fg='white',
            relief='flat', bd=0, cursor='hand2',
            padx=14, pady=6,
            activebackground='#0a58ca',
            activeforeground='white',
            command=self._export_report_csv
        ).pack(side=tk.LEFT, padx=(8, 0))

        tk.Button(
            row1, text="🔄  Refresh Users",
            font=('Segoe UI', 9),
            bg='#e9ecef', fg='#495057',
            relief='flat', bd=0, cursor='hand2',
            padx=12, pady=6,
            command=self._load_users_async
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.report_text = scrolledtext.ScrolledText(
            self.reports_tab,
            font=('Consolas', 10),
            bg='#ffffff', fg='#212529',
            relief='flat', bd=0,
            highlightthickness=1,
            highlightbackground='#dee2e6')
        self.report_text.pack(fill=tk.BOTH, expand=True,
                               padx=10, pady=(10, 10))

    # ══════════
    # USERS TAB
    # ══════════

    def setup_users_tab(self):
        top = tk.Frame(self.users_tab, bg='#f8f9fa')
        top.pack(fill='x', padx=10, pady=10)

        tk.Label(top, text="User Accounts",
                 font=('Segoe UI', 12, 'bold'),
                 bg='#f8f9fa').pack(side=tk.LEFT)

        btns = tk.Frame(top, bg='#f8f9fa')
        btns.pack(side=tk.RIGHT)

        tk.Button(btns, text="🔄  Refresh",
                  bg='#e9ecef', relief='flat', bd=0,
                  padx=12, pady=6, cursor='hand2',
                  command=self._load_users_async
                  ).pack(side=tk.LEFT, padx=4)

        tk.Button(btns, text="➕  Add User",
                  bg=self.ACCENT, fg='white', relief='flat', bd=0,
                  padx=12, pady=6, cursor='hand2',
                  command=self.add_user
                  ).pack(side=tk.LEFT, padx=4)

        tk.Button(btns, text="🗑️  Delete",
                  bg='#dc3545', fg='white', relief='flat', bd=0,
                  padx=12, pady=6, cursor='hand2',
                  command=self.delete_user
                  ).pack(side=tk.LEFT, padx=4)

        tk.Button(btns, text="🔑  Reset Password",
                  bg='#ffc107', fg='#212529', relief='flat', bd=0,
                  padx=12, pady=6, cursor='hand2',
                  command=self.reset_user_password
                  ).pack(side=tk.LEFT, padx=4)

        wrapper = tk.Frame(self.users_tab, bg='#f8f9fa')
        wrapper.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.users_tree = ttk.Treeview(
            wrapper,
            columns=('ID', 'Username', 'Full Name', 'Email',
                     'Role', 'Status'),
            show='headings', height=18)
        for col, w, anchor in [
            ('ID', 50, 'center'),
            ('Username', 120, 'w'),
            ('Full Name', 180, 'w'),
            ('Email', 180, 'w'),
            ('Role', 90, 'center'),
            ('Status', 90, 'center'),
        ]:
            self.users_tree.heading(col, text=col)
            self.users_tree.column(col, width=w, anchor=anchor)
        self.users_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(wrapper, orient=tk.VERTICAL,
                            command=self.users_tree.yview)
        sb.pack(side=tk.RIGHT, fill='y')
        self.users_tree.configure(yscrollcommand=sb.set)

    # ═════════════
    # PRODUCTS TAB
    # ═════════════

    def setup_products_tab(self):
        top = tk.Frame(self.products_tab, bg='#f8f9fa')
        top.pack(fill='x', padx=10, pady=10)

        tk.Label(top, text="Product Management",
                 font=('Segoe UI', 12, 'bold'),
                 bg='#f8f9fa').pack(side=tk.LEFT)

        btns = tk.Frame(top, bg='#f8f9fa')
        btns.pack(side=tk.RIGHT)

        tk.Button(btns, text="🔄  Refresh",
                  bg='#e9ecef', relief='flat', bd=0,
                  padx=12, pady=6, cursor='hand2',
                  command=self.load_products
                  ).pack(side=tk.LEFT, padx=4)

        tk.Button(btns, text="➕  Add Product",
                  bg=self.ACCENT, fg='white', relief='flat', bd=0,
                  padx=12, pady=6, cursor='hand2',
                  command=self.add_product
                  ).pack(side=tk.LEFT, padx=4)

        tk.Button(btns, text="🗑️  Delete",
                  bg='#dc3545', fg='white', relief='flat', bd=0,
                  padx=12, pady=6, cursor='hand2',
                  command=self.delete_product
                  ).pack(side=tk.LEFT, padx=4)

        wrapper = tk.Frame(self.products_tab, bg='#f8f9fa')
        wrapper.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.products_tree = ttk.Treeview(
            wrapper,
            columns=('ID', 'Name', 'Barcode', 'Category',
                     'Price', 'Stock', 'Status'),
            show='headings', height=18)
        for col, w, anchor in [
            ('ID', 50, 'center'),
            ('Name', 200, 'w'),
            ('Barcode', 130, 'w'),
            ('Category', 130, 'w'),
            ('Price', 90, 'e'),
            ('Stock', 70, 'center'),
            ('Status', 90, 'center'),
        ]:
            self.products_tree.heading(col, text=col)
            self.products_tree.column(col, width=w, anchor=anchor)
        self.products_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(wrapper, orient=tk.VERTICAL,
                            command=self.products_tree.yview)
        sb.pack(side=tk.RIGHT, fill='y')
        self.products_tree.configure(yscrollcommand=sb.set)

        self.notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)

    def _on_tab_changed(self, event=None):
        try:
            current = self.notebook.select()
            if (self.products_tab
                    and current == str(self.products_tab)
                    and not self.products):
                self.load_products()
        except Exception:
            pass

    # ═══════════
    # LOAD USERS
    # ═══════════

    def _load_users_async(self):
        if self._loading_users or not self._alive():
            return
        self._loading_users = True

        async_call(
            widget=self,
            task=lambda: Api.get(self.api_url, '/auth/users',
                                  token=self.token,
                                  params={'per_page': 200},
                                  timeout=15),
            on_success=self._on_users_loaded,
            on_error=lambda e: toast(self, f"Failed to load users: {e}",
                                     "error"),
            on_finally=self._reset_users_loading,
        )

    def _reset_users_loading(self):
        self._loading_users = False

    def _on_users_loaded(self, data):
        if not self._alive():
            return
        if data.get('success'):
            self.users = (data.get('data') or {}).get('items') or []
            if getattr(self, 'users_tree', None):
                self._populate_users_tree()
            if getattr(self, 'report_user_dropdown', None):
                self._populate_user_dropdown()
        else:
            toast(self, data.get('message', 'Failed to load users'), 'error')

    def _populate_users_tree(self):
        if not self._alive() or not getattr(self, 'users_tree', None):
            return
        try:
            self.users_tree.delete(*self.users_tree.get_children())
            for u in self.users:
                status = "Active" if u.get('is_active') else "Inactive"
                self.users_tree.insert(
                    '', 'end',
                    iid=str(u.get('id')),
                    values=(
                        u.get('id'),
                        u.get('username'),
                        u.get('full_name'),
                        u.get('email') or '—',
                        (u.get('role') or '').title(),
                        status,
                    ))
        except Exception as e:
            print(f"[Admin] populate users: {e}")

    def _populate_user_dropdown(self):
        if not self._alive():
            return
        try:
            choices = ['All Users']
            for u in self.users:
                label = (f"{u.get('full_name') or u.get('username')} "
                         f"({u.get('username')})")
                choices.append(label)
            self.report_user_dropdown['values'] = choices
            self.report_user_filter.set('All Users')
        except Exception as e:
            print(f"[Admin] populate dropdown: {e}")

    def _resolve_user_id_from_filter(self):
        sel = self.report_user_filter.get()
        if not sel or sel == 'All Users':
            return None
        if '(' in sel and sel.endswith(')'):
            username = sel[sel.rfind('(') + 1:-1].strip()
            for u in self.users:
                if u.get('username') == username:
                    return u.get('id')
        return None

    # ════════════════
    # GENERATE REPORT
    # ════════════════

    def generate_report(self):
        start = self.start_date.get().strip()
        end = self.end_date.get().strip()
        user_id = self._resolve_user_id_from_filter()

        if not start or not end:
            messagebox.showwarning("Missing Dates",
                                    "Select both start and end dates.")
            return

        for label, val in [("Start", start), ("End", end)]:
            try:
                datetime.strptime(val, '%Y-%m-%d')
            except ValueError:
                messagebox.showerror(
                    "Invalid Date Format",
                    f"{label} date must be YYYY-MM-DD.\nYou entered: {val}")
                return

        self.report_text.delete('1.0', tk.END)
        self.report_text.insert('1.0', "Loading report...\n")

        params = {'start_date': start, 'end_date': end}
        if user_id is not None:
            params['user_id'] = user_id

        async_call(
            widget=self,
            task=lambda: Api.get(self.api_url, '/reports/sales',
                                  token=self.token, params=params,
                                  timeout=20),
            on_success=lambda data: self._render_report(data, start, end,
                                                         user_id),
            on_error=lambda e: self._render_report_error(str(e)),
        )

    def _render_report_error(self, msg):
        if not self._alive():
            return
        try:
            self.report_text.delete('1.0', tk.END)
            self.report_text.insert('1.0', f"Error generating report:\n{msg}")
        except Exception:
            pass

    def _render_report(self, data, start, end, user_id):
        if not self._alive():
            return
        if not data.get('success'):
            self.report_text.delete('1.0', tk.END)
            self.report_text.insert(
                '1.0', f"Failed: {data.get('message', 'Unknown error')}")
            return

        report = data.get('data', {}) or {}
        summary = report.get('summary', {}) or {}
        period_data = (report.get('period_data')
                       or report.get('daily_data') or [])
        top_products = report.get('top_products', []) or []

        if user_id is None:
            user_label = "All Users"
        else:
            user_label = next(
                (f"{u.get('full_name')} ({u.get('username')})"
                 for u in self.users if u.get('id') == user_id),
                f"User ID {user_id}")

        L = []
        L.append("=" * 78)
        L.append("                          SALES REPORT".center(78))
        L.append("=" * 78)
        L.append(f"Period:      {start}  →  {end}")
        L.append(f"User:        {user_label}")
        L.append(f"Generated:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        L.append("-" * 78)
        L.append("")
        L.append("SUMMARY")
        L.append(f"  Total Sales:         {summary.get('total_sales', 0):>10}")
        L.append(f"  Total Revenue:       ₱{summary.get('total_revenue', 0):>12,.2f}")
        L.append(f"  Total Discounts:     ₱{summary.get('total_discounts', 0):>12,.2f}")
        L.append(f"  Total Taxes:         ₱{summary.get('total_taxes', 0):>12,.2f}")
        L.append(f"  Average Sale:        ₱{summary.get('average_sale', 0):>12,.2f}")
        L.append("")
        L.append("-" * 78)
        L.append("BREAKDOWN")
        L.append(f"  {'Date':<14} {'Sales':>8} {'Revenue':>14} {'Discounts':>14}")
        L.append(f"  {'-' * 14} {'-' * 8} {'-' * 14} {'-' * 14}")

        if not period_data:
            L.append("  (No sales in this range)")
        else:
            for d in period_data:
                date_val = d.get('period') or d.get('date') or '—'
                L.append(
                    f"  {str(date_val):<14} "
                    f"{d.get('sales_count', 0):>8} "
                    f"₱{d.get('revenue', 0):>12,.2f} "
                    f"₱{d.get('discounts', 0):>12,.2f}")

        L.append("")
        L.append("-" * 78)
        L.append("TOP PRODUCTS")
        if not top_products:
            L.append("  (No product data)")
        else:
            L.append(f"  {'#':<4} {'Product':<32} {'Qty':>8} {'Revenue':>16}")
            L.append(f"  {'-' * 4} {'-' * 32} {'-' * 8} {'-' * 16}")
            for i, p in enumerate(top_products, 1):
                name = str(p.get('name', '?'))[:32]
                L.append(
                    f"  {i:<4} {name:<32} "
                    f"{p.get('quantity_sold', 0):>8} "
                    f"₱{p.get('revenue', 0):>14,.2f}")

        L.append("")
        L.append("=" * 78)

        self.report_text.delete('1.0', tk.END)
        self.report_text.insert('1.0', "\n".join(L))

    def _export_report_csv(self):
        start = self.start_date.get().strip()
        end = self.end_date.get().strip()
        user_id = self._resolve_user_id_from_filter()

        try:
            datetime.strptime(start, '%Y-%m-%d')
            datetime.strptime(end, '%Y-%m-%d')
        except ValueError:
            messagebox.showerror("Invalid Date",
                                  "Dates must be YYYY-MM-DD.")
            return

        default_name = f"sales_report_{start}_to_{end}.csv"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=default_name,
            title="Save Report")
        if not filepath:
            return

        params = {
            'start_date': start,
            'end_date': end,
            'per_page': 1000,
        }
        if user_id is not None:
            params['user_id'] = user_id

        async_call(
            widget=self,
            task=lambda: Api.get(self.api_url, '/sales',
                                  token=self.token, params=params,
                                  timeout=30),
            on_success=lambda data: self._write_report_csv(data, filepath),
            on_error=lambda e: messagebox.showerror("Export Failed", str(e)),
        )

    def _write_report_csv(self, data, filepath):
        if not self._alive():
            return
        if not data.get('success'):
            messagebox.showerror(
                "Export Failed",
                data.get('message', 'Could not fetch sales.'))
            return

        items = data.get('data', {}).get('items', []) or []
        if not items:
            messagebox.showwarning("Nothing to Export",
                                    "No sales matched the filter.")
            return

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Invoice', 'Date', 'Cashier', 'Customer',
                    'Items', 'Payment', 'Total'
                ])
                grand = 0.0
                for sale in items:
                    amt = float(sale.get('final_amount') or 0)
                    grand += amt
                    writer.writerow([
                        sale.get('invoice_number') or '',
                        sale.get('created_at') or '',
                        sale.get('username') or '',
                        sale.get('customer_name') or 'Walk-in',
                        sale.get('total_items') or 0,
                        (sale.get('payment_method') or '').upper(),
                        f"{amt:.2f}",
                    ])
                writer.writerow([])
                writer.writerow(['', '', '', '', '', 'TOTAL', f"{grand:.2f}"])

            messagebox.showinfo(
                "Export Complete",
                f"Exported {len(items)} sales to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    # ══════════════
    # PRODUCTS LOAD
    # ══════════════

    def load_products(self):
        if self._loading_products or not self._alive():
            return
        self._loading_products = True

        async_call(
            widget=self,
            task=lambda: Api.get(self.api_url, '/products',
                                  token=self.token,
                                  params={'per_page': 500},
                                  timeout=15),
            on_success=self._on_products_loaded,
            on_error=lambda e: messagebox.showerror(
                "Error", f"Failed to load products:\n{e}"),
            on_finally=self._reset_products_loading,
        )

    def _reset_products_loading(self):
        self._loading_products = False

    def _on_products_loaded(self, data):
        if not self._alive():
            return
        if data.get('success'):
            self.products = (data.get('data') or {}).get('items') or []
            self.products_by_id = {p['id']: p for p in self.products}
            self._populate_products_tree()
        else:
            messagebox.showerror("Error",
                                  data.get('message', 'Failed to load'))

    def _populate_products_tree(self):
        if not self._alive() or not getattr(self, 'products_tree', None):
            return
        try:
            self.products_tree.delete(*self.products_tree.get_children())
            for p in self.products:
                stock = p.get('stock_quantity', 0) or 0
                min_stock = p.get('min_stock_level', 10) or 10

                if stock <= 0:
                    status = "Out of Stock"
                elif stock <= min_stock:
                    status = "Low Stock"
                else:
                    status = "In Stock"

                self.products_tree.insert(
                    '', 'end',
                    iid=str(p.get('id')),
                    values=(
                        p.get('id'),
                        p.get('name'),
                        p.get('barcode') or '—',
                        p.get('category_name') or 'Uncategorized',
                        f"₱{float(p.get('selling_price', 0)):,.2f}",
                        stock,
                        status,
                    ))
        except Exception as e:
            print(f"[Admin] populate products: {e}")

    # ══════════
    # ADD USER
    # ══════════

    def add_user(self):
        dialog = tk.Toplevel(self)
        dialog.title("Add User")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg='#ffffff')

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 210
        y = (dialog.winfo_screenheight() // 2) - 220
        dialog.geometry(f"420x440+{x}+{y}")

        tk.Label(dialog, text="➕  Add New User",
                 font=('Segoe UI', 14, 'bold'),
                 bg='#ffffff', fg='#1a1a2e').pack(pady=(20, 10))

        form = tk.Frame(dialog, bg='#ffffff')
        form.pack(fill='x', padx=30)

        def field(label, show=None):
            tk.Label(form, text=label, anchor='w',
                     font=('Segoe UI', 9, 'bold'),
                     bg='#ffffff', fg='#495057'
                     ).pack(fill='x', pady=(8, 2))
            e = tk.Entry(form, show=show or '',
                         font=('Segoe UI', 10),
                         bg='#f8f9fa', relief='flat', bd=0,
                         highlightthickness=1,
                         highlightbackground='#dee2e6',
                         highlightcolor=self.ACCENT)
            e.pack(fill='x', ipady=8, ipadx=6)
            return e

        username_e = field("Username *")
        full_name_e = field("Full Name *")
        password_e = field("Password *", show='•')

        tk.Label(form, text="Role", anchor='w',
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg='#495057'
                 ).pack(fill='x', pady=(8, 2))
        role_var = tk.StringVar(value='cashier')
        ttk.Combobox(form, textvariable=role_var,
                      values=['cashier', 'owner'],
                      state='readonly', font=('Segoe UI', 10)
                      ).pack(fill='x', ipady=4)

        status = tk.Label(dialog, text="",
                           font=('Segoe UI', 9),
                           bg='#ffffff', fg='#dc3545')
        status.pack(pady=(10, 0))

        def submit():
            data = {
                'username': username_e.get().strip(),
                'full_name': full_name_e.get().strip(),
                'email': None,
                'password': password_e.get(),
                'role': role_var.get(),
            }
            if (not data['username'] or not data['full_name']
                    or not data['password']):
                status.config(
                    text="Username, Full Name, and Password are required.")
                return

            status.config(text="Creating...", fg='#0d6efd')

            def task():
                return Api.post(self.api_url, '/auth/register',
                                 token=self.token, json=data, timeout=20)

            def ok(result):
                if not dialog.winfo_exists():
                    return
                if result.get('success'):
                    messagebox.showinfo("Success", "User created.")
                    dialog.destroy()
                    self._load_users_async()
                else:
                    msg = result.get('message', 'Failed')
                    details = result.get('details')
                    if isinstance(details, dict):
                        msg = "\n".join(
                            f"{k}: "
                            f"{', '.join(v) if isinstance(v, list) else v}"
                            for k, v in details.items())
                    status.config(text=msg, fg='#dc3545')

            def err(exc):
                if not dialog.winfo_exists():
                    return
                status.config(text=f"Error: {exc}", fg='#dc3545')

            async_call(widget=dialog, task=task,
                        on_success=ok, on_error=err)

        btns = tk.Frame(dialog, bg='#ffffff')
        btns.pack(fill='x', padx=30, pady=20)

        tk.Button(btns, text="Cancel",
                  font=('Segoe UI', 10),
                  bg='#f1f3f5', fg='#495057',
                  relief='flat', bd=0, cursor='hand2',
                  padx=20, pady=8,
                  command=dialog.destroy).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(btns, text="Create User",
                  font=('Segoe UI', 10, 'bold'),
                  bg=self.ACCENT, fg='white',
                  relief='flat', bd=0, cursor='hand2',
                  padx=20, pady=8,
                  activebackground=self.ACCENT_DARK,
                  activeforeground='white',
                  command=submit).pack(side=tk.RIGHT)

        username_e.focus()

    # ═════════════════════════════════════════════════════════
    # DELETE USER — this is the missing method from the traceback
    # ═════════════════════════════════════════════════════════

    def delete_user(self):
        sel = self.users_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a user first.")
            return
        try:
            user_id = int(sel[0])
        except ValueError:
            return

        user = next((u for u in self.users if u.get('id') == user_id), None)
        name = user.get('username') if user else f"ID {user_id}"

        if not messagebox.askyesno("Confirm Delete",
                                    f"Delete user '{name}'?"):
            return

        async_call(
            widget=self,
            task=lambda: Api.delete(self.api_url,
                                     f'/auth/users/{user_id}',
                                     token=self.token, timeout=15),
            on_success=self._on_user_deleted,
            on_error=lambda e: messagebox.showerror("Error", str(e)),
        )

    def _on_user_deleted(self, data):
        if data.get('success'):
            messagebox.showinfo("Success", "User deleted.")
            self._load_users_async()
        else:
            messagebox.showerror("Error", data.get('message', 'Failed'))

    # ═════════════════════
    # RESET USER PASSWORD
    # ═════════════════════

    def reset_user_password(self):
        sel = self.users_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a user first.")
            return
        try:
            user_id = int(sel[0])
        except ValueError:
            return

        user = next((u for u in self.users if u.get('id') == user_id), None)
        name = user.get('username') if user else f"ID {user_id}"

        dialog = tk.Toplevel(self)
        dialog.title("Reset Password")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg='#ffffff')

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 220
        y = (dialog.winfo_screenheight() // 2) - 210
        dialog.geometry(f"440x420+{x}+{y}")

        tk.Label(dialog, text="🔑  Reset Password",
                 font=('Segoe UI', 14, 'bold'),
                 bg='#ffffff', fg='#1a1a2e').pack(pady=(20, 4))
        tk.Label(dialog, text=f"User: {name}",
                 font=('Segoe UI', 10),
                 bg='#ffffff', fg='#6c757d').pack(pady=(0, 16))

        form = tk.Frame(dialog, bg='#ffffff')
        form.pack(fill='x', padx=30)

        def field(label):
            tk.Label(form, text=label, anchor='w',
                     font=('Segoe UI', 9, 'bold'),
                     bg='#ffffff', fg='#495057'
                     ).pack(fill='x', pady=(8, 2))
            e = tk.Entry(form, show='•',
                         font=('Segoe UI', 10),
                         bg='#f8f9fa', relief='flat', bd=0,
                         highlightthickness=1,
                         highlightbackground='#dee2e6',
                         highlightcolor=self.ACCENT)
            e.pack(fill='x', ipady=8, ipadx=6)
            return e

        pw_entry = field("New Password")
        confirm_entry = field("Confirm New Password")

        status = tk.Label(dialog, text="",
                           font=('Segoe UI', 9),
                           bg='#ffffff', fg='#dc3545')
        status.pack(pady=(10, 0))

        def submit():
            new_pw = pw_entry.get()
            confirm = confirm_entry.get()

            if not new_pw or not confirm:
                status.config(text="Both fields are required.",
                              fg='#dc3545')
                return
            if new_pw != confirm:
                status.config(text="Passwords do not match.",
                              fg='#dc3545')
                return
            if len(new_pw) < 8:
                status.config(
                    text="Password must be at least 8 characters.",
                    fg='#dc3545')
                return

            status.config(text="Resetting...", fg='#0d6efd')

            def task():
                return Api.post(
                    self.api_url,
                    f'/auth/users/{user_id}/reset-password',
                    token=self.token,
                    json={'new_password': new_pw},
                    timeout=15)

            def ok(data):
                if not dialog.winfo_exists():
                    return
                if data.get('success'):
                    messagebox.showinfo(
                        "Success",
                        f"Password reset for '{name}'.\n"
                        f"New password: {new_pw}")
                    dialog.destroy()
                else:
                    status.config(text=data.get('message', 'Failed'),
                                  fg='#dc3545')

            def err(exc):
                if not dialog.winfo_exists():
                    return
                status.config(text=str(exc), fg='#dc3545')

            async_call(widget=dialog, task=task,
                        on_success=ok, on_error=err)

        btns = tk.Frame(dialog, bg='#ffffff')
        btns.pack(fill='x', padx=30, pady=20)

        tk.Button(btns, text="Cancel",
                  bg='#f1f3f5', fg='#495057',
                  relief='flat', bd=0, padx=20, pady=8,
                  cursor='hand2',
                  command=dialog.destroy).pack(side=tk.RIGHT, padx=(8, 0))
        tk.Button(btns, text="✔  DONE",
                  bg=self.ACCENT, fg='white',
                  relief='flat', bd=0, padx=24, pady=8,
                  cursor='hand2',
                  font=('Segoe UI', 10, 'bold'),
                  activebackground=self.ACCENT_DARK,
                  activeforeground='white',
                  command=submit).pack(side=tk.RIGHT)

        pw_entry.focus()

    # ═════════════════════════════════════════════════════════
    # ADD PRODUCT — fixed: button row anchored to bottom
    # ═════════════════════════════════════════════════════════

    def add_product(self):
        dialog = tk.Toplevel(self)
        dialog.title("Add Product")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, True)
        dialog.configure(bg='#ffffff')

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 240
        y = max(20, (dialog.winfo_screenheight() // 2) - 320)
        # Taller window so the button row has space
        dialog.geometry(f"480x720+{x}+{y}")

        # ── 1. Button row FIRST (side=BOTTOM) so it never gets pushed
        #      off-screen by long form content. ──
        btns = tk.Frame(dialog, bg='#f8f9fa',
                        highlightbackground='#e9ecef', highlightthickness=1)
        btns.pack(fill='x', side=tk.BOTTOM)

        btns_inner = tk.Frame(btns, bg='#f8f9fa')
        btns_inner.pack(fill='x', padx=24, pady=12)

        status = tk.Label(btns_inner, text="",
                           font=('Segoe UI', 9),
                           bg='#f8f9fa', fg='#dc3545',
                           anchor='w')
        status.pack(fill='x', pady=(0, 8))

        btn_row = tk.Frame(btns_inner, bg='#f8f9fa')
        btn_row.pack(fill='x')

        def submit():
            try:
                data = {
                    'name': name_e.get().strip(),
                    'barcode': barcode_e.get().strip() or None,
                    'description': desc_e.get().strip() or None,
                    'purchase_price': float(purchase_e.get() or 0),
                    'selling_price': float(selling_e.get() or 0),
                    'stock_quantity': int(stock_e.get() or 0),
                    'min_stock_level': int(min_stock_e.get() or 10),
                }
            except ValueError:
                status.config(text="Invalid numeric value.")
                return

            if not data['name']:
                status.config(text="Product name is required.")
                return
            if data['selling_price'] < data['purchase_price']:
                status.config(
                    text="Selling price must be ≥ purchase price.")
                return

            status.config(text="Creating...", fg='#0d6efd')

            def task():
                return Api.post(self.api_url, '/products',
                                 token=self.token, json=data, timeout=20)

            def ok(result):
                if not dialog.winfo_exists():
                    return
                if result.get('success'):
                    messagebox.showinfo("Success", "Product created.")
                    dialog.destroy()
                    self.load_products()
                else:
                    status.config(text=result.get('message', 'Failed'))

            def err(exc):
                if not dialog.winfo_exists():
                    return
                status.config(text=f"Error: {exc}")

            async_call(widget=dialog, task=task,
                        on_success=ok, on_error=err)

        tk.Button(btn_row, text="Cancel",
                  bg='#f1f3f5', fg='#495057',
                  relief='flat', bd=0, padx=16, pady=8, cursor='hand2',
                  font=('Segoe UI', 10),
                  command=dialog.destroy).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(btn_row, text="Create Product",
                  bg=self.ACCENT, fg='white',
                  relief='flat', bd=0, padx=16, pady=8, cursor='hand2',
                  font=('Segoe UI', 10, 'bold'),
                  activebackground=self.ACCENT_DARK,
                  activeforeground='white',
                  command=submit).pack(side=tk.RIGHT)

        # ── 2. Header ──
        tk.Label(dialog, text="➕  Add Product",
                 font=('Segoe UI', 14, 'bold'),
                 bg='#ffffff', fg='#1a1a2e').pack(pady=(20, 10))

        # ── 3. Form in a scrollable area so it never pushes buttons ──
        scroll_wrap = tk.Frame(dialog, bg='#ffffff')
        scroll_wrap.pack(fill=tk.BOTH, expand=True, padx=24)

        canvas = tk.Canvas(scroll_wrap, bg='#ffffff', highlightthickness=0)
        vsb = ttk.Scrollbar(scroll_wrap, orient=tk.VERTICAL,
                             command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill='y')

        form = tk.Frame(canvas, bg='#ffffff')
        win_id = canvas.create_window((0, 0), window=form, anchor='nw')

        def _configure_form(event=None):
            try:
                canvas.configure(scrollregion=canvas.bbox('all'))
            except Exception:
                pass

        def _configure_canvas(event):
            try:
                canvas.itemconfig(win_id, width=event.width)
            except Exception:
                pass

        form.bind('<Configure>', _configure_form)
        canvas.bind('<Configure>', _configure_canvas)

        def field(label, default=None):
            tk.Label(form, text=label, anchor='w',
                     font=('Segoe UI', 9, 'bold'),
                     bg='#ffffff', fg='#495057'
                     ).pack(fill='x', pady=(6, 2))
            e = tk.Entry(form,
                         font=('Segoe UI', 10),
                         bg='#f8f9fa', relief='flat', bd=0,
                         highlightthickness=1,
                         highlightbackground='#dee2e6',
                         highlightcolor=self.ACCENT)
            e.pack(fill='x', ipady=6, ipadx=6)
            if default is not None:
                e.insert(0, default)
            return e

        name_e = field("Product Name *")
        barcode_e = field("Barcode")
        desc_e = field("Description")
        purchase_e = field("Purchase Price *", default="0.00")
        selling_e = field("Selling Price *", default="0.00")
        stock_e = field("Stock Quantity", default="0")
        min_stock_e = field("Min Stock Level", default="10")

        name_e.focus()

    # ════════════════
    # DELETE PRODUCT
    # ════════════════

    def delete_product(self):
        sel = self.products_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a product first.")
            return
        try:
            pid = int(sel[0])
        except ValueError:
            return

        product = self.products_by_id.get(pid)
        name = product.get('name') if product else f"ID {pid}"

        if not messagebox.askyesno("Confirm Delete",
                                    f"Delete product '{name}'?"):
            return

        async_call(
            widget=self,
            task=lambda: Api.delete(self.api_url, f'/products/{pid}',
                                     token=self.token, timeout=15),
            on_success=self._on_product_deleted,
            on_error=lambda e: messagebox.showerror("Error", str(e)),
        )

    def _on_product_deleted(self, data):
        if data.get('success'):
            messagebox.showinfo("Success", "Product deleted.")
            self.load_products()
        else:
            messagebox.showerror("Error", data.get('message', 'Failed'))
