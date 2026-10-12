
#Login window

import tkinter as tk
from tkinter import ttk
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from frontend.gui.api import Api, ApiError
from frontend.gui.config import get_api_url
from frontend.gui.ui import async_call, toast


class LoginWindow(tk.Frame):
    """Professional login window."""

    # Palette
    BG_DARK      = '#0b1e14'
    BG_MID       = '#123524'
    BG_DECOR     = '#1c5236'
    CARD_BG      = '#ffffff'
    ACCENT       = '#2d6a4f'
    ACCENT_HOVER = '#1b4332'
    TEXT_MAIN    = '#1a1a2e'
    TEXT_SUB     = '#6c757d'
    TEXT_HINT    = '#adb5bd'
    BORDER       = '#dee2e6'
    INPUT_BG     = '#f8f9fa'
    ERROR        = '#dc3545'
    SUCCESS      = '#198754'

    def __init__(self, parent, on_success):
        super().__init__(parent)
        self.parent = parent
        self.on_success = on_success
        self.api_url = get_api_url()

        self._loading = False
        self._bg_job = None
        self._role_var = tk.StringVar(value='owner')
        self._password_visible = False

        # Store name label — populated from the API after UI is built
        self.store_name_label = None

        self.setup_ui()

        # Load the store name from the public endpoint
        self.after(300, self._load_store_name_from_api)

    # ══════════
    # LIFECYCLE
    # ══════════
    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def destroy(self):
        if self._bg_job is not None:
            try:
                self.after_cancel(self._bg_job)
            except Exception:
                pass
            self._bg_job = None
        try:
            super().destroy()
        except Exception:
            pass

    # ═════════════════════
    # STORE NAME LOADER
    # ═════════════════════
    def _load_store_name_from_api(self):
        if not self._alive():
            return

        def task():
            return Api.get(
                self.api_url,
                '/settings/public-no-auth',
                timeout=8,
            )

        def done(data):
            if not self._alive():
                return
            if data.get('success'):
                name = data['data'].get('store_name', 'Saliga')
                if self.store_name_label is not None:
                    try:
                        self.store_name_label.config(text=name)
                    except Exception:
                        pass

        async_call(widget=self, task=task, on_success=done,
                   on_error=lambda e: None)

    # ═══
    # UI
    # ═══
    def setup_ui(self):
        self.configure(bg=self.BG_DARK)
        self.pack(fill=tk.BOTH, expand=True)

        # Background canvas
        self.bg_canvas = tk.Canvas(self, bg=self.BG_DARK,
                                    highlightthickness=0)
        self.bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bind('<Configure>', self._on_resize)

        # ── Centered card ──
        center = tk.Frame(self, bg=self.BG_DARK)
        center.place(relx=0.5, rely=0.5, anchor='center')

        # Shadow
        shadow = tk.Frame(center, bg='#000000')
        shadow.place(x=6, y=8, relwidth=1, relheight=1)

        # Card
        card = tk.Frame(center, bg=self.CARD_BG,
                        highlightbackground='#c8d1d9',
                        highlightthickness=1)
        card.pack()

        # ── HEADER ──
        header = tk.Frame(card, bg=self.ACCENT)
        header.pack(fill='x')

        tk.Label(header, text="🏪",
                 font=('Segoe UI Emoji', 40),
                 bg=self.ACCENT, fg='white').pack(pady=(28, 0))

        self.store_name_label = tk.Label(
            header, text="Saliga ",
            font=('Segoe UI Semibold', 22),
            bg=self.ACCENT, fg='white')
        self.store_name_label.pack(pady=(8, 0))

        tk.Label(header, text="Sari-Sari Store POS",
                 font=('Segoe UI', 10),
                 bg=self.ACCENT, fg='#b7e4c7').pack(pady=(2, 0))

        # Decorative dots
        dots = tk.Frame(header, bg=self.ACCENT)
        dots.pack(pady=(14, 24))
        for i in range(3):
            tk.Label(dots, text="•", font=('Segoe UI', 14),
                     bg=self.ACCENT,
                     fg='#95d5b2' if i == 1 else '#52b788'
                     ).pack(side=tk.LEFT, padx=3)

        # ── BODY ──
        body = tk.Frame(card, bg=self.CARD_BG)
        body.pack(fill='x', padx=42, pady=(30, 14))

        tk.Label(body, text="Welcome back",
                 font=('Segoe UI Semibold', 17),
                 bg=self.CARD_BG, fg=self.TEXT_MAIN,
                 anchor='w').pack(fill='x')

        tk.Label(body, text="Sign in with your staff credentials",
                 font=('Segoe UI', 10),
                 bg=self.CARD_BG, fg=self.TEXT_SUB,
                 anchor='w').pack(fill='x', pady=(4, 24))

        # ── ROLE SELECTOR ──
        tk.Label(body, text="ACCOUNT TYPE",
                 font=('Segoe UI Semibold', 8),
                 bg=self.CARD_BG, fg=self.TEXT_HINT,
                 anchor='w').pack(fill='x', pady=(0, 8))

        seg_outer = tk.Frame(body, bg='#f1f3f5',
                             highlightbackground='#dee2e6',
                             highlightthickness=1)
        seg_outer.pack(fill='x', pady=(0, 24))

        seg = tk.Frame(seg_outer, bg='#f1f3f5')
        seg.pack(fill='x', padx=4, pady=4)

        self.owner_btn = self._make_role_btn(seg, "👑  Owner", 'owner')
        self.owner_btn.pack(side=tk.LEFT, fill='x', expand=True)

        self.cashier_btn = self._make_role_btn(seg, "🛒  Cashier", 'cashier')
        self.cashier_btn.pack(side=tk.LEFT, fill='x', expand=True)

        # ── USERNAME ──
        tk.Label(body, text="USERNAME",
                 font=('Segoe UI Semibold', 8),
                 bg=self.CARD_BG, fg=self.TEXT_HINT,
                 anchor='w').pack(fill='x', pady=(0, 6))

        self.user_wrap = tk.Frame(body, bg=self.BORDER)
        self.user_wrap.pack(fill='x', pady=(0, 18))

        self.username_entry = tk.Entry(
            self.user_wrap,
            font=('Segoe UI', 12),
            bg=self.INPUT_BG, fg=self.TEXT_MAIN,
            relief='flat', bd=0,
            highlightthickness=0,
            insertbackground=self.ACCENT,
        )
        self.username_entry.pack(fill='x', ipady=12, padx=2, pady=2)

        # ── PASSWORD ──
        tk.Label(body, text="PASSWORD",
                 font=('Segoe UI Semibold', 8),
                 bg=self.CARD_BG, fg=self.TEXT_HINT,
                 anchor='w').pack(fill='x', pady=(0, 6))

        self.pass_wrap = tk.Frame(body, bg=self.BORDER)
        self.pass_wrap.pack(fill='x')

        pw_inner = tk.Frame(self.pass_wrap, bg=self.INPUT_BG)
        pw_inner.pack(fill='x', padx=2, pady=2)

        self.password_entry = tk.Entry(
            pw_inner,
            font=('Segoe UI', 12),
            bg=self.INPUT_BG, fg=self.TEXT_MAIN,
            relief='flat', bd=0,
            highlightthickness=0,
            show='•',
            insertbackground=self.ACCENT,
        )
        self.password_entry.pack(side=tk.LEFT, fill='x', expand=True,
                                  ipady=12, padx=(12, 0))

        self.toggle_btn = tk.Button(
            pw_inner, text="👁",
            font=('Segoe UI', 11),
            bg=self.INPUT_BG, fg='#6c757d',
            relief='flat', bd=0,
            activebackground=self.INPUT_BG,
            cursor='hand2',
            command=self.toggle_password_visibility,
            padx=12,
        )
        self.toggle_btn.pack(side=tk.RIGHT)

        # ── STATUS ──
        self.status_label = tk.Label(body, text="",
                                     font=('Segoe UI', 9),
                                     bg=self.CARD_BG, fg=self.ERROR,
                                     wraplength=340, justify='center',
                                     anchor='w')
        self.status_label.pack(fill='x', pady=(14, 0))

        # ── SIGN IN BUTTON ──
        self.login_btn = tk.Button(
            body, text="Sign In",
            font=('Segoe UI Semibold', 12),
            bg=self.ACCENT, fg='white',
            relief='flat', bd=0, cursor='hand2',
            activebackground=self.ACCENT_HOVER,
            activeforeground='white',
            pady=14,
            command=self.handle_login,
        )
        self.login_btn.pack(fill='x', pady=(14, 0))
        self.login_btn.bind(
            '<Enter>',
            lambda e: self.login_btn.config(bg=self.ACCENT_HOVER)
            if self.login_btn['state'] == 'normal' else None,
        )
        self.login_btn.bind(
            '<Leave>',
            lambda e: self.login_btn.config(bg=self.ACCENT)
            if self.login_btn['state'] == 'normal' else None,
        )

        # ── FOOTER ──
        footer = tk.Frame(card, bg='#f8f9fa')
        footer.pack(fill='x', side=tk.BOTTOM)

        footer_inner = tk.Frame(footer, bg='#f8f9fa')
        footer_inner.pack(pady=14)

        tk.Label(footer_inner, text="Demo login:",
                 font=('Segoe UI', 8),
                 bg='#f8f9fa', fg=self.TEXT_HINT
                 ).pack(side=tk.LEFT, padx=(0, 8))

        owner_link = tk.Label(footer_inner, text="Owner",
                              font=('Segoe UI', 8, 'underline'),
                              bg='#f8f9fa', fg=self.ACCENT,
                              cursor='hand2')
        owner_link.pack(side=tk.LEFT)
        owner_link.bind('<Button-1>', lambda e: self.quick_fill('owner'))

        tk.Label(footer_inner, text="•",
                 font=('Segoe UI', 8),
                 bg='#f8f9fa', fg='#dee2e6').pack(side=tk.LEFT, padx=8)

        cashier_link = tk.Label(footer_inner, text="Cashier",
                                font=('Segoe UI', 8, 'underline'),
                                bg='#f8f9fa', fg='#e76f51',
                                cursor='hand2')
        cashier_link.pack(side=tk.LEFT)
        cashier_link.bind('<Button-1>', lambda e: self.quick_fill('cashier'))

        # ── KEYBOARD BINDINGS ──
        self.username_entry.bind('<Return>',
                                  lambda e: self.password_entry.focus())
        self.password_entry.bind('<Return>',
                                  lambda e: self.handle_login())

        # ── FOCUS VISUALS ──
        self.username_entry.bind(
            '<FocusIn>',
            lambda e: self.user_wrap.config(bg=self.ACCENT))
        self.username_entry.bind(
            '<FocusOut>',
            lambda e: self.user_wrap.config(bg=self.BORDER))
        self.password_entry.bind(
            '<FocusIn>',
            lambda e: self.pass_wrap.config(bg=self.ACCENT))
        self.password_entry.bind(
            '<FocusOut>',
            lambda e: self.pass_wrap.config(bg=self.BORDER))

        self._update_role_visuals()

        # Focus username after a short delay (widget must be mapped first)
        self.after(250, self._focus_username)

    def _make_role_btn(self, parent, text, value):
        return tk.Radiobutton(
            parent, text=text,
            variable=self._role_var, value=value,
            font=('Segoe UI Semibold', 11),
            bg='#f1f3f5', fg='#495057',
            activebackground=self.ACCENT,
            activeforeground='white',
            selectcolor=self.ACCENT,
            indicatoron=False,
            pady=11, bd=0, highlightthickness=0,
            cursor='hand2',
            command=self._update_role_visuals,
        )

    def _focus_username(self):
        if not self._alive():
            return
        try:
            self.username_entry.focus_set()
        except Exception:
            pass

    # ══════════════
    # ROLE VISUALS
    # ══════════════
    def _update_role_visuals(self):
        
        try:
            if self._role_var.get() == 'owner':
                self.owner_btn.config(bg=self.ACCENT, fg='white',
                                       selectcolor=self.ACCENT)
                self.cashier_btn.config(bg='#f1f3f5', fg='#495057',
                                         selectcolor='#f1f3f5')
            else:
                self.cashier_btn.config(bg=self.ACCENT, fg='white',
                                         selectcolor=self.ACCENT)
                self.owner_btn.config(bg='#f1f3f5', fg='#495057',
                                       selectcolor='#f1f3f5')
        except Exception:
            pass

    # ════════════
    # BACKGROUND
    # ════════════
    def _on_resize(self, event):
        if not self._alive():
            return
        if self._bg_job is not None:
            try:
                self.after_cancel(self._bg_job)
            except Exception:
                pass
        try:
            self._bg_job = self.after(150, self._draw_background)
        except Exception:
            self._bg_job = None

    def _draw_background(self):
        self._bg_job = None
        if not self._alive():
            return

        try:
            c = self.bg_canvas
            c.delete('all')
            w = c.winfo_width()
            h = c.winfo_height()
            if w < 10 or h < 10:
                return

            # Two soft ovals for gradient feel
            c.create_oval(-int(w * 0.4), -int(h * 0.4),
                          int(w * 0.7), int(h * 0.7),
                          fill=self.BG_MID, outline='')
            c.create_oval(w - int(w * 0.4), h - int(h * 0.4),
                          w + int(w * 0.4), h + int(h * 0.4),
                          fill=self.BG_MID, outline='')

            # Top-right concentric circles
            cx, cy = w - 80, 60
            for i in range(6):
                r = 100 + i * 70
                c.create_oval(cx - r, cy - r, cx + r, cy + r,
                              outline=self.BG_DECOR, width=1)

            # Bottom-left concentric circles
            cx2, cy2 = 80, h - 80
            for i in range(5):
                r = 80 + i * 60
                c.create_oval(cx2 - r, cy2 - r, cx2 + r, cy2 + r,
                              outline=self.BG_DECOR, width=1)

            # Faint diagonal lines
            for i in range(6):
                off = i * 110
                c.create_line(w - off - 150, 0,
                              w - off - 450, h,
                              fill=self.BG_DECOR, width=1)
        except Exception as e:
            print(f"[Login] bg: {e}")

    # ══════
    # EVENTS
    # ═══════
    def toggle_password_visibility(self):
        if not self._alive():
            return
        if self._password_visible:
            self.password_entry.config(show='•')
            self.toggle_btn.config(text="👁")
            self._password_visible = False
        else:
            self.password_entry.config(show='')
            self.toggle_btn.config(text="🙈")
            self._password_visible = True

    def quick_fill(self, role):
        #Fill form with the demo credentials for the given role
        if not self._alive():
            return
        try:
            if role == 'owner':
                self.username_entry.delete(0, tk.END)
                self.username_entry.insert(0, 'admin')
                self.password_entry.delete(0, tk.END)
                self.password_entry.insert(0, 'admin123')
                self._role_var.set('owner')
            else:
                self.username_entry.delete(0, tk.END)
                self.username_entry.insert(0, 'cashier')
                self.password_entry.delete(0, tk.END)
                self.password_entry.insert(0, 'cashier123')
                self._role_var.set('cashier')

            self._update_role_visuals()
            self.status_label.config(
                text=f"✓ Filled demo {role} credentials — click Sign In",
                fg=self.SUCCESS,
            )
            self.after(2200, self._clear_status_if_alive)
        except Exception:
            pass

    def _clear_status_if_alive(self):
        if not self._alive():
            return
        try:
            self.status_label.config(text="")
        except Exception:
            pass

    # ═══════
    # LOGIN
    # ═══════
    def handle_login(self):
        if not self._alive() or self._loading:
            return

        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        role = self._role_var.get()

        if not username or not password:
            self.status_label.config(
                text="Please enter your username and password",
                fg=self.ERROR,
            )
            return

        # Disable button during request
        self.login_btn.config(text="Signing in...",
                              state='disabled',
                              bg='#6c757d')
        self.status_label.config(text="Authenticating...", fg=self.ACCENT)
        self._loading = True

        async_call(
            widget=self,
            task=lambda: Api.post(
                self.api_url, '/auth/login',
                json={
                    'username': username,
                    'password': password,
                    'role': role,
                },
                timeout=15,
            ),
            on_success=self._on_login_result,
            on_error=self._on_login_error,
        )

    def _on_login_result(self, data):
        self._loading = False
        if not self._alive():
            return

        if data.get('success'):
            user_data = data.get('data', {}).get('user', {})
            token = data.get('data', {}).get('access_token')

            try:
                self.parent.token = token
                self.parent.user = user_data
            except Exception:
                pass

            role_label = user_data.get('role', 'user').title()
            self.status_label.config(
                text=f"✓ Signed in as {role_label}",
                fg=self.SUCCESS,
            )
            self.login_btn.config(text="Sign In",
                                   state='normal',
                                   bg=self.ACCENT)

            # Small delay so the user sees the success message
            self.after(280, lambda: self._dispatch_success(user_data))
        else:
            # Success=False in JSON — treat as error
            self._on_login_error(
                ApiError(data.get('message', 'Login failed'),
                         payload=data)
            )

    def _dispatch_success(self, user_data):
        if not self._alive():
            return
        try:
            if self.on_success:
                self.on_success(user_data)
        except Exception as e:
            print(f"[Login] on_success callback: {e}")

    def _on_login_error(self, exc):
        self._loading = False
        if not self._alive():
            return

        # Extract a friendly message
        if isinstance(exc, ApiError):
            msg = exc.message
        else:
            msg = str(exc) or "Login failed"

        # Special-case common error codes from the backend
        payload = getattr(exc, 'payload', {}) or {}
        code = payload.get('error', '')

        if code == 'role_mismatch':
            msg = f"Role mismatch — {msg}"
        elif code == 'account_locked':
            msg = f"Account locked — {msg}"
        elif code == 'account_inactive':
            msg = f"Account inactive — {msg}"

        self.status_label.config(text=msg, fg=self.ERROR)
        self.login_btn.config(text="Sign In",
                               state='normal',
                               bg=self.ACCENT)

        try:
            self.password_entry.delete(0, tk.END)
            self.password_entry.focus_set()
        except Exception:
            pass
