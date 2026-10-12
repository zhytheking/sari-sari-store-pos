"""
Web Access Panel — auto-detects the LAN IP and shows the web app URL.
Owners can copy it or open it in their browser without knowing the IP.
"""
import socket
import tkinter as tk
import webbrowser


def detect_lan_ip() -> str:
   #Detect the machine's LAN IP. Returns '127.0.0.1' on failure
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

#Return the full URL the owner should type on their phone
def get_web_url(port: int = 5000) -> str:
    return f"http://{detect_lan_ip()}:{port}"


class WebAccessPanel(tk.Frame):
    """
    A card showing the LAN URL for the web app.
    Buttons: Copy URL, Open in Browser, Refresh.
    """

    ACCENT = '#2d6a4f'
    ACCENT_DARK = '#1b4332'
    BG = '#ffffff'
    BG_SOFT = '#f0fdf4'
    BORDER = '#52b788'
    TEXT = '#1a1a2e'
    TEXT_MUTED = '#6c757d'
    DANGER = '#dc3545'

    def __init__(self, parent, port: int = 5000, **kwargs):
        super().__init__(parent, bg=self.BG, **kwargs)
        self.port = port
        self.lan_ip = detect_lan_ip()
        self._build()

    def _build(self):
        card = tk.Frame(
            self,
            bg=self.BG_SOFT,
            highlightbackground=self.BORDER,
            highlightthickness=2,
        )
        card.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        inner = tk.Frame(card, bg=self.BG_SOFT)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)

        # ── Header ──
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

        # ── Description ──
        tk.Label(
            inner,
            text="Open this address in any browser on the same WiFi:",
            font=('Segoe UI', 9),
            bg=self.BG_SOFT, fg=self.TEXT_MUTED, anchor='w',
        ).pack(fill='x', pady=(10, 6))

        # ── URL box ──
        url_row = tk.Frame(
            inner, bg='#ffffff',
            highlightbackground=self.BORDER, highlightthickness=1,
        )
        url_row.pack(fill='x')

        self.url_var = tk.StringVar()
        tk.Entry(
            url_row,
            textvariable=self.url_var,
            font=('Consolas', 14, 'bold'),
            bg='#ffffff', fg=self.ACCENT,
            relief='flat', bd=0,
            state='readonly',
            readonlybackground='#ffffff',
            justify='center',
        ).pack(fill='x', ipady=14, padx=8)

        # ── Buttons ──
        btn_row = tk.Frame(inner, bg=self.BG_SOFT)
        btn_row.pack(fill='x', pady=(12, 0))

        self._button(btn_row, "📋  Copy URL", self._copy,
                     bg=self.ACCENT).pack(side=tk.LEFT, expand=True,
                                           fill='x', padx=(0, 4))
        self._button(btn_row, "🌐  Open in Browser", self._open,
                     bg='#0d6efd').pack(side=tk.LEFT, expand=True,
                                         fill='x', padx=(4, 4))
        self._button(btn_row, "🔄  Refresh", self.refresh,
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
        self.lan_ip = detect_lan_ip()
        url = f"http://{self.lan_ip}:{self.port}"
        self.url_var.set(url)

        if self.lan_ip == "127.0.0.1":
            self.status.config(
                text="⚠️  No LAN connection. Connect to WiFi to enable remote access.",
                fg=self.DANGER,
            )
        else:
            self.status.config(
                text="✅  Ready — any device on this WiFi can connect.",
                fg=self.ACCENT,
            )

    def _copy(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.url_var.get())
            self.status.config(text="✅  Copied to clipboard!", fg=self.ACCENT)
            self.after(2500, self.refresh)
        except Exception as e:
            self.status.config(text=f"Copy failed: {e}", fg=self.DANGER)

    def _open(self):
        try:
            webbrowser.open(self.url_var.get())
            self.status.config(text="✅  Opening in browser...", fg=self.ACCENT)
            self.after(2500, self.refresh)
        except Exception as e:
            self.status.config(text=f"Open failed: {e}", fg=self.DANGER)
