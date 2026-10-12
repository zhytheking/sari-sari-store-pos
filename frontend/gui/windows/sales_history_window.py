
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
import threading
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from frontend.gui.config import get_api_url
from frontend.gui.logger import get_logger

log = get_logger(__name__)

_session = requests.Session()
_session.headers.update({'Connection': 'keep-alive'})

_MAX_INDIVIDUAL_FETCH = 50


class SalesHistoryWindow(tk.Frame):
    """Sales history viewer."""

    ACCENT = '#2d6a4f'
    ACCENT_DARK = '#1b4332'

    def __init__(self, parent, api_url, token,
                 current_user=None, is_owner=False):
        super().__init__(parent)
        self.parent = parent
        base = api_url or get_api_url()
        self.api_url = base.replace("localhost", "127.0.0.1")
        self.token = token
        self.current_user = current_user or {}
        self.is_owner = is_owner
        self.my_user_id = self.current_user.get('id')

        self._destroyed = False
        self._loading = False
        self._after_ids = set()
        self._sales = []
        self._users = []
        self._user_choices = {}
        self._products_cache = {}

        self.setup_ui()
        self._schedule(80, self._initial_load)

    def _alive(self):
        if self._destroyed:
            return False
        try:
            return bool(self.winfo_exists())
        except Exception:
            return False

    def _schedule(self, delay_ms, fn, *args):
        if not self._alive():
            return None
        try:
            holder = {}
            aid = self.after(delay_ms, lambda: self._run(holder, fn, args))
            holder['id'] = aid
            self._after_ids.add(aid)
            return aid
        except Exception:
            return None

    def _run(self, holder, fn, args):
        aid = holder.get('id')
        if aid is not None:
            self._after_ids.discard(aid)
        if not self._alive():
            return
        try:
            fn(*args)
        except tk.TclError:
            pass
        except Exception as e:
            log.warning("callback: %s", e)

    def destroy(self):
        self._destroyed = True
        for aid in list(self._after_ids):
            try:
                self.after_cancel(aid)
            except Exception:
                pass
        self._after_ids.clear()
        try:
            super().destroy()
        except Exception:
            pass

    def _initial_load(self):
        if self.is_owner:
            self._load_users_async(then_load_sales=True)
        else:
            self.load_sales_async()

    def setup_ui(self):
        self.configure(bg='#f0f4f8')
        self.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(self, bg='#f0f4f8')
        header.pack(fill='x', padx=16, pady=12)

        tk.Label(header, text="🧾  Sales History",
                 font=('Segoe UI', 16, 'bold'),
                 bg='#f0f4f8', fg='#1a1a2e').pack(side=tk.LEFT)

        subtitle = ("All sales" if self.is_owner else "Your sales only")
        tk.Label(header, text=subtitle,
                 font=('Segoe UI', 9),
                 bg='#f0f4f8', fg='#6c757d').pack(side=tk.LEFT, padx=12)

        tk.Button(header, text="🔄  Refresh",
                  font=('Segoe UI', 9),
                  bg='#ffffff', fg='#495057',
                  relief='flat', bd=0, cursor='hand2',
                  padx=14, pady=6,
                  activebackground='#e9ecef',
                  command=self.load_sales_async).pack(side=tk.RIGHT)

        if self.is_owner:
            export_btn = tk.Menubutton(
                header, text="📤  Export ▾",
                font=('Segoe UI', 9, 'bold'),
                bg='#0d6efd', fg='white',
                relief='flat', bd=0, cursor='hand2',
                padx=14, pady=6,
                activebackground='#0a58ca',
                activeforeground='white')
            export_btn.pack(side=tk.RIGHT, padx=(0, 8))

            menu = tk.Menu(export_btn, tearoff=0, font=('Segoe UI', 9))
            menu.add_command(
                label="Export ALL records (current filter)",
                command=lambda: self.export_csv(mode='all'))
            menu.add_separator()
            menu.add_command(
                label="Export ADMIN (owner) records only",
                command=lambda: self.export_csv(mode='owner'))
            menu.add_command(
                label="Export CASHIER records only",
                command=lambda: self.export_csv(mode='cashier'))
            menu.add_separator()
            menu.add_command(
                label="Export records of currently selected user",
                command=lambda: self.export_csv(mode='current'))
            export_btn.config(menu=menu)
        else:
            tk.Button(header, text="📤  Export My Sales",
                      font=('Segoe UI', 9, 'bold'),
                      bg='#0d6efd', fg='white',
                      relief='flat', bd=0, cursor='hand2',
                      padx=14, pady=6,
                      activebackground='#0a58ca',
                      activeforeground='white',
                      command=lambda: self.export_csv(mode='all')
                      ).pack(side=tk.RIGHT, padx=(0, 8))

        filters = tk.Frame(self, bg='#ffffff',
                           highlightbackground='#e9ecef',
                           highlightthickness=1)
        filters.pack(fill='x', padx=16, pady=(0, 12))

        f_inner = tk.Frame(filters, bg='#ffffff')
        f_inner.pack(fill='x', padx=16, pady=12)

        row1 = tk.Frame(f_inner, bg='#ffffff')
        row1.pack(fill='x')

        tk.Label(row1, text="From:",
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg='#495057').pack(side=tk.LEFT)
        self.from_entry = tk.Entry(row1, width=14, font=('Segoe UI', 10))
        self.from_entry.pack(side=tk.LEFT, padx=(4, 12))
        default_from = (datetime.now() - timedelta(days=30)
                        ).strftime('%Y-%m-%d')
        self.from_entry.insert(0, default_from)

        tk.Label(row1, text="To:",
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg='#495057').pack(side=tk.LEFT)
        self.to_entry = tk.Entry(row1, width=14, font=('Segoe UI', 10))
        self.to_entry.pack(side=tk.LEFT, padx=(4, 12))
        self.to_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))

        self.user_filter_var = None
        self.user_dropdown = None
        if self.is_owner:
            tk.Label(row1, text="User:",
                     font=('Segoe UI', 9, 'bold'),
                     bg='#ffffff', fg='#495057').pack(side=tk.LEFT)
            self.user_filter_var = tk.StringVar(value='All Users')
            self.user_dropdown = ttk.Combobox(
                row1, textvariable=self.user_filter_var,
                state='readonly', width=26, font=('Segoe UI', 9))
            self.user_dropdown['values'] = ['All Users']
            self.user_dropdown.pack(side=tk.LEFT, padx=(4, 12))

        tk.Button(row1, text="🔍  Apply",
                  font=('Segoe UI', 9, 'bold'),
                  bg=self.ACCENT, fg='white',
                  relief='flat', bd=0, cursor='hand2',
                  padx=14, pady=6,
                  activebackground=self.ACCENT_DARK,
                  activeforeground='white',
                  command=self.load_sales_async).pack(side=tk.LEFT)

        tk.Button(row1, text="Clear",
                  font=('Segoe UI', 9),
                  bg='#e9ecef', fg='#495057',
                  relief='flat', bd=0, cursor='hand2',
                  padx=14, pady=6,
                  command=self.clear_filters).pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(f_inner, text="📅  Format: YYYY-MM-DD",
                 font=('Segoe UI', 8, 'italic'),
                 bg='#ffffff', fg='#6c757d').pack(anchor='w', pady=(6, 0))

        wrapper = tk.Frame(self, bg='#ffffff',
                           highlightbackground='#e9ecef',
                           highlightthickness=1)
        wrapper.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        style = ttk.Style()
        try:
            style.configure("Hist.Treeview",
                            background="#ffffff", fieldbackground="#ffffff",
                            foreground="#212529", rowheight=30,
                            font=('Segoe UI', 10))
            style.configure("Hist.Treeview.Heading",
                            background="#f8f9fa", foreground="#495057",
                            font=('Segoe UI', 10, 'bold'), relief='flat')
            style.map("Hist.Treeview",
                      background=[('selected', '#d8f3dc')],
                      foreground=[('selected', '#1b4332')])
        except Exception:
            pass

        self.tree = ttk.Treeview(
            wrapper,
            columns=('Cashier', 'Date', 'Products', 'Items', 'Total'),
            show='headings', style="Hist.Treeview", selectmode='browse')

        for col, w, anchor in [
            ('Cashier', 120, 'w'), ('Date', 150, 'w'),
            ('Products', 380, 'w'), ('Items', 60, 'center'),
            ('Total', 100, 'e'),
        ]:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor=anchor,
                             stretch=(col == 'Products'))

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(wrapper, orient=tk.VERTICAL, command=self.tree.yview)
        sb.pack(side=tk.RIGHT, fill='y')
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind('<Double-1>', self.show_sale_details)

        footer = tk.Frame(self, bg='#ffffff',
                          highlightbackground='#e9ecef', highlightthickness=1)
        footer.pack(fill='x', padx=16, pady=(0, 16))
        f_inner2 = tk.Frame(footer, bg='#ffffff')
        f_inner2.pack(fill='x', padx=16, pady=12)

        self.count_label = tk.Label(f_inner2, text="0 sales",
                                    font=('Segoe UI', 10),
                                    bg='#ffffff', fg='#6c757d')
        self.count_label.pack(side=tk.LEFT)
        self.total_label = tk.Label(f_inner2, text="Total Revenue:  ₱0.00",
                                    font=('Segoe UI', 12, 'bold'),
                                    bg='#ffffff', fg=self.ACCENT)
        self.total_label.pack(side=tk.RIGHT)

    def _load_users_async(self, then_load_sales=False):
        if not self.is_owner or not self._alive():
            return

        def worker():
            try:
                r = _session.get(
                    f"{self.api_url}/auth/users?per_page=200",
                    headers={'Authorization': f'Bearer {self.token}'},
                    timeout=15)
                data = r.json()
                if not self._alive():
                    return
                if data.get('success'):
                    self._users = (data.get('data', {}).get('items', []) or [])
                    self._schedule(0, self._populate_user_dropdown)
                    if then_load_sales:
                        self._schedule(200, self.load_sales_async)
            except Exception as e:
                log.warning("load users: %s", e)
                if then_load_sales:
                    self._schedule(200, self.load_sales_async)

        threading.Thread(target=worker, daemon=True).start()

    def _populate_user_dropdown(self):
        if not self._alive() or not self.user_dropdown:
            return
        try:
            self._user_choices = {}
            choices = ['All Users']
            self._user_choices['All Users'] = None
            for u in self._users:
                label = (f"{u.get('full_name') or u.get('username')} "
                         f"({u.get('username')})")
                choices.append(label)
                self._user_choices[label] = u.get('id')
            self.user_dropdown['values'] = choices
            self.user_filter_var.set('All Users')
        except Exception as e:
            log.warning("populate dropdown: %s", e)

    def _resolve_user_id_from_filter(self):
        if not self.is_owner or not self.user_filter_var:
            return None
        sel = self.user_filter_var.get()
        return self._user_choices.get(sel)

    def load_sales_async(self):
        if self._loading or not self._alive():
            return
        self._loading = True

        start = self.from_entry.get().strip()
        end = self.to_entry.get().strip()
        try:
            datetime.strptime(start, '%Y-%m-%d')
            datetime.strptime(end, '%Y-%m-%d')
        except ValueError:
            messagebox.showerror(
                "Invalid Date",
                "Dates must be in YYYY-MM-DD format (example: 2026-09-17).")
            self._loading = False
            return

        try:
            self.tree.delete(*self.tree.get_children())
            self.tree.insert('', 'end', iid='__loading__',
                             values=('⏳ Loading...', '', '', '', ''))
        except Exception:
            pass

        user_id = (self._resolve_user_id_from_filter() if self.is_owner
                   else self.my_user_id)

        def worker():
            try:
                params = {
                    'start_date': start, 'end_date': end,
                    'per_page': 500,
                    'include_items': 'true',
                }
                if user_id is not None:
                    params['user_id'] = user_id

                r = _session.get(
                    f"{self.api_url}/sales",
                    params=params,
                    headers={'Authorization': f'Bearer {self.token}'},
                    timeout=30)
                data = r.json()
                if not self._alive():
                    return

                items = data.get('data', {}).get('items', []) or []
                has_inline = any('items' in s for s in items)
                if has_inline:
                    self._products_cache = {
                        s['id']: ", ".join(
                            f"{it.get('product_name') or it.get('name')} ×{it.get('quantity', 0)}"
                            for it in (s.get('items') or []))
                        for s in items
                    }
                    self._schedule(0, lambda: self._render_sales(data))
                else:
                    self._prefetch_sale_items(items, data)
            except Exception as e:
                self._schedule(0, lambda: self._show_load_error(str(e)))
            finally:
                self._loading = False

        threading.Thread(target=worker, daemon=True).start()

    def _prefetch_sale_items(self, sales, original_data):
        if not sales:
            self._schedule(0, lambda: self._render_sales(original_data))
            return

        to_fetch = [
            s for s in sales
            if s.get('id') and s['id'] not in self._products_cache
        ][:_MAX_INDIVIDUAL_FETCH]

        for sale in to_fetch:
            if not self._alive():
                return
            try:
                r = _session.get(
                    f"{self.api_url}/sales/{sale['id']}",
                    headers={'Authorization': f'Bearer {self.token}'},
                    timeout=10)
                detail = r.json()
                if detail.get('success'):
                    items = (detail.get('data', {}).get('items', []) or [])
                    names = []
                    for it in items:
                        name = it.get('product_name') or it.get('name') or ''
                        qty = it.get('quantity', 0)
                        if name:
                            names.append(f"{name} ×{qty}")
                    self._products_cache[sale['id']] = ", ".join(names)
                else:
                    self._products_cache[sale['id']] = "—"
            except Exception as e:
                log.warning("fetch sale %s: %s", sale.get('id'), e)
                self._products_cache[sale['id']] = "—"

        self._schedule(0, lambda: self._render_sales(original_data))

    def _show_load_error(self, msg):
        if not self._alive():
            return
        try:
            self.tree.delete(*self.tree.get_children())
            self.tree.insert('', 'end',
                             values=(f"Error: {msg}", '', '', '', ''))
        except Exception:
            pass

    def _render_sales(self, data):
        if not self._alive():
            return
        try:
            self.tree.delete(*self.tree.get_children())
        except Exception:
            return

        if not data.get('success'):
            self.tree.insert(
                '', 'end',
                values=(data.get('message', 'Failed to load'), '', '', '', ''))
            return

        items = data.get('data', {}).get('items', []) or []
        self._sales = items

        if not items:
            self.tree.insert('', 'end', values=('No sales found', '', '', '', ''))
            self.count_label.config(text="0 sales")
            self.total_label.config(text="Total Revenue:  ₱0.00")
            return

        grand_total = 0.0
        for sale in items:
            cashier = sale.get('username') or '—'
            date_str = sale.get('created_at') or ''
            try:
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                date_display = date_obj.strftime('%Y-%m-%d %H:%M')
            except Exception:
                date_display = date_str

            products_str = self._products_cache.get(sale.get('id'), '—') or '—'
            total_items = sale.get('total_items') or 0
            total_amt = float(sale.get('final_amount') or 0)
            grand_total += total_amt

            self.tree.insert(
                '', 'end', iid=str(sale.get('id')),
                values=(cashier, date_display, products_str,
                        total_items, f"₱{total_amt:,.2f}"))

        self.count_label.config(
            text=f"{len(items)} sale{'s' if len(items) != 1 else ''}")
        self.total_label.config(text=f"Total Revenue:  ₱{grand_total:,.2f}")

    def clear_filters(self):
        default_from = (datetime.now() - timedelta(days=30)
                        ).strftime('%Y-%m-%d')
        self.from_entry.delete(0, tk.END)
        self.from_entry.insert(0, default_from)
        self.to_entry.delete(0, tk.END)
        self.to_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))
        if self.is_owner and self.user_filter_var:
            self.user_filter_var.set('All Users')
        self.load_sales_async()

    def show_sale_details(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        try:
            sale_id = int(sel[0])
        except ValueError:
            return

        def worker():
            try:
                r = _session.get(
                    f"{self.api_url}/sales/{sale_id}",
                    headers={'Authorization': f'Bearer {self.token}'},
                    timeout=15)
                data = r.json()
                self._schedule(0, lambda: self._open_details_dialog(
                    data.get('data', {})))
            except Exception as e:
                self._schedule(0, lambda: messagebox.showerror(
                    "Error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _open_details_dialog(self, sale):
        if not sale:
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Sale Details — {sale.get('invoice_number', '')}")
        dialog.geometry("560x560")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg='#ffffff')

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 280
        y = (dialog.winfo_screenheight() // 2) - 280
        dialog.geometry(f"560x560+{x}+{y}")

        tk.Label(dialog, text=f"🧾  {sale.get('invoice_number', '')}",
                 font=('Segoe UI', 14, 'bold'),
                 bg='#ffffff', fg='#1a1a2e').pack(pady=(20, 4))

        info = tk.Frame(dialog, bg='#ffffff')
        info.pack(fill='x', padx=30, pady=(0, 12))

        for label, value in [
            ("Date", sale.get('created_at', '—')),
            ("Cashier", sale.get('username', '—')),
            ("Payment", (sale.get('payment_method') or '—').upper()),
        ]:
            row = tk.Frame(info, bg='#ffffff')
            row.pack(fill='x', pady=2)
            tk.Label(row, text=label, width=12, anchor='w',
                     font=('Segoe UI', 9, 'bold'),
                     bg='#ffffff', fg='#495057').pack(side=tk.LEFT)
            tk.Label(row, text=str(value), anchor='w',
                     font=('Segoe UI', 9),
                     bg='#ffffff', fg='#212529').pack(side=tk.LEFT)

        wrap = tk.Frame(dialog, bg='#ffffff',
                        highlightbackground='#e9ecef', highlightthickness=1)
        wrap.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 12))

        tree = ttk.Treeview(wrap,
                            columns=('Item', 'Qty', 'Price', 'Total'),
                            show='headings', height=10)
        for col, w, anchor in [
            ('Item', 220, 'w'), ('Qty', 60, 'center'),
            ('Price', 100, 'e'), ('Total', 100, 'e'),
        ]:
            tree.heading(col, text=col)
            tree.column(col, width=w, anchor=anchor)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        items = sale.get('items', []) or []
        for item in items:
            tree.insert(
                '', 'end',
                values=(
                    item.get('product_name') or item.get('name') or '—',
                    item.get('quantity', 0),
                    f"₱{float(item.get('selling_price') or 0):,.2f}",
                    f"₱{float(item.get('subtotal') or 0):,.2f}",
                ))

        totals = tk.Frame(dialog, bg='#f8f9fa')
        totals.pack(fill='x', padx=30, pady=(0, 12))
        t_inner = tk.Frame(totals, bg='#f8f9fa')
        t_inner.pack(fill='x', padx=16, pady=12)

        for label, value, bold in [
            ("Subtotal", sale.get('total_amount', 0), False),
            ("Discount", sale.get('discount_amount', 0), False),
            ("Tax", sale.get('tax_amount', 0), False),
            ("Total", sale.get('final_amount', 0), True),
        ]:
            row = tk.Frame(t_inner, bg='#f8f9fa')
            row.pack(fill='x', pady=2)
            font = (('Segoe UI', 11, 'bold') if bold else ('Segoe UI', 10))
            tk.Label(row, text=label, anchor='w',
                     font=font, bg='#f8f9fa',
                     fg='#1a1a2e' if bold else '#6c757d').pack(side=tk.LEFT)
            tk.Label(row, text=f"₱{float(value or 0):,.2f}", anchor='e',
                     font=font, bg='#f8f9fa',
                     fg=self.ACCENT if bold else '#495057'
                     ).pack(side=tk.RIGHT)

        tk.Button(dialog, text="Close",
                  font=('Segoe UI', 10),
                  bg='#e9ecef', fg='#495057',
                  relief='flat', bd=0, cursor='hand2',
                  padx=24, pady=8,
                  command=dialog.destroy).pack(pady=(0, 20))

    def export_csv(self, mode='all'):
        start = self.from_entry.get().strip()
        end = self.to_entry.get().strip()
        try:
            datetime.strptime(start, '%Y-%m-%d')
            datetime.strptime(end, '%Y-%m-%d')
        except ValueError:
            messagebox.showerror("Invalid Date",
                                 "Dates must be in YYYY-MM-DD format.")
            return

        if not self.is_owner:
            user_id = self.my_user_id
            filename_label = "my_sales"
        else:
            if mode == 'owner':
                owner_ids = [u['id'] for u in self._users
                             if u.get('role') == 'owner']
                user_id = owner_ids[0] if owner_ids else None
                filename_label = "admin_sales"
            elif mode == 'cashier':
                user_id = None
                filename_label = "cashier_sales"
            elif mode == 'current':
                user_id = self._resolve_user_id_from_filter()
                if user_id is None:
                    messagebox.showwarning("No User Selected",
                                           "Please select a specific user first.")
                    return
                label = self.user_filter_var.get()
                filename_label = (label.split('(')[-1].rstrip(')')
                                  if '(' in label else 'user')
            else:
                user_id = self._resolve_user_id_from_filter()
                filename_label = "sales_history"

        default_name = f"{filename_label}_{start}_to_{end}.csv"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=default_name,
            title="Save Sales History")
        if not filepath:
            return

        def worker():
            try:
                params = {'start_date': start, 'end_date': end, 'per_page': 1000}
                if user_id is not None:
                    params['user_id'] = user_id

                r = _session.get(
                    f"{self.api_url}/sales",
                    params=params,
                    headers={'Authorization': f'Bearer {self.token}'},
                    timeout=30)
                data = r.json()
                self._schedule(0, lambda: self._do_export(data, filepath, mode))
            except Exception as e:
                self._schedule(0, lambda: messagebox.showerror(
                    "Export Failed", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _do_export(self, data, filepath, mode):
        if not self._alive():
            return
        if not data.get('success'):
            messagebox.showerror("Export Failed",
                                 data.get('message', 'Could not fetch sales.'))
            return

        items = data.get('data', {}).get('items', []) or []

        if mode == 'cashier' and self.is_owner:
            cashier_usernames = {u['username'] for u in self._users
                                 if u.get('role') == 'cashier'}
            items = [s for s in items
                     if (s.get('username') or '') in cashier_usernames]

        if not items:
            messagebox.showwarning("Nothing to Export",
                                   "No sales matched the filter.")
            return

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Cashier', 'Date', 'Products',
                                 'Items', 'Payment Method', 'Total'])
                grand = 0.0
                for sale in items:
                    amt = float(sale.get('final_amount') or 0)
                    grand += amt
                    products_str = self._products_cache.get(sale.get('id'), '') or ''
                    writer.writerow([
                        sale.get('username') or '',
                        sale.get('created_at') or '',
                        products_str,
                        sale.get('total_items') or 0,
                        (sale.get('payment_method') or '').upper(),
                        f"{amt:.2f}",
                    ])
                writer.writerow([])
                writer.writerow(['', '', '', '', 'TOTAL', f"{grand:.2f}"])

            messagebox.showinfo("Export Complete",
                                f"Exported {len(items)} sales to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))
