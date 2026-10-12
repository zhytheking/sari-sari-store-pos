"""
Reusable UI helpers: async runner, debouncer, toast.
"""
import tkinter as tk
from tkinter import messagebox
import threading
from typing import Callable, Any, Optional


# ═══════════
# ASYNC CALL
# ═══════════

def async_call(
    widget: tk.Widget,
    task: Callable[[], Any],
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    on_finally: Optional[Callable[[], None]] = None,
) -> None:

    def alive() -> bool:
        try:
            return bool(widget.winfo_exists())
        except tk.TclError:
            return False

    def deliver(fn, *args):
        if not alive() or fn is None:
            return
        try:
            widget.after(0, lambda: _safe(fn, args))
        except tk.TclError:
            pass

    def _safe(fn, args):
        if not alive():
            return
        try:
            fn(*args)
        except tk.TclError:
            pass
        except Exception as e:
            print(f"[async_call] callback: {e}")

    def worker():
        try:
            result = task()
            deliver(on_success, result)
        except Exception as e:
            if on_error:
                deliver(on_error, e)
            else:
                deliver(
                    lambda err: messagebox.showerror("Error", str(err)),
                    e,
                )
        finally:
            deliver(on_finally)

    threading.Thread(target=worker, daemon=True).start()


# ══════════
# DEBOUNCER
# ══════════

class Debouncer:
    def __init__(self, widget: tk.Widget, delay_ms: int = 200):
        self.widget = widget
        self.delay_ms = delay_ms
        self._aid: Optional[str] = None

    def call(self, fn: Callable[[], None]) -> None:
        self.cancel()
        try:
            self._aid = self.widget.after(self.delay_ms, self._fire, fn)
        except tk.TclError:
            self._aid = None

    def _fire(self, fn):
        self._aid = None
        try:
            if self.widget.winfo_exists():
                fn()
        except tk.TclError:
            pass
        except Exception as e:
            print(f"[debounce] {e}")

    def cancel(self) -> None:
        if self._aid is not None:
            try:
                self.widget.after_cancel(self._aid)
            except Exception:
                pass
            self._aid = None


# ═════
# TOAST
# ═════

_active_toasts: list = []


def toast(parent: tk.Widget, message: str, kind: str = "info",
          duration_ms: int = 2800) -> None:
    try:
        root = parent.winfo_toplevel()
    except tk.TclError:
        return

    colors = {
        'info':    ('#0dcaf0', '#055160', 'ℹ'),
        'success': ('#198754', '#ffffff', '✓'),
        'error':   ('#dc3545', '#ffffff', '✕'),
        'warning': ('#ffc107', '#212529', '!'),
    }
    bg, fg, icon = colors.get(kind, colors['info'])

    try:
        t = tk.Toplevel(root)
    except tk.TclError:
        return

    t.overrideredirect(True)
    try:
        t.attributes('-topmost', True)
    except tk.TclError:
        pass
    t.configure(bg=bg)

    frame = tk.Frame(t, bg=bg, padx=16, pady=10)
    frame.pack(fill=tk.BOTH, expand=True)

    tk.Label(frame, text=icon, font=('Segoe UI', 12, 'bold'),
             bg=bg, fg=fg).pack(side=tk.LEFT, padx=(0, 10))
    tk.Label(frame, text=message, font=('Segoe UI', 10),
             bg=bg, fg=fg, wraplength=320,
             justify=tk.LEFT).pack(side=tk.LEFT)

    # Position at top-right of the parent window
    try:
        root.update_idletasks()
        t.update_idletasks()
        w = t.winfo_width()
        h = t.winfo_height()
        x = root.winfo_rootx() + root.winfo_width() - w - 24
        y = root.winfo_rooty() + 24 + len(_active_toasts) * (h + 8)
        t.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass

    _active_toasts.append(t)

    def dismiss():
        if t in _active_toasts:
            _active_toasts.remove(t)
        try:
            t.destroy()
        except tk.TclError:
            pass

    try:
        t.after(duration_ms, dismiss)
    except tk.TclError:
        pass
    t.bind("<Button-1>", lambda e: dismiss())
