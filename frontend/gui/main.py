
#Main entry point for the GUI application.

import sys
import os
from pathlib import Path

if getattr(sys, 'frozen', False):
    # Running as a PyInstaller bundle
    project_root = Path(sys.executable).resolve().parent
else:
    # Running from source
    project_root = Path(__file__).resolve().parent.parent.parent

for _p in (str(project_root), str(project_root / 'backend'), str(project_root / 'frontend')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import tkinter as tk
from tkinter import messagebox


class POSApplication:
    #Main application class

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("POS Inventory Management System")
        self.root.geometry("1200x750")
        self.root.minsize(1000, 650)
        self._destroyed = False

        self._apply_window_icon()

        self.center_window()
        self.token = None
        self.user = None
        self.current_window = None

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.show_login()

    # ═════════════
    # WINDOW ICON
    # ═════════════

    def _apply_window_icon(self):
        candidates = [
            project_root / "frontend" / "web" / "static" / "assets" / "images" / "pos.ico",
            project_root / "frontend" / "web" / "static" / "assets" / "images" / "favicon.ico",
            project_root / "frontend" / "web" / "static" / "assets" / "images" / "pos.png",
            project_root / "frontend" / "web" / "static" / "assets" / "images" / "icon.ico",
            project_root / "frontend" / "web" / "static" / "favicon.ico",
            project_root / "assets" / "pos.ico",
            project_root / "pos.ico",
        ]

        # Also scan the images folder for any .ico file
        images_dir = project_root / "frontend" / "web" / "static" / "assets" / "images"
        if images_dir.is_dir():
            try:
                for f in images_dir.glob("*.ico"):
                    candidates.append(f)
            except Exception:
                pass

        for path in candidates:
            try:
                if path.exists() and path.is_file():
                    # .ico → iconbitmap (Windows-native)
                    if path.suffix.lower() == ".ico":
                        self.root.iconbitmap(default=str(path))
                        # Second call helps the taskbar update on some Windows builds
                        try:
                            self.root.iconbitmap(str(path))
                        except Exception:
                            pass
                        print(f"[GUI] Icon loaded from: {path}")
                        return

                    # .png fallback via Pillow (if available)
                    if path.suffix.lower() == ".png":
                        try:
                            from PIL import Image, ImageTk
                            img = Image.open(path)
                            photo = ImageTk.PhotoImage(img)
                            self.root.iconphoto(True, photo)
                            # Keep a reference so Tkinter doesn't GC it
                            self.root._icon_photo = photo
                            print(f"[GUI] Icon loaded from PNG: {path}")
                            return
                        except ImportError:
                            print(f"[GUI] Pillow not installed — cannot load PNG icon")
                        except Exception as e:
                            print(f"[GUI] PNG icon load failed: {e}")
            except Exception as e:
                print(f"[GUI] Icon candidate failed ({path}): {e}")

        print("[GUI] No window icon found. Continuing without one.")

    # ════════════════════
    # WINDOW POSITIONING
    # ════════════════════
    def center_window(self):
        try:
            self.root.update_idletasks()
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            x = (self.root.winfo_screenwidth() // 2) - (width // 2)
            y = (self.root.winfo_screenheight() // 2) - (height // 2)
            self.root.geometry(f'{width}x{height}+{x}+{y}')
        except Exception:
            pass

    # ════════════
    # WINDOW FLOW
    # ════════════
    def show_login(self):
        if self._destroyed:
            return

        if self.current_window:
            try:
                self.current_window.destroy()
            except Exception:
                pass
            self.current_window = None

        try:
            from frontend.gui.windows.login_window import LoginWindow
        except Exception as e:
            print(f"Error importing LoginWindow: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to load login: {e}")
            return

        try:
            self.current_window = LoginWindow(self.root, self.on_login_success)
            self.current_window.pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            print(f"Error creating LoginWindow: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to create login: {e}")

    def on_login_success(self, user):
        if self._destroyed:
            return

        print(f"[LOGIN] Success! User: {user.get('username', 'Unknown')}")

        if self.current_window:
            try:
                self.current_window.destroy()
                self.current_window = None
            except Exception as e:
                print(f"Error destroying login window: {e}")

        try:
            from frontend.gui.windows.main_window import MainWindow
            self.current_window = MainWindow(self.root, user, self.on_logout)
            self.current_window.pack(fill=tk.BOTH, expand=True)
            self.root.update_idletasks()
            print("[LOGIN] Main window loaded successfully")
        except Exception as e:
            print(f"[LOGIN] Error creating main window: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to load dashboard: {e}")
            self.show_login()

    def on_logout(self):
        if self._destroyed:
            return
        print("[LOGIN] Logging out...")
        self.token = None
        self.user = None
        self.show_login()

    # ══════════
    # SHUTDOWN
    # ══════════
    def on_closing(self):
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            self._destroyed = True
            try:
                self.root.destroy()
            except Exception:
                pass
            sys.exit(0)

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._destroyed = True
            try:
                self.root.destroy()
            except Exception:
                pass
            sys.exit(0)


def main():
    try:
        app = POSApplication()
        app.run()
    except KeyboardInterrupt:
        print("\nApplication stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
