"""
Product grid — table view + Add / Delete / Add Stock / Remove Stock.
Owner-only buttons are gated by decoding the JWT role claim.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import base64
import json
import random
import sys
import threading
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from frontend.gui.api import Api
from frontend.gui.config import get_api_url
from frontend.gui.ui import async_call, Debouncer, toast


class ProductGrid(tk.Frame):
    #Product grid — table view with owner-only CRUD controls

    ACCENT = '#2d6a4f'
    ACCENT_DARK = '#1b4332'
    _MAX_BARCODE_RETRIES = 3

    def __init__(self, parent, api_url, token, user=None):
        super().__init__(parent)
        self.parent = parent
        base = api_url or get_api_url()
        self.api_url = base.replace("localhost", "127.0.0.1")
        self.token = token
        self.is_owner = (self._role_from_token() == 'owner')

        self.products = []
        self._loading = False
        self._categories = []

        self.setup_ui()
        self._debounce = Debouncer(self, delay_ms=220)
        self.after(60, self.load_products_async)

    # ═════════════════
    # LIFECYCLE + ROLE
    # ═════════════════
    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def _role_from_token(self) -> str:
        try:
            parts = self.token.split('.') if self.token else []
            if len(parts) != 3:
                return 'cashier'
            payload_b64 = parts[1] + '=' * (-len(parts[1]) % 4)
            payload = json.loads(
                base64.urlsafe_b64decode(payload_b64).decode('utf-8'))
            role = payload.get('role', 'cashier')
            return role if role in ('owner', 'cashier') else 'cashier'
        except Exception as e:
            print(f"[ProductGrid] token decode failed: {e}")
            return 'cashier'

    # ═══════════
    # CATEGORIES
    # ═══════════
    def _fetch_categories_sync(self):
        try:
            resp = Api.get(self.api_url, '/products/categories',
                           token=self.token, timeout=10)
            if resp.get('success'):
                return resp.get('data') or []
        except Exception as e:
            print(f"[ProductGrid] fetch categories failed: {e}")
        return []

    # ══
    # UI
    # ══
    def setup_ui(self):
        self.configure(bg='#f0f4f8')
        self.pack(fill=tk.BOTH, expand=True)

        top = tk.Frame(self, bg='#f0f4f8')
        top.pack(fill='x', padx=16, pady=12)

        tk.Label(top, text="📦  Products",
                 font=('Segoe UI', 16, 'bold'),
                 bg='#f0f4f8', fg='#1a1a2e').pack(side=tk.LEFT)

        self.count_label = tk.Label(top, text="", font=('Segoe UI', 9),
                                    bg='#f0f4f8', fg='#8a94a0')
        self.count_label.pack(side=tk.LEFT, padx=12)

        self.refresh_btn = tk.Button(
            top, text="🔄  Refresh", font=('Segoe UI', 9),
            bg='#ffffff', fg='#495057',
            relief='flat', bd=0, cursor='hand2',
            padx=14, pady=6, activebackground='#e9ecef',
            command=self.load_products_async)
        self.refresh_btn.pack(side=tk.RIGHT)

        sw = tk.Frame(top, bg='#eef2f5')
        sw.pack(side=tk.RIGHT, padx=(0, 8))
        si = tk.Frame(sw, bg='#ffffff')
        si.pack(padx=1, pady=1)

        tk.Label(si, text="🔍", font=('Segoe UI', 10),
                 bg='#ffffff', fg='#8a94a0').pack(side=tk.LEFT, padx=(10, 4))

        self.search_var = tk.StringVar()
        tk.Entry(si, textvariable=self.search_var,
                 font=('Segoe UI', 10), bg='#ffffff',
                 relief='flat', bd=0, highlightthickness=0, width=24,
                 insertbackground=self.ACCENT).pack(side=tk.LEFT, ipady=6, padx=(0, 8))
        self.search_var.trace_add('write', self._on_search_changed)

        if self.is_owner:
            action_bar = tk.Frame(self, bg='#f0f4f8')
            action_bar.pack(fill='x', padx=16, pady=(0, 10))

            def make_btn(text, bg, cmd):
                return tk.Button(action_bar, text=text,
                                 font=('Segoe UI', 10, 'bold'),
                                 bg=bg, fg='white',
                                 relief='flat', bd=0, cursor='hand2',
                                 padx=16, pady=8,
                                 activebackground=bg, activeforeground='white',
                                 command=cmd)

            make_btn("➕  Add Product", self.ACCENT, self.add_product).pack(side=tk.LEFT, padx=(0, 6))
            make_btn("📥  Add Stock", '#198754', self.add_stock).pack(side=tk.LEFT, padx=6)
            make_btn("📤  Remove Stock", '#e37400', self.remove_stock).pack(side=tk.LEFT, padx=6)
            make_btn("⚙️  Adjust Stock", '#6c757d', self.adjust_stock).pack(side=tk.LEFT, padx=6)
            make_btn("🗑️  Delete", '#dc3545', self.delete_product).pack(side=tk.LEFT, padx=6)

        wrapper = tk.Frame(self, bg='#ffffff',
                           highlightbackground='#e9ecef', highlightthickness=1)
        wrapper.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        style = ttk.Style()
        try:
            style.configure("Grid.Treeview",
                            background="#ffffff", fieldbackground="#ffffff",
                            foreground="#212529", rowheight=28,
                            font=('Segoe UI', 10))
            style.configure("Grid.Treeview.Heading",
                            background="#f8f9fa", foreground="#495057",
                            font=('Segoe UI', 10, 'bold'), relief='flat')
            style.map("Grid.Treeview",
                      background=[('selected', '#d8f3dc')],
                      foreground=[('selected', '#1b4332')])
        except Exception:
            pass

        self.tree = ttk.Treeview(
            wrapper,
            columns=('ID', 'Name', 'Barcode', 'Category',
                     'Price', 'Stock', 'Status'),
            show='headings', style="Grid.Treeview")

        for col, w, anchor in [
            ('ID', 50, 'center'), ('Name', 220, 'w'),
            ('Barcode', 150, 'w'), ('Category', 130, 'w'),
            ('Price', 100, 'e'), ('Stock', 70, 'center'),
            ('Status', 110, 'center'),
        ]:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor=anchor,
                             stretch=(col == 'Name'))

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(wrapper, orient=tk.VERTICAL, command=self.tree.yview)
        sb.pack(side=tk.RIGHT, fill='y')
        self.tree.configure(yscrollcommand=sb.set)

        self.tree.tag_configure('out_of_stock', foreground='#dc3545')
        self.tree.tag_configure('low_stock', foreground='#e37400')
        self.tree.tag_configure('in_stock', foreground='#1e8e3e')

    # ═══════
    # SEARCH
    # ═══════
    def _on_search_changed(self, *args):
        if not self._alive():
            return
        self._debounce.call(self._apply_filter)

    def _apply_filter(self):
        if not self._alive():
            return
        q = self.search_var.get().strip().lower()
        if not q:
            self._render(self.products)
            return
        filtered = [
            p for p in self.products
            if q in str(p.get('name') or '').lower()
            or q in str(p.get('barcode') or '').lower()
            or q in str(p.get('category_name') or '').lower()
        ]
        self._render(filtered)

    # ════
    # LOAD
    # ════
    def load_products_async(self):
        if self._loading or not self._alive():
            return
        self._loading = True
        try:
            self.refresh_btn.config(text="⏳", state='disabled')
        except Exception:
            pass

        async_call(
            widget=self,
            task=lambda: Api.get(self.api_url, '/products',
                                 token=self.token,
                                 params={'per_page': 500}, timeout=15),
            on_success=self._on_products_loaded,
            on_error=self._on_products_error,
            on_finally=self._reset_loading)

    def _reset_loading(self):
        self._loading = False
        if not self._alive():
            return
        try:
            self.refresh_btn.config(text="🔄  Refresh", state='normal')
        except Exception:
            pass

    def _on_products_loaded(self, data):
        if not self._alive():
            return
        if data.get('success'):
            self.products = (data.get('data') or {}).get('items') or []
            self._render(self.products)
        else:
            toast(self, data.get('message', 'Failed to load products'), 'error')

    def _on_products_error(self, exc):
        if not self._alive():
            return
        toast(self, f"Failed: {exc}", 'error')

    # ══════════════
    # SORT + RENDER
    # ══════════════
    def _sort_products(self, products):
        def priority(p):
            stock = p.get('stock_quantity', 0) or 0
            min_stock = p.get('min_stock_level', 10) or 10
            if stock <= 0:
                return 0
            elif stock <= min_stock:
                return 1
            return 2
        return sorted(products,
                      key=lambda p: (priority(p),
                                     str(p.get('name') or '').lower()))

    def _render(self, products):
        if not self._alive():
            return
        sorted_products = self._sort_products(products)
        try:
            current_ids = set(self.tree.get_children())
        except Exception:
            return
        new_ids = {str(p.get('id')) for p in sorted_products}

        try:
            for iid in current_ids - new_ids:
                self.tree.delete(iid)
            for p in sorted_products:
                pid = str(p.get('id'))
                stock = p.get('stock_quantity', 0) or 0
                min_stock = p.get('min_stock_level', 10) or 10
                if stock <= 0:
                    status, tag = "Out of Stock", 'out_of_stock'
                elif stock <= min_stock:
                    status, tag = "Low Stock", 'low_stock'
                else:
                    status, tag = "In Stock", 'in_stock'
                values = (
                    p.get('id'), p.get('name') or '—',
                    p.get('barcode') or '—',
                    p.get('category_name') or 'Uncategorized',
                    f"₱{float(p.get('selling_price') or 0):,.2f}",
                    stock, status)
                if pid in current_ids:
                    self.tree.item(pid, values=values, tags=(tag,))
                else:
                    self.tree.insert('', 'end', iid=pid, values=values, tags=(tag,))
        except Exception as e:
            print(f"[ProductGrid] render: {e}")

        self.count_label.config(
            text=f"{len(sorted_products)} product"
                 f"{'s' if len(sorted_products) != 1 else ''}")

    # ════════
    # HELPERS
    # ════════
    def _get_selected_product(self):
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            pid = int(sel[0])
        except ValueError:
            return None
        return next((p for p in self.products if p.get('id') == pid), None)

    def _generate_unique_barcode(self):
        existing = {str(p.get('barcode') or '').strip() for p in self.products}
        for _ in range(50):
            body = [random.randint(0, 9) for _ in range(12)]
            odd = sum(body[i] for i in range(0, 12, 2))
            even = sum(body[i] for i in range(1, 12, 2))
            check = (10 - ((odd + even * 3) % 10)) % 10
            code = ''.join(str(d) for d in body) + str(check)
            if code not in existing:
                return code
        return ''.join(str(random.randint(0, 9)) for _ in range(13))

    # ════════════
    # ADD PRODUCT
    # ════════════
    def add_product(self):
        if not self.is_owner:
            messagebox.showwarning("Access Denied", "Only owners can add products.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Add Product")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg='#ffffff')

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 250
        y = (dialog.winfo_screenheight() // 2) - 350
        dialog.geometry(f"500x720+{x}+{y}")

        tk.Label(dialog, text="➕  Add Product",
                 font=('Segoe UI', 14, 'bold'),
                 bg='#ffffff', fg='#1a1a2e').pack(pady=(20, 10))

        form = tk.Frame(dialog, bg='#ffffff')
        form.pack(fill='x', padx=30)

        def field(label, default=None):
            tk.Label(form, text=label, anchor='w',
                     font=('Segoe UI', 9, 'bold'),
                     bg='#ffffff', fg='#495057').pack(fill='x', pady=(6, 2))
            e = tk.Entry(form, font=('Segoe UI', 10),
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

        bc_row = tk.Frame(form, bg='#ffffff')
        bc_row.pack(fill='x', pady=(4, 0))
        tk.Button(bc_row, text="🎲  Auto-Generate Barcode",
                  font=('Segoe UI', 9, 'bold'),
                  bg='#0d6efd', fg='white',
                  relief='flat', bd=0, cursor='hand2',
                  padx=12, pady=4,
                  activebackground='#0a58ca',
                  activeforeground='white',
                  command=lambda: (
                      barcode_e.delete(0, tk.END),
                      barcode_e.insert(0, self._generate_unique_barcode())
                  )).pack(side=tk.LEFT)
        tk.Label(bc_row, text="  ← Leave blank if no barcode",
                 font=('Segoe UI', 8, 'italic'),
                 bg='#ffffff', fg='#8a94a0').pack(side=tk.LEFT)

        desc_e = field("Description")

        tk.Label(form, text="Category", anchor='w',
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg='#495057').pack(fill='x', pady=(6, 2))

        category_var = tk.StringVar(value="Loading…")
        category_combo = ttk.Combobox(form, textvariable=category_var,
                                      state='disabled',
                                      font=('Segoe UI', 10))
        category_combo['values'] = ['Loading…']
        category_combo.pack(fill='x', ipady=4)

        def load_categories_for_dialog():
            cats = self._fetch_categories_sync()

            def apply_cats():
                if not dialog.winfo_exists():
                    return
                try:
                    if cats:
                        names = ['— Uncategorized —'] + [c['name'] for c in cats]
                        category_combo['values'] = names
                        category_combo.config(state='readonly')
                        category_var.set('— Uncategorized —')
                    else:
                        category_combo['values'] = ['— Uncategorized —']
                        category_combo.config(state='readonly')
                        category_var.set('— Uncategorized —')
                    self._categories = cats
                except Exception:
                    pass

            try:
                dialog.after(0, apply_cats)
            except Exception:
                pass

        threading.Thread(target=load_categories_for_dialog, daemon=True).start()

        purchase_e = field("Purchase Price *", default="0.00")
        selling_e = field("Selling Price *", default="0.00")
        stock_e = field("Stock Quantity", default="0")
        min_stock_e = field("Min Stock Level", default="10")

        status = tk.Label(dialog, text="",
                          font=('Segoe UI', 9),
                          bg='#ffffff', fg='#dc3545')
        status.pack(pady=(8, 0))

        def attempt_create(attempt=1):
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
                status.config(text="Selling price must be ≥ purchase price.")
                return

            chosen_name = category_var.get()
            if chosen_name and chosen_name not in ('— Uncategorized —', 'Loading…'):
                for c in self._categories:
                    if c.get('name') == chosen_name:
                        data['category_id'] = c.get('id')
                        break

            status.config(text=f"Creating… (attempt {attempt})", fg='#0d6efd')

            def task():
                return Api.post(self.api_url, '/products',
                                token=self.token, json=data, timeout=20)

            def ok(result):
                if not dialog.winfo_exists():
                    return
                if result.get('success'):
                    toast(self, f"Product '{data['name']}' created", 'success')
                    dialog.destroy()
                    self.load_products_async()
                else:
                    # If barcode collision, retry with a new barcode
                    msg = (result.get('message') or '').lower()
                    if 'barcode' in msg and attempt < self._MAX_BARCODE_RETRIES:
                        new_bc = self._generate_unique_barcode()
                        barcode_e.delete(0, tk.END)
                        barcode_e.insert(0, new_bc)
                        status.config(text=f"Barcode collision, retrying…", fg='#e37400')
                        dialog.after(400, lambda: attempt_create(attempt + 1))
                        return
                    status.config(text=result.get('message', 'Failed'))

            def err(exc):
                if not dialog.winfo_exists():
                    return
                status.config(text=f"Error: {exc}")

            async_call(widget=dialog, task=task, on_success=ok, on_error=err)

        btns = tk.Frame(dialog, bg='#ffffff')
        btns.pack(fill='x', padx=30, pady=20, side=tk.BOTTOM)

        tk.Button(btns, text="Cancel",
                  bg='#f1f3f5', fg='#495057',
                  relief='flat', bd=0, padx=16, pady=8, cursor='hand2',
                  command=dialog.destroy).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(btns, text="Create Product",
                  bg=self.ACCENT, fg='white',
                  relief='flat', bd=0, padx=16, pady=8, cursor='hand2',
                  activebackground=self.ACCENT_DARK,
                  activeforeground='white',
                  command=lambda: attempt_create(1)).pack(side=tk.RIGHT)

        name_e.focus()

    # ══════════════
    # STOCK ACTIONS
    # ══════════════
    def add_stock(self):
        if not self.is_owner:
            return
        product = self._get_selected_product()
        if not product:
            messagebox.showwarning("No Selection",
                                   "Select a product from the table first.")
            return
        self._stock_dialog(action='add', product=product,
                           title=f"📥  Add Stock — {product.get('name')}",
                           button_text="Add Stock", button_color='#198754')

    def remove_stock(self):
        if not self.is_owner:
            return
        product = self._get_selected_product()
        if not product:
            messagebox.showwarning("No Selection",
                                   "Select a product from the table first.")
            return
        self._stock_dialog(action='remove', product=product,
                           title=f"📤  Remove Stock — {product.get('name')}",
                           button_text="Remove Stock", button_color='#e37400')

    def adjust_stock(self):
        if not self.is_owner:
            return
        product = self._get_selected_product()
        if not product:
            messagebox.showwarning("No Selection",
                                   "Select a product from the table first.")
            return
        self._stock_dialog(action='adjust', product=product,
                           title=f"⚙️  Adjust Stock — {product.get('name')}",
                           button_text="Set Quantity", button_color='#6c757d')

    def _stock_dialog(self, action, product, title, button_text, button_color):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg='#ffffff')

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 220
        y = (dialog.winfo_screenheight() // 2) - 260
        dialog.geometry(f"440x520+{x}+{y}")

        tk.Label(dialog, text=title, font=('Segoe UI', 13, 'bold'),
                 bg='#ffffff', fg='#1a1a2e',
                 wraplength=400, justify='center').pack(pady=(20, 4))

        current_stock = product.get('stock_quantity', 0) or 0
        tk.Label(dialog, text=f"Current stock: {current_stock}",
                 font=('Segoe UI', 10),
                 bg='#ffffff', fg='#6c757d').pack(pady=(0, 16))

        form = tk.Frame(dialog, bg='#ffffff')
        form.pack(fill='x', padx=30)

        if action == 'adjust':
            label = "New Quantity (exact)"
            default = str(current_stock)
        else:
            label = "Quantity"
            default = "1"

        tk.Label(form, text=label, anchor='w',
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg='#495057').pack(fill='x', pady=(8, 2))
        qty_e = tk.Entry(form, font=('Segoe UI', 12),
                         bg='#f8f9fa', relief='flat', bd=0, justify='center',
                         highlightthickness=1,
                         highlightbackground='#dee2e6',
                         highlightcolor=self.ACCENT)
        qty_e.pack(fill='x', ipady=10)
        qty_e.insert(0, default)

        tk.Label(form, text="Reason", anchor='w',
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg='#495057').pack(fill='x', pady=(12, 2))

        if action == 'add':
            reason_options = ['Restock', 'New shipment',
                              'Return from customer', 'Other']
        elif action == 'remove':
            reason_options = ['Damaged', 'Expired',
                              'Return to supplier', 'Wastage',
                              'Stolen/Lost', 'Other']
        else:
            reason_options = ['Inventory count correction',
                              'Physical count', 'Other']

        reason_var = tk.StringVar(value=reason_options[0])
        ttk.Combobox(form, textvariable=reason_var, values=reason_options,
                     state='readonly', font=('Segoe UI', 10)
                     ).pack(fill='x', ipady=4)

        tk.Label(form, text="Note (optional)", anchor='w',
                 font=('Segoe UI', 9, 'bold'),
                 bg='#ffffff', fg='#495057').pack(fill='x', pady=(12, 2))
        note_e = tk.Entry(form, font=('Segoe UI', 10),
                          bg='#f8f9fa', relief='flat', bd=0,
                          highlightthickness=1,
                          highlightbackground='#dee2e6',
                          highlightcolor=self.ACCENT)
        note_e.pack(fill='x', ipady=6, ipadx=6)

        status = tk.Label(dialog, text="",
                          font=('Segoe UI', 9),
                          bg='#ffffff', fg='#dc3545')
        status.pack(pady=(10, 0))

        def submit():
            try:
                qty = int(qty_e.get() or 0)
            except ValueError:
                status.config(text="Quantity must be a whole number.")
                return
            if action in ('add', 'remove') and qty <= 0:
                status.config(text="Quantity must be greater than 0.")
                return
            if action == 'adjust' and qty < 0:
                status.config(text="Quantity cannot be negative.")
                return
            if action == 'remove' and qty > current_stock:
                status.config(text=f"Cannot remove {qty} — only {current_stock} in stock.")
                return

            pid = product.get('id')
            reason = reason_var.get()
            note = note_e.get().strip() or None
            status.config(text="Processing...", fg='#0d6efd')

            def task():
                if action == 'add':
                    return Api.post(self.api_url, '/admin/stock/add',
                                    token=self.token,
                                    json={'product_id': pid, 'quantity': qty,
                                          'reason': reason, 'note': note},
                                    timeout=15)
                elif action == 'remove':
                    return Api.post(self.api_url, '/admin/stock/remove',
                                    token=self.token,
                                    json={'product_id': pid, 'quantity': qty,
                                          'reason': reason, 'note': note},
                                    timeout=15)
                else:
                    return Api.post(self.api_url, '/admin/stock/adjust',
                                    token=self.token,
                                    json={'product_id': pid, 'new_quantity': qty,
                                          'reason': reason, 'note': note},
                                    timeout=15)

            def ok(result):
                if not dialog.winfo_exists():
                    return
                if result.get('success'):
                    toast(self, result.get('message', 'Stock updated'), 'success')
                    dialog.destroy()
                    self.load_products_async()
                else:
                    status.config(text=result.get('message', 'Failed'), fg='#dc3545')

            def err(exc):
                if not dialog.winfo_exists():
                    return
                status.config(text=f"Error: {exc}", fg='#dc3545')

            async_call(widget=dialog, task=task, on_success=ok, on_error=err)

        btns = tk.Frame(dialog, bg='#ffffff')
        btns.pack(fill='x', padx=30, pady=20, side=tk.BOTTOM)

        tk.Button(btns, text="Cancel",
                  bg='#f1f3f5', fg='#495057',
                  relief='flat', bd=0, padx=20, pady=8, cursor='hand2',
                  command=dialog.destroy).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(btns, text=button_text, bg=button_color, fg='white',
                  relief='flat', bd=0, padx=20, pady=8, cursor='hand2',
                  font=('Segoe UI', 10, 'bold'),
                  activebackground=button_color, activeforeground='white',
                  command=submit).pack(side=tk.RIGHT)

        qty_e.focus()
        qty_e.selection_range(0, tk.END)

    # ═══════
    # DELETE
    # ═══════
    def delete_product(self):
        if not self.is_owner:
            messagebox.showwarning("Access Denied", "Only owners can delete products.")
            return
        product = self._get_selected_product()
        if not product:
            messagebox.showwarning("No Selection",
                                   "Select a product from the table first.")
            return

        name = product.get('name', f"ID {product.get('id')}")
        if not messagebox.askyesno(
                "Confirm Delete",
                f"Delete product '{name}'?\n\n"
                f"This is a soft delete — the product is hidden "
                f"from POS and products list, but sale history is kept."):
            return

        pid = product.get('id')

        async_call(
            widget=self,
            task=lambda: Api.delete(self.api_url, f'/products/{pid}',
                                    token=self.token, timeout=15),
            on_success=self._on_product_deleted,
            on_error=lambda e: messagebox.showerror("Error", str(e)))

    def _on_product_deleted(self, data):
        if not self._alive():
            return
        if data.get('success'):
            toast(self, "Product deleted", 'success')
            self.load_products_async()
        else:
            messagebox.showerror("Error", data.get('message', 'Failed'))
