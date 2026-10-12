#Camera-based QR/barcode scanner dialog.


import tkinter as tk
from tkinter import messagebox
import threading
import time

from frontend.gui.logger import get_logger

log = get_logger(__name__)


class ScannerDialog(tk.Toplevel):

    def __init__(self, parent, on_scan=None, camera_index=0):
        super().__init__(parent)
        self.parent = parent
        self.on_scan = on_scan
        self.camera_index = camera_index
        self.result = None

        self._running = True
        self._cap = None
        self._thread = None
        self._last_scanned = None
        self._cooldown_until = 0.0

        self.title("Scan QR / Barcode")
        self.geometry("660x620")
        self.resizable(False, False)
        self.transient(parent)
        self.configure(bg='#0f2a1c')
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self.after(200, self._start_camera)

    def _build_ui(self):
        header = tk.Frame(self, bg='#2d6a4f')
        header.pack(fill='x')

        tk.Label(header, text="📷  Scan QR / Barcode",
                 font=('Segoe UI Semibold', 14),
                 bg='#2d6a4f', fg='white').pack(pady=14)

        video_holder = tk.Frame(self, bg='#000000', width=600, height=400)
        video_holder.pack(pady=(18, 10))
        video_holder.pack_propagate(False)

        self.video_label = tk.Label(video_holder, bg='#000000',
                                    text="Starting camera...",
                                    font=('Segoe UI', 12), fg='#adb5bd')
        self.video_label.pack(fill='both', expand=True)

        self.status = tk.Label(self, text="",
                               font=('Segoe UI', 10),
                               bg='#0f2a1c', fg='#adb5bd')
        self.status.pack(pady=(0, 8))

        manual_row = tk.Frame(self, bg='#0f2a1c')
        manual_row.pack(fill='x', padx=20, pady=(4, 10))

        tk.Label(manual_row, text="Or type code:",
                 font=('Segoe UI', 9),
                 bg='#0f2a1c', fg='#adb5bd').pack(side=tk.LEFT)

        self.manual_var = tk.StringVar()
        manual_entry = tk.Entry(manual_row, textvariable=self.manual_var,
                                font=('Consolas', 12),
                                bg='#ffffff', fg='#1a1a2e',
                                relief='flat', bd=0)
        manual_entry.pack(side=tk.LEFT, fill='x', expand=True, padx=8, ipady=6)
        manual_entry.bind('<Return>', lambda e: self._manual_submit())

        tk.Button(manual_row, text="Submit",
                  font=('Segoe UI', 9, 'bold'),
                  bg='#2d6a4f', fg='white',
                  relief='flat', bd=0, cursor='hand2',
                  padx=14, pady=6,
                  command=self._manual_submit).pack(side=tk.LEFT)

        btn_row = tk.Frame(self, bg='#0f2a1c')
        btn_row.pack(fill='x', padx=20, pady=(0, 16))

        tk.Button(btn_row, text="Cancel",
                  font=('Segoe UI', 10),
                  bg='#6c757d', fg='white',
                  relief='flat', bd=0, cursor='hand2',
                  padx=20, pady=8,
                  command=self._on_close).pack(side=tk.RIGHT)

        manual_entry.focus_set()

    def _start_camera(self):
        try:
            import cv2
        except ImportError:
            self._show_no_camera(
                "OpenCV is not installed.\n\n"
                "Install it with:\n"
                "    python -m pip install opencv-python pyzbar pillow")
            return

        self._cap = None
        last_error = None
        for idx in [self.camera_index, 0, 1, 2]:
            try:
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        self._cap = cap
                        break
                    cap.release()
                else:
                    cap.release()
            except Exception as e:
                last_error = str(e)
                continue

        if self._cap is None:
            self._show_no_camera(
                "No camera detected.\n\n"
                "Laptop: the built-in webcam should work.\n"
                "PC without webcam: install DroidCam or Iriun Webcam\n"
                "on your phone and PC — they create a virtual webcam\n"
                "that this scanner uses automatically.\n\n"
                + (f"Last error: {last_error}" if last_error else ""))
            return

        self.status.config(
            text="📷  Camera active — point the QR code at the lens",
            fg='#52b788')

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _show_no_camera(self, message):
        try:
            self.video_label.config(
                image='',
                text="📷\n\n" + message,
                font=('Segoe UI', 10),
                fg='#adb5bd',
                wraplength=520,
                justify='center')
        except Exception:
            pass
        try:
            self.status.config(text="Manual entry only — type the code below",
                               fg='#ffc107')
        except Exception:
            pass

    def _capture_loop(self):
        try:
            import cv2
        except Exception:
            return

        try:
            from pyzbar import pyzbar
            has_pyzbar = True
        except Exception as e:
            log.warning("pyzbar not available: %s", e)
            has_pyzbar = False

        cv2_qr = cv2.QRCodeDetector()

        while self._running and self._cap is not None:
            try:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    time.sleep(0.05)
                    continue
            except Exception:
                time.sleep(0.05)
                continue

            detected = None

            if has_pyzbar:
                try:
                    results = pyzbar.decode(frame)
                    for r in results:
                        try:
                            detected = r.data.decode('utf-8')
                            if detected:
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

            if not detected:
                try:
                    data, points, _ = cv2_qr.detectAndDecode(frame)
                    if data:
                        detected = data
                except Exception:
                    pass

            now = time.time()
            if detected and now > self._cooldown_until:
                self._last_scanned = detected
                self._cooldown_until = now + 1.5
                try:
                    self.after(0, lambda d=detected: self._on_detected(d))
                except Exception:
                    return

            try:
                h, w = frame.shape[:2]
                if w > 580:
                    scale = 580.0 / w
                    frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            except Exception:
                pass

            try:
                self.after(0, lambda f=frame: self._update_preview(f))
            except Exception:
                return
            time.sleep(0.03)

    def _update_preview(self, frame_rgb):
        if not self._running:
            return
        try:
            from PIL import Image, ImageTk
            img = Image.fromarray(frame_rgb)
            photo = ImageTk.PhotoImage(img)
            self.video_label.config(image=photo, text='')
            self.video_label.image = photo
        except Exception as e:
            log.debug("preview render: %s", e)

    def _on_detected(self, code):
        if not self._running:
            return
        try:
            self.status.config(text=f"✓  Scanned: {code}", fg='#198754')
        except Exception:
            pass
        self.result = code
        if self.on_scan:
            try:
                self.on_scan(code)
            except Exception as e:
                log.warning("on_scan callback: %s", e)
        try:
            self.after(400, self._on_close)
        except Exception:
            pass

    def _manual_submit(self):
        code = self.manual_var.get().strip()
        if not code:
            return
        self._on_detected(code)

    def _on_close(self):
        self._running = False
        try:
            if self._cap is not None:
                self._cap.release()
                self._cap = None
        except Exception:
            pass
        try:
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=0.5)
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
