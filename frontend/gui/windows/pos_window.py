"""
POS window — product list + cart + payment.
Includes USB scanner capture, camera scanner, and GCash QR.
Camera scanning only works on secure origins (https or 127.0.0.1)
per browser security policy. On LAN HTTP, users must use USB scanners.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import sys
import threading
import urllib.request
from io import BytesIO
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from frontend.gui.api import Api
from frontend.gui.config import get_api_url
from frontend.gui.logger import get_logger
from frontend.gui.ui import async_call, Debouncer, toast

log = get_logger(__name__)

try:
    from PIL import Image, ImageTk
    _PIL_AVAILABLE = True
    _PIL_IMPORT_ERROR = None
except ImportError as e:
    _PIL_AVAILABLE = False
    _PIL_IMPORT_ERROR = str(e)
    Image = None
    ImageTk = None


class POSWindow(tk.Frame):

    ACCENT = '#2d6a4f'
    ACCENT_DARK = '#1b4332'
    BG = '#f0f4f8'
    DANGER = '#dc3545'
    DANGER_DARK = '#b02a37'
    SCANNER_BUFFER_TIMEOUT_MS = 280
    REQUEST_TIMEOUT = 20

    def __init__(self, parent, api_url, token):
        super().__init__(parent)
        self.parent = parent

        base = api_url or get_api_url()
        self.api_url = base.replace("localhost", "127.0.0.1")
        self.token = token

        self.cart = []
        self.products = []
        self.products_by_id = {}
        self._loading = False

        self._scan_buffer = ""
        self._scan_timer = None
        self._key_binding_id = None
        self._gcash_qr_url = None
        self._cart_rows = {}

        self.setup_ui()
        self._debounce = Debouncer(self, delay_ms=180)
        self.after(60, self.load_products_async)
        self._bind_scanner()

        if not _PIL_AVAILABLE:
            self.after(600, lambda: toast(
                self,
                "⚠️  Pillow not installed. GCash QR will not display. "
                "Run: pip install Pillow",
                'warning', duration_ms=8000))

    # ══════════
    # LIFECYCLE
    # ══════════
    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def destroy(self):
        if self._scan_timer is not None:
            try:
                self.after_cancel(self._scan_timer)
            except Exception:
                pass
            self._scan_timer = None
        try:
            if self._key_binding_id is not None:
                self.winfo_toplevel().unbind('<Key>', self._key_binding_id)
                self._key_binding_id = None
        except Exception:
            pass
        try:
            super().destroy()
        except Exception:
            pass

    # ══════════════════
    # SCANNER BINDING
    # ══════════════════
    def _bind_scanner(self):
        try:
            top = self.winfo_toplevel()
            self._key_binding_id = top.bind('<Key>', self._on_key, add='+')
        except Exception:
            self._key_binding_id = None

    def _on_key(self, event):
        try:
            focus = self.focus_get()
        except Exception:
            focus = None
        if focus is None:
            return None
        try:
            if not str(focus).startswith(str(self)):
                return None
        except Exception:
            pass

        if event.keysym in ('Return', 'KP_Enter'):
            code = self._scan_buffer.strip()
            self._scan_buffer = ""
            if code:
                self._lookup_and_add(code)
            return None

        char = event.char
        if char and char.isprintable() and char not in ('\r', '\n'):
            self._scan_buffer += char
            if self._scan_timer is not None:
                try:
                    self.after_cancel(self._scan_timer)
                except Exception:
                    pass
            try:
                self._scan_timer = self.after(
                    self.SCANNER_BUFFER_TIMEOUT_MS, self._flush_scan)
            except Exception:
                self._scan_timer = None
        return None

    def _flush_scan(self):
        self._scan_timer = None
        self._scan_buffer = ""

    def refresh(self):
        if not self._alive():
            return
        self._loading = False
        self.load_products_async()

    # ════
    # UI
    # ════
    def setup_ui(self):
        self.configure(bg=self.BG)
        self.pack(fill=tk.BOTH, expand=True)

        top = tk.Frame(self, bg=self.BG)
        top.pack(fill='x', padx=16, pady=12)

        tk.Label(top, text="🛒  Point of Sale",
                 font=('Segoe UI', 16, 'bold'),
                 bg=self.BG, fg='#1a1a2e').pack(side=tk.LEFT)

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

        scan_bar = tk.Frame(self, bg='#d8f3dc',
                            highlightbackground='#52b788',
                            highlightthickness=2)
        scan_bar.pack(fill='x', padx=16, pady=(0, 12))

        scan_inner = tk.Frame(scan_bar, bg='#d8f3dc')
        scan_inner.pack(fill='x', padx=12, pady=10)

        tk.Label(scan_inner, text="📷  BARCODE / QR",
                 font=('Segoe UI Semibold', 10),
                 bg='#d8f3dc', fg='#1b4332').pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(scan_inner,
                 text="Point a USB scanner at the barcode, or click the button for camera.",
                 font=('Segoe UI', 9),
                 bg='#d8f3dc', fg='#495057').pack(side=tk.LEFT, padx=(0, 12))

        tk.Button(scan_inner, text="📷  Scan Barcode",
                  font=('Segoe UI Semibold', 10),
                  bg=self.ACCENT, fg='white',
                  relief='flat', bd=0, cursor='hand2',
                  activebackground=self.ACCENT_DARK,
                  activeforeground='white',
                  padx=24, pady=8,
                  command=self._open_camera_scanner).pack(side=tk.RIGHT)

        self.empty_banner = tk.Frame(self, bg='#fef3c7',
                                     highlightbackground='#fde68a',
                                     highlightthickness=1)
        self.empty_banner_label = tk.Label(
            self.empty_banner,
            text="⚠️  No products in the system. Ask the owner to add products in Stocks.",
            font=('Segoe UI', 9),
            bg='#fef3c7', fg='#92400e',
            anchor='w', justify='left', wraplength=900)
        self.empty_banner_label.pack(fill='x', padx=14, pady=10)

        main = tk.Frame(self, bg=self.BG)
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        left = tk.Frame(main, bg='#ffffff',
                        highlightbackground='#e9ecef', highlightthickness=1)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left_header = tk.Frame(left, bg='#ffffff')
        left_header.pack(fill='x', padx=16, pady=12)
        tk.Label(left_header, text="Products",
                 font=('Segoe UI Semibold', 12),
                 bg='#ffffff', fg='#1a1a2e').pack(side=tk.LEFT)
        self.product_count_label = tk.Label(
            left_header, text="", font=('Segoe UI', 9),
            bg='#ffffff', fg='#8a94a0')
        self.product_count_label.pack(side=tk.RIGHT)
        tk.Frame(left, bg='#eef2f5', height=1).pack(fill='x')

        style = ttk.Style()
        try:
            style.configure("Pos.Treeview",
                            background="#ffffff", fieldbackground="#ffffff",
                            foreground="#212529", rowheight=28,
                            font=('Segoe UI', 10))
            style.configure("Pos.Treeview.Heading",
                            background="#f8f9fa", foreground="#495057",
                            font=('Segoe UI', 10, 'bold'), relief='flat')
            style.map("Pos.Treeview",
                      background=[('selected', '#d8f3dc')],
                      foreground=[('selected', '#1b4332')])
        except Exception:
            pass

        tree_wrap = tk.Frame(left, bg='#ffffff')
        tree_wrap.pack(fill=tk.BOTH, expand=True)

        self.products_tree = ttk.Treeview(
            tree_wrap,
            columns=('Name', 'Barcode', 'Price', 'Stock'),
            show='headings', style="Pos.Treeview", selectmode='browse')

        for col, w, anchor in [
            ('Name', 300, 'w'), ('Barcode', 180, 'w'),
            ('Price', 120, 'e'), ('Stock', 100, 'center'),
        ]:
            self.products_tree.heading(col, text=col)
            self.products_tree.column(col, width=w, anchor=anchor,
                                      stretch=(col == 'Name'))

        self.products_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL,
                           command=self.products_tree.yview)
        sb.pack(side=tk.RIGHT, fill='y')
        self.products_tree.configure(yscrollcommand=sb.set)

        self.products_tree.bind('<Double-1>', self._on_product_double_click)
        self.products_tree.bind('<Return>', self._on_product_double_click)
        self.products_tree.tag_configure('low_stock', foreground='#e37400')
        self.products_tree.tag_configure('out_of_stock', foreground='#dc3545')
        self.products_tree.tag_configure('inactive', foreground='#adb5bd')

        right = tk.Frame(main, bg='#ffffff',
                         highlightbackground='#e9ecef',
                         highlightthickness=1, width=440)
        right.pack(side=tk.RIGHT, fill='y', padx=(16, 0))
        right.pack_propagate(False)

        action_wrap = tk.Frame(right, bg='#ffffff')
        action_wrap.pack(fill='x', side=tk.BOTTOM)
        action_inner = tk.Frame(action_wrap, bg='#ffffff')
        action_inner.pack(fill='x', padx=16, pady=12)

        tk.Button(action_inner, text="🗑  Clear",
                  font=('Segoe UI', 10),
                  bg='#f1f3f5', fg='#495057',
                  relief='flat', bd=0, cursor='hand2',
                  activebackground='#e9ecef',
                  padx=16, pady=12,
                  command=self.clear_cart).pack(side=tk.LEFT)

        tk.Button(action_inner, text="✓  Pay",
                  font=('Segoe UI Semibold', 12),
                  bg=self.ACCENT, fg='white',
                  relief='flat', bd=0, cursor='hand2',
                  activebackground=self.ACCENT_DARK,
                  padx=36, pady=12,
                  command=self.checkout).pack(side=tk.RIGHT)

        totals = tk.Frame(right, bg='#f8f9fa')
        totals.pack(fill='x', side=tk.BOTTOM)
        totals_inner = tk.Frame(totals, bg='#f8f9fa')
        totals_inner.pack(fill='x', padx=16, pady=12)

        r1 = tk.Frame(totals_inner, bg='#f8f9fa')
        r1.pack(fill='x')
        tk.Label(r1, text="Subtotal", font=('Segoe UI', 10),
                 bg='#f8f9fa', fg='#6c757d').pack(side=tk.LEFT)
        self.subtotal_label = tk.Label(r1, text="₱0.00",
                                       font=('Segoe UI', 10),
                                       bg='#f8f9fa', fg='#495057')
        self.subtotal_label.pack(side=tk.RIGHT)

        tk.Frame(totals_inner, bg='#dee2e6', height=1).pack(fill='x', pady=8)

        r3 = tk.Frame(totals_inner, bg='#f8f9fa')
        r3.pack(fill='x')
        tk.Label(r3, text="Total", font=('Segoe UI Semibold', 13),
                 bg='#f8f9fa', fg='#1a1a2e').pack(side=tk.LEFT)
        self.total_label = tk.Label(r3, text="₱0.00",
                                    font=('Segoe UI', 20, 'bold'),
                                    bg='#f8f9fa', fg=self.ACCENT)
        self.total_label.pack(side=tk.RIGHT)

        cart_header = tk.Frame(right, bg='#ffffff')
        cart_header.pack(fill='x', padx=16, pady=12, side=tk.TOP)
        tk.Label(cart_header, text="🧾  Current Order",
                 font=('Segoe UI Semibold', 12),
                 bg='#ffffff', fg='#1a1a2e').pack(side=tk.LEFT)
        self.cart_count_label = tk.Label(cart_header, text="0 items",
                                         font=('Segoe UI', 9),
                                         bg='#ffffff', fg='#8a94a0')
        self.cart_count_label.pack(side=tk.RIGHT)

        tk.Frame(right, bg='#eef2f5', height=1).pack(fill='x', side=tk.TOP)

        cart_scroll_wrap = tk.Frame(right, bg='#ffffff')
        cart_scroll_wrap.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        self.cart_canvas = tk.Canvas(cart_scroll_wrap, bg='#ffffff',
                                     highlightthickness=0, bd=0)
        cart_scrollbar = ttk.Scrollbar(cart_scroll_wrap, orient=tk.VERTICAL,
                                       command=self.cart_canvas.yview)
        self.cart_canvas.configure(yscrollcommand=cart_scrollbar.set)
        self.cart_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cart_scrollbar.pack(side=tk.RIGHT, fill='y')

        self.cart_container = tk.Frame(self.cart_canvas, bg='#ffffff')
        self._cart_window_id = self.cart_canvas.create_window(
            (0, 0), window=self.cart_container, anchor='nw')

        self.cart_container.bind('<Configure>', self._on_cart_container_configure)
        self.cart_canvas.bind('<Configure>', self._on_cart_canvas_configure)
        self.cart_canvas.bind('<Enter>', self._bind_cart_wheel)
        self.cart_canvas.bind('<Leave>', self._unbind_cart_wheel)

        self.empty_cart_label = tk.Label(
            self.cart_container,
            text="🛒\n\nYour cart is empty\n\nDouble-click a product or scan a barcode",
            font=('Segoe UI', 10), bg='#ffffff', fg='#adb5bd', justify='center')
        self.empty_cart_label.pack(pady=60)

    def _on_cart_container_configure(self, event=None):
        try:
            self.cart_canvas.configure(scrollregion=self.cart_canvas.bbox('all'))
        except Exception:
            pass

    def _on_cart_canvas_configure(self, event):
        try:
            self.cart_canvas.itemconfig(self._cart_window_id, width=event.width)
        except Exception:
            pass

    def _bind_cart_wheel(self, event=None):
        self.cart_canvas.bind_all('<MouseWheel>', self._on_cart_wheel)
        self.cart_canvas.bind_all('<Button-4>', self._on_cart_wheel)
        self.cart_canvas.bind_all('<Button-5>', self._on_cart_wheel)

    def _unbind_cart_wheel(self, event=None):
        try:
            self.cart_canvas.unbind_all('<MouseWheel>')
            self.cart_canvas.unbind_all('<Button-4>')
            self.cart_canvas.unbind_all('<Button-5>')
        except Exception:
            pass

    def _on_cart_wheel(self, event):
        try:
            if event.num == 4:
                delta = -1
            elif event.num == 5:
                delta = 1
            else:
                delta = int(-1 * (event.delta / 120))
            self.cart_canvas.yview_scroll(delta, 'units')
        except Exception:
            pass

    def _on_search_changed(self, *args):
        if not self._alive():
            return
        self._debounce.call(self._apply_search_filter)

    def _apply_search_filter(self):
        if not self._alive():
            return
        q = self.search_var.get().strip().lower()
        visible = list(self.products)
        if q:
            visible = [p for p in visible
                       if q in str(p.get('name') or '').lower()
                       or q in str(p.get('barcode') or '').lower()]
        self._render_products_tree(visible)

    def _open_camera_scanner(self):
        if not self._alive():
            return
        try:
            from frontend.gui.windows.scanner_dialog import ScannerDialog
        except Exception as e:
            messagebox.showerror("Scanner Error",
                                 f"Could not load scanner:\n{e}")
            return
        ScannerDialog(self, on_scan=self._lookup_and_add)

    def _lookup_and_add(self, code):
        if not self._alive():
            return
        code_clean = str(code).strip()
        if not code_clean:
            return
        code_lower = code_clean.lower()

        for p in self.products:
            barcode = str(p.get('barcode') or '').strip()
            if barcode and barcode == code_clean:
                self._add_product_to_cart(p)
                return

        for p in self.products:
            barcode = str(p.get('barcode') or '').strip().lower()
            if barcode and barcode == code_lower:
                self._add_product_to_cart(p)
                return

        for p in self.products:
            name = str(p.get('name') or '').lower()
            if code_lower and code_lower in name:
                self._add_product_to_cart(p)
                return

        def task():
            try:
                return Api.get(self.api_url,
                               f'/products/barcode/{code_clean}',
                               token=self.token, timeout=10)
            except Exception:
                return Api.get(self.api_url, '/products/search',
                               token=self.token,
                               params={'q': code_clean, 'limit': 1},
                               timeout=10)

        def on_result(data):
            if not self._alive():
                return
            if data.get('success') and data.get('data'):
                payload = data['data']
                if isinstance(payload, list):
                    if payload:
                        self._add_product_to_cart(payload[0])
                else:
                    self._add_product_to_cart(payload)
            else:
                toast(self, f"No product matches: {code_clean}", 'warning')

        async_call(widget=self, task=task, on_success=on_result,
                   on_error=lambda e: toast(self, f"Lookup failed: {e}", "error"))

    def load_products_async(self):
        if self._loading or not self._alive():
            return
        self._loading = True
        try:
            self.refresh_btn.config(text="⏳ Loading", state='disabled')
        except Exception:
            pass

        async_call(
            widget=self,
            task=lambda: Api.get(self.api_url, '/products',
                                 token=self.token,
                                 params={'per_page': 500, 'active': 'all'},
                                 timeout=self.REQUEST_TIMEOUT),
            on_success=self._on_products_loaded,
            on_error=self._on_products_error,
            on_finally=self._reset_refresh)

    def _reset_refresh(self):
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
            self.products_by_id = {p['id']: p for p in self.products}
            self._apply_search_filter()
            try:
                if self.products:
                    self.empty_banner.pack_forget()
                else:
                    self.empty_banner.pack(fill='x', padx=16, pady=(0, 12))
            except Exception:
                pass
        else:
            toast(self, data.get('message', 'Failed to load products'), 'error')

    def _on_products_error(self, exc):
        if not self._alive():
            return
        toast(self, f"Failed: {exc}", 'error')

    def _render_products_tree(self, products):
        if not self._alive():
            return
        try:
            current_ids = set(self.products_tree.get_children())
        except Exception:
            return
        new_ids = {str(p.get('id')) for p in products}

        try:
            for iid in current_ids - new_ids:
                self.products_tree.delete(iid)

            for p in products:
                pid = str(p.get('id'))
                stock = p.get('stock_quantity', 0) or 0
                min_stock = p.get('min_stock_level', 10) or 10
                is_active = p.get('is_active', True)

                if not is_active:
                    tag = 'inactive'
                elif stock <= 0:
                    tag = 'out_of_stock'
                elif stock <= min_stock:
                    tag = 'low_stock'
                else:
                    tag = ''

                if not is_active:
                    stock_text = 'INACTIVE'
                elif stock <= 0:
                    stock_text = 'OUT'
                else:
                    stock_text = f"{stock}"

                values = (
                    p.get('name') or '—',
                    p.get('barcode') or '—',
                    f"₱{float(p.get('selling_price') or 0):,.2f}",
                    stock_text,
                )

                if pid in current_ids:
                    self.products_tree.item(pid, values=values,
                                            tags=(tag,) if tag else ())
                else:
                    self.products_tree.insert('', 'end', iid=pid, values=values,
                                              tags=(tag,) if tag else ())
        except Exception as e:
            log.debug("render products: %s", e)

        try:
            sellable = sum(1 for p in products
                           if p.get('is_active', True)
                           and (p.get('stock_quantity') or 0) > 0)
            self.product_count_label.config(text=f"{sellable} available")
        except Exception:
            pass

    def _on_product_double_click(self, event=None):
        if not self._alive():
            return
        try:
            sel = self.products_tree.selection()
            if not sel:
                return
            pid = int(sel[0])
            product = self.products_by_id.get(pid)
            if product:
                self._add_product_to_cart(product)
        except (ValueError, tk.TclError):
            pass

    def _add_product_to_cart(self, product):
        if not self._alive():
            return
        try:
            if product.get('is_active') is False:
                toast(self, f"{product.get('name')} is inactive", 'warning')
                return
            stock = product.get('stock_quantity', 0)
            if stock <= 0:
                toast(self, f"{product.get('name')} is out of stock", 'warning')
                return

            pid = product.get('id')
            existing = next((i for i in self.cart if i['id'] == pid), None)

            if existing:
                if existing['quantity'] >= stock:
                    toast(self, f"Only {stock} left of {product.get('name')}", 'warning')
                    return
                existing['quantity'] += 1
                self._update_cart_row(pid)
                self._recalc_totals()
            else:
                item = {
                    'id': pid, 'name': product.get('name'),
                    'price': float(product.get('selling_price', 0) or 0),
                    'quantity': 1, 'max_stock': stock,
                    'barcode': product.get('barcode'),
                }
                self.cart.append(item)
                self._append_cart_row(item)
                self._recalc_totals()

            self._update_cart_count()
            self._scroll_cart_to_bottom()
        except Exception as e:
            log.warning("add to cart failed: %s", e)

    def _append_cart_row(self, item):
        pid = item['id']
        if self.empty_cart_label is not None:
            try:
                self.empty_cart_label.pack_forget()
            except Exception:
                pass

        row = tk.Frame(self.cart_container, bg='#ffffff')
        row.pack(fill='x', padx=12, pady=6)

        top = tk.Frame(row, bg='#ffffff')
        top.pack(fill='x')

        name_label = tk.Label(top, text=item['name'] or '—',
                              font=('Segoe UI Semibold', 10),
                              bg='#ffffff', fg='#1a1a2e',
                              anchor='w', justify='left', wraplength=180)
        name_label.pack(side=tk.LEFT, anchor='w')

        total_label = tk.Label(top,
                               text=f"₱{item['price'] * item['quantity']:,.2f}",
                               font=('Segoe UI Semibold', 11),
                               bg='#ffffff', fg=self.ACCENT, anchor='e')
        total_label.pack(side=tk.RIGHT, anchor='e')

        price_label = tk.Label(row,
                               text=f"₱{item['price']:,.2f} × {item['quantity']}",
                               font=('Segoe UI', 8),
                               bg='#ffffff', fg='#6c757d', anchor='w')
        price_label.pack(fill='x', pady=(2, 6))

        ctrl = tk.Frame(row, bg='#ffffff')
        ctrl.pack(fill='x')

        def make_circle_button(parent, text, bg, fg, cmd):
            return tk.Button(parent, text=text,
                             font=('Segoe UI', 12, 'bold'),
                             bg=bg, fg=fg,
                             activebackground=bg, activeforeground=fg,
                             relief='flat', bd=0, cursor='hand2',
                             width=3, height=1, padx=0, pady=0,
                             command=cmd)

        minus_btn = make_circle_button(ctrl, "−", self.ACCENT, 'white',
                                       lambda pid=pid: self._cart_decrement(pid))
        minus_btn.pack(side=tk.LEFT)

        qty_label = tk.Label(ctrl, text=str(item['quantity']),
                             font=('Segoe UI Semibold', 12),
                             bg='#ffffff', fg='#1a1a2e', width=3)
        qty_label.pack(side=tk.LEFT, padx=6)

        plus_btn = make_circle_button(ctrl, "+", self.ACCENT, 'white',
                                      lambda pid=pid: self._cart_increment(pid))
        plus_btn.pack(side=tk.LEFT)

        tk.Frame(ctrl, bg='#ffffff').pack(side=tk.LEFT, expand=True, fill='x')

        remove_btn = make_circle_button(ctrl, "×", self.DANGER, 'white',
                                        lambda pid=pid: self._cart_remove(pid))
        remove_btn.pack(side=tk.RIGHT)

        if item['quantity'] >= item['max_stock']:
            try:
                plus_btn.config(state='disabled', bg='#adb5bd',
                                activebackground='#adb5bd')
            except Exception:
                pass

        sep = tk.Frame(self.cart_container, bg='#f1f3f5', height=1)
        sep.pack(fill='x', padx=12)

        self._cart_rows[pid] = {
            'row': row, 'sep': sep,
            'name_label': name_label, 'price_label': price_label,
            'qty_label': qty_label, 'total_label': total_label,
            'plus_btn': plus_btn, 'minus_btn': minus_btn, 'remove_btn': remove_btn,
        }

    def _update_cart_row(self, pid):
        item = next((i for i in self.cart if i['id'] == pid), None)
        refs = self._cart_rows.get(pid)
        if not item or not refs:
            return
        try:
            refs['price_label'].config(text=f"₱{item['price']:,.2f} × {item['quantity']}")
            refs['qty_label'].config(text=str(item['quantity']))
            refs['total_label'].config(
                text=f"₱{item['price'] * item['quantity']:,.2f}")
            at_max = item['quantity'] >= item['max_stock']
            if at_max:
                refs['plus_btn'].config(state='disabled', bg='#adb5bd',
                                        activebackground='#adb5bd')
            else:
                refs['plus_btn'].config(state='normal', bg=self.ACCENT,
                                        activebackground=self.ACCENT)
        except Exception as e:
            log.debug("update row: %s", e)

    def _destroy_cart_row(self, pid):
        refs = self._cart_rows.pop(pid, None)
        if not refs:
            return
        for key in ('row', 'sep'):
            w = refs.get(key)
            if w is not None:
                try:
                    w.destroy()
                except Exception:
                    pass
        if not self.cart and self.empty_cart_label is not None:
            try:
                self.empty_cart_label.pack(pady=60)
            except Exception:
                pass
        self._on_cart_container_configure()

    def _scroll_cart_to_bottom(self):
        try:
            self.cart_canvas.update_idletasks()
            self.cart_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _cart_increment(self, pid):
        item = next((i for i in self.cart if i['id'] == pid), None)
        if not item:
            return
        if item['quantity'] >= item['max_stock']:
            toast(self, f"Only {item['max_stock']} available", 'warning')
            return
        item['quantity'] += 1
        self._update_cart_row(pid)
        self._recalc_totals()
        self._update_cart_count()

    def _cart_decrement(self, pid):
        item = next((i for i in self.cart if i['id'] == pid), None)
        if not item:
            return
        item['quantity'] -= 1
        if item['quantity'] <= 0:
            self.cart = [i for i in self.cart if i['id'] != pid]
            self._destroy_cart_row(pid)
        else:
            self._update_cart_row(pid)
        self._recalc_totals()
        self._update_cart_count()

    def _cart_remove(self, pid):
        item = next((i for i in self.cart if i['id'] == pid), None)
        if not item:
            return
        self.cart = [i for i in self.cart if i['id'] != pid]
        self._destroy_cart_row(pid)
        self._recalc_totals()
        self._update_cart_count()

    def clear_cart(self):
        if not self.cart:
            return
        if not messagebox.askyesno("Clear Cart",
                                    "Remove all items from the cart?"):
            return
        for pid in list(self._cart_rows.keys()):
            self._destroy_cart_row(pid)
        self.cart = []
        self._recalc_totals()
        self._update_cart_count()

    def _update_cart_count(self):
        try:
            qty = sum(i['quantity'] for i in self.cart)
            self.cart_count_label.config(text=f"{qty} item{'s' if qty != 1 else ''}")
        except Exception:
            pass

    def _recalc_totals(self):
        try:
            subtotal = sum(i['price'] * i['quantity'] for i in self.cart)
            self.subtotal_label.config(text=f"₱{subtotal:,.2f}")
            self.total_label.config(text=f"₱{subtotal:,.2f}")
        except Exception:
            pass

    def _fetch_gcash_qr_bytes(self, full_url):
        try:
            req = urllib.request.Request(
                full_url, headers={'User-Agent': 'SariSariPOS-GUI/1.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
                if not data or len(data) < 4:
                    return None
                return data
        except Exception as e:
            log.warning("QR download failed: %s", e)
            return None

    def checkout(self):
        if not self.cart:
            toast(self, "Add items before checking out", 'warning')
            return

        total = sum(i['price'] * i['quantity'] for i in self.cart)

        dialog = tk.Toplevel(self)
        dialog.title("Payment")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, True)
        dialog.configure(bg='#f0f4f8')

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 230
        y = max(20, (dialog.winfo_screenheight() // 2) - 280)
        dialog.geometry(f"460x560+{x}+{y}")

        header = tk.Frame(dialog, bg='#ffffff',
                          highlightbackground='#e9ecef', highlightthickness=1)
        header.pack(fill='x', side=tk.TOP)
        hi = tk.Frame(header, bg='#ffffff')
        hi.pack(fill='x', padx=24, pady=16)
        tk.Label(hi, text="Complete Payment",
                 font=('Segoe UI', 14, 'bold'),
                 bg='#ffffff', fg='#1a1a2e').pack(anchor='w')
        tk.Label(hi, text=f"Total due: ₱{total:.2f}",
                 font=('Segoe UI', 10),
                 bg='#ffffff', fg=self.ACCENT).pack(anchor='w', pady=(2, 0))

        footer = tk.Frame(dialog, bg='#ffffff',
                          highlightbackground='#e9ecef', highlightthickness=1)
        footer.pack(fill='x', side=tk.BOTTOM)
        fi = tk.Frame(footer, bg='#ffffff')
        fi.pack(fill='x', padx=18, pady=14)

        tk.Button(fi, text="Cancel",
                  font=('Segoe UI', 10),
                  bg='#f8f9fa', fg='#6c757d',
                  relief='flat', bd=0, cursor='hand2',
                  activebackground='#e9ecef',
                  padx=20, pady=10,
                  command=dialog.destroy).pack(side=tk.RIGHT, padx=(8, 0))

        process_btn = tk.Button(fi, text="💰  Process Payment",
                                font=('Segoe UI Semibold', 10),
                                bg=self.ACCENT, fg='white',
                                relief='flat', bd=0, cursor='hand2',
                                activebackground=self.ACCENT_DARK,
                                padx=20, pady=10)
        process_btn.pack(side=tk.RIGHT)

        body_outer = tk.Frame(dialog, bg='#f0f4f8')
        body_outer.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(body_outer, bg='#f0f4f8', highlightthickness=0)
        sb = ttk.Scrollbar(body_outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill='y')

        body = tk.Frame(canvas, bg='#f0f4f8')
        bw = canvas.create_window((0, 0), window=body, anchor='nw')

        def _update_sr(e=None):
            try:
                canvas.configure(scrollregion=canvas.bbox('all'))
            except Exception:
                pass

        def _resize(e):
            try:
                canvas.itemconfig(bw, width=e.width)
            except Exception:
                pass

        body.bind('<Configure>', _update_sr)
        canvas.bind('<Configure>', _resize)

        body_pad = tk.Frame(body, bg='#f0f4f8')
        body_pad.pack(fill='both', expand=True, padx=18, pady=14)

        def make_card(parent, title):
            card = tk.Frame(parent, bg='#ffffff',
                            highlightbackground='#e9ecef', highlightthickness=1)
            card.pack(fill='x', pady=(0, 12))
            inner = tk.Frame(card, bg='#ffffff')
            inner.pack(fill='x', padx=18, pady=14)
            tk.Label(inner, text=title, font=('Segoe UI', 9, 'bold'),
                     bg='#ffffff', fg='#495057').pack(anchor='w', pady=(0, 10))
            return inner

        method_card = make_card(body_pad, "Payment Method")
        method_var = tk.StringVar(value='cash')
        method_row = tk.Frame(method_card, bg='#ffffff')
        method_row.pack(fill='x')

        tk.Radiobutton(method_row, text="💵  Cash",
                       variable=method_var, value='cash',
                       font=('Segoe UI', 10), bg='#ffffff', fg='#495057',
                       activebackground='#ffffff', selectcolor='#e6f4ea',
                       indicatoron=False, width=14, pady=10, bd=0,
                       highlightthickness=0, cursor='hand2',
                       command=lambda: on_method_change()
                       ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Radiobutton(method_row, text="📱  GCash",
                       variable=method_var, value='gcash',
                       font=('Segoe UI', 10), bg='#ffffff', fg='#495057',
                       activebackground='#ffffff', selectcolor='#e6f4ea',
                       indicatoron=False, width=14, pady=10, bd=0,
                       highlightthickness=0, cursor='hand2',
                       command=lambda: on_method_change()
                       ).pack(side=tk.LEFT)

        amount_card = make_card(body_pad, "Amount Received")
        amount_wrap = tk.Frame(amount_card, bg='#eef2f5')
        amount_wrap.pack(fill='x')

        amount_entry = tk.Entry(amount_wrap, font=('Segoe UI', 14, 'bold'),
                                bg='#f8f9fa', fg=self.ACCENT,
                                relief='flat', bd=0, justify='center',
                                highlightthickness=0,
                                insertbackground=self.ACCENT)
        amount_entry.pack(fill='x', ipady=10)
        amount_entry.insert(0, f"{total:.2f}")

        change_label = tk.Label(amount_card, text="Change: ₱0.00",
                                font=('Segoe UI', 10),
                                bg='#ffffff', fg=self.ACCENT, anchor='w')
        change_label.pack(fill='x', pady=(8, 0))

        def update_change(*args):
            try:
                amt = float(amount_entry.get() or 0)
                ch = amt - total
                if ch < 0:
                    change_label.config(text=f"Short by ₱{abs(ch):.2f}", fg='#dc3545')
                else:
                    change_label.config(text=f"Change: ₱{ch:.2f}", fg=self.ACCENT)
            except ValueError:
                change_label.config(text="Change: —", fg='#6c757d')

        amount_entry.bind('<KeyRelease>', update_change)

        gcash_card = tk.Frame(body_pad, bg='#e0f2ff',
                              highlightbackground='#b6dcff', highlightthickness=1)
        gcash_inner = tk.Frame(gcash_card, bg='#e0f2ff')
        gcash_inner.pack(fill='x', padx=18, pady=14)

        tk.Label(gcash_inner, text="📱  GCash Payment",
                 font=('Segoe UI', 10, 'bold'),
                 bg='#e0f2ff', fg='#0066cc').pack(anchor='w')
        tk.Label(gcash_inner,
                 text=("Ask customer to scan the QR. Then enter the last "
                       "3 digits of the reference."),
                 font=('Segoe UI', 8), bg='#e0f2ff', fg='#495057',
                 wraplength=360, justify='left').pack(anchor='w', pady=(2, 10))

        qr_container = tk.Frame(gcash_inner, bg='#ffffff',
                                width=170, height=170,
                                highlightbackground='#b6dcff', highlightthickness=1)
        qr_container.pack(pady=(0, 10))
        qr_container.pack_propagate(False)

        qr_image_label = tk.Label(qr_container, bg='#ffffff',
                                  text="Loading...",
                                  font=('Segoe UI', 9), fg='#8a94a0')
        qr_image_label.pack(fill=tk.BOTH, expand=True)

        qr_status_label = tk.Label(gcash_inner, text="",
                                   font=('Segoe UI', 8),
                                   bg='#e0f2ff', fg='#6c757d')
        qr_status_label.pack()

        tk.Label(gcash_inner, text="Last 3 digits of reference number",
                 font=('Segoe UI', 9, 'bold'),
                 bg='#e0f2ff', fg='#495057').pack(anchor='w', pady=(10, 6))

        ref_row = tk.Frame(gcash_inner, bg='#e0f2ff')
        ref_row.pack(fill='x')
        tk.Label(ref_row, text="•••• •••• ••",
                 font=('Consolas', 12, 'bold'),
                 bg='#e0f2ff', fg='#8a94a0').pack(side=tk.LEFT, padx=(0, 8))

        ref_entry = tk.Entry(ref_row, font=('Consolas', 15, 'bold'),
                             width=4, justify='center',
                             bg='#ffffff', relief='flat', bd=0,
                             highlightthickness=1,
                             highlightbackground='#b6dcff',
                             highlightcolor=self.ACCENT)
        ref_entry.pack(side=tk.LEFT, ipady=6, ipadx=6)

        ref_status = tk.Label(gcash_inner, text="",
                              font=('Segoe UI', 8),
                              bg='#e0f2ff', anchor='w')
        ref_status.pack(fill='x', pady=(6, 0))

        qr_photo_ref = {'photo': None}

        def load_gcash_qr():
            if self._gcash_qr_url is not None:
                _show_qr(self._gcash_qr_url)
                return

            def fetch():
                try:
                    response = Api.get(self.api_url, '/settings/gcash-qr',
                                       token=self.token, timeout=10)
                    if (response.get('success')
                            and response.get('data', {}).get('image_url')):
                        self._gcash_qr_url = response['data']['image_url']
                    else:
                        self._gcash_qr_url = ''
                    dialog.after(0, lambda: _show_qr(self._gcash_qr_url))
                except Exception as e:
                    log.warning("QR fetch: %s", e)
                    dialog.after(0, lambda: _show_qr(''))

            threading.Thread(target=fetch, daemon=True).start()

        def _show_qr(image_url):
            try:
                if not dialog.winfo_exists():
                    return
            except Exception:
                return

            if not image_url:
                qr_image_label.config(image='', text="No QR\nuploaded",
                                      font=('Segoe UI', 10), fg='#8a94a0')
                qr_status_label.config(
                    text="Ask the owner to upload a QR in Settings.",
                    fg='#dc3545')
                return

            if not _PIL_AVAILABLE:
                qr_image_label.config(image='', text="Pillow not installed",
                                      font=('Segoe UI', 9, 'bold'),
                                      fg='#dc3545')
                qr_status_label.config(
                    text="Run: pip install Pillow", fg='#dc3545')
                return

            server_root = self.api_url.replace('/api/v1', '')
            full_url = f"{server_root}{image_url}"

            def do_show():
                img_bytes = self._fetch_gcash_qr_bytes(full_url)
                dialog.after(0, lambda: _place_image(img_bytes))

            threading.Thread(target=do_show, daemon=True).start()

        def _place_image(img_bytes):
            try:
                if not dialog.winfo_exists():
                    return
            except Exception:
                return

            if not img_bytes:
                qr_image_label.config(image='', text="Download failed",
                                      font=('Segoe UI', 9), fg='#dc3545')
                qr_status_label.config(text="Could not download QR.", fg='#dc3545')
                return

            try:
                img = Image.open(BytesIO(img_bytes))
                img.thumbnail((160, 160))
                photo = ImageTk.PhotoImage(img)
                qr_photo_ref['photo'] = photo
                qr_image_label.config(image=photo, text='')
                qr_status_label.config(text="✓  QR ready", fg='#198754')
            except Exception as e:
                qr_image_label.config(image='', text="QR error",
                                      font=('Segoe UI', 9), fg='#dc3545')
                qr_status_label.config(text=f"{type(e).__name__}", fg='#dc3545')

        def validate_ref(*args):
            val = ref_entry.get().strip()
            cleaned = ''.join(c for c in val if c.isdigit())[:3]
            if cleaned != val:
                ref_entry.delete(0, tk.END)
                ref_entry.insert(0, cleaned)
            if len(cleaned) == 3:
                ref_status.config(text="✓  Reference accepted", fg='#198754')
                ref_entry.config(highlightbackground='#198754')
            else:
                remaining = 3 - len(cleaned)
                ref_status.config(
                    text=f"Enter {remaining} more digit{'s' if remaining != 1 else ''}",
                    fg='#dc3545')
                ref_entry.config(highlightbackground='#b6dcff')

        ref_entry.bind('<KeyRelease>', validate_ref)

        def on_method_change():
            if method_var.get() == 'gcash':
                gcash_card.pack(fill='x', pady=(0, 12))
                load_gcash_qr()
                amount_entry.delete(0, tk.END)
                amount_entry.insert(0, f"{total:.2f}")
                update_change()
                dialog.after(60, _update_sr)
                try:
                    ref_entry.focus_set()
                except Exception:
                    pass
            else:
                gcash_card.pack_forget()
                dialog.after(60, _update_sr)

        def process_payment():
            method = method_var.get()
            try:
                amount = float(amount_entry.get() or 0)
            except ValueError:
                messagebox.showerror("Error", "Invalid amount.")
                return
            if amount < total:
                messagebox.showwarning("Insufficient Payment",
                                       f"Amount must be at least ₱{total:.2f}")
                return

            payment_reference = None
            if method == 'gcash':
                ref = ref_entry.get().strip()
                if len(ref) != 3 or not ref.isdigit():
                    messagebox.showwarning("GCash Reference Required",
                                           "Enter the last 3 digits of the reference.")
                    return
                payment_reference = ref

            sale_data = {
                'items': [
                    {'product_id': i['id'], 'quantity': i['quantity'],
                     'selling_price': i['price']}
                    for i in self.cart
                ],
                'payment_method': method,
                'payment_amount': amount,
                'discount': 0,
                'customer_name': None,
            }
            if payment_reference:
                sale_data['payment_reference'] = payment_reference

            process_btn.config(text="⏳  Processing...",
                               state='disabled', bg='#6c757d')

            def task():
                return Api.post(self.api_url, '/sales', token=self.token,
                                json=sale_data, timeout=30)

            def ok(data):
                if not dialog.winfo_exists():
                    return
                process_btn.config(text="💰  Process Payment",
                                   state='normal', bg=self.ACCENT)
                if data.get('success'):
                    invoice = (data.get('data', {}).get('sale', {})
                               .get('invoice_number'))
                    change = amount - total
                    messagebox.showinfo(
                        "Payment Complete",
                        f"Sale recorded.\n\n"
                        f"Invoice: {invoice}\n"
                        f"Change: ₱{change:.2f}")
                    self.cart = []
                    for pid in list(self._cart_rows.keys()):
                        self._destroy_cart_row(pid)
                    self._recalc_totals()
                    self._update_cart_count()
                    self.load_products_async()
                    dialog.destroy()
                else:
                    msg = data.get('message', 'Sale failed')
                    details = data.get('details')
                    if details and isinstance(details, dict):
                        parts = []
                        for k, v in details.items():
                            if isinstance(v, list):
                                parts.append(f"{k}: {', '.join(v)}")
                            else:
                                parts.append(f"{k}: {v}")
                        msg = "\n".join(parts)
                    messagebox.showerror("Sale Failed", msg)

            def err(exc):
                if not dialog.winfo_exists():
                    return
                process_btn.config(text="💰  Process Payment",
                                   state='normal', bg=self.ACCENT)
                messagebox.showerror("Error", str(exc))

            async_call(widget=dialog, task=task, on_success=ok, on_error=err)

        process_btn.config(command=process_payment)
        on_method_change()
        dialog.after(100, _update_sr)
