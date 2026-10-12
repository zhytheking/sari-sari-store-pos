"""
run.py — Unified entry point for Saliga Sari-Sari Store POS.

Modes:
    --app       Server (detached) + GUI (foreground)
    --serve     Web server only (foreground)
    --gui       GUI only (assumes server is running)
    --stop      Stop the running server
    --status    Show server status
    --init-db   Initialize the database
    --backup    Manual DB backup
    --check-routes  Print all registered routes
    --web       Dev web server (Flask debug)

Server lifecycle:
    --app spawns the server as a DETACHED subprocess. The server
    survives after the GUI closes. Use --stop to kill it.
"""
import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# ════════════════════════════════════════════════════════════
# STARTUP DIAGNOSTICS
# ════════════════════════════════════════════════════════════
print("=" * 60)
print("  SALIGA SARI-SARI STORE POS — STARTUP")
print("=" * 60)
print(f"  Frozen:          {getattr(sys, 'frozen', False)}")
print(f"  sys.executable:  {sys.executable}")
print(f"  sys._MEIPASS:    {getattr(sys, '_MEIPASS', '(not set)')}")
print(f"  cwd:             {os.getcwd()}")
print(f"  argv:            {sys.argv}")
print("=" * 60)
sys.stdout.flush()


# ════════════════════════════════════════════════════════════
# PATH SETUP
# ════════════════════════════════════════════════════════════

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(sys.executable).resolve().parent
    project_root = BUNDLE_DIR
else:
    APP_DIR = Path(__file__).resolve().parent
    project_root = APP_DIR

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def _data_root() -> Path:
    """
    Where runtime files (data/, logs/) live. Matches config.py.
    """
    if getattr(sys, 'frozen', False):
        local = os.getenv("LOCALAPPDATA")
        if local:
            return Path(local) / "SariSariPOS"
        return Path.home() / "AppData" / "Local" / "SariSariPOS"
    return APP_DIR / "data"


DATA_ROOT = _data_root()
DATA_ROOT.mkdir(parents=True, exist_ok=True)
(DATA_ROOT / "logs").mkdir(exist_ok=True)
(DATA_ROOT / "backups").mkdir(exist_ok=True)
PID_FILE = DATA_ROOT / "server.pid"


# ══════════════════
# PID FILE HELPERS
# ══════════════════


def _write_pid(pid: int):
    try:
        PID_FILE.write_text(str(pid), encoding='utf-8')
    except Exception as e:
        print(f"[pid] Could not write PID file: {e}")


def _read_pid():
    try:
        if PID_FILE.exists():
            return int(PID_FILE.read_text(encoding='utf-8').strip())
    except Exception:
        pass
    return None


def _clear_pid():
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass


def _is_process_alive(pid: int) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            exit_code = wintypes.DWORD()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            kernel32.CloseHandle(handle)
            STILL_ACTIVE = 259
            return exit_code.value == STILL_ACTIVE
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def _kill_process(pid: int) -> bool:
    if not _is_process_alive(pid):
        return True
    try:
        if os.name == 'nt':
            subprocess.run(
                ['taskkill', '/PID', str(pid), '/F', '/T'],
                capture_output=True, check=False,
            )
        else:
            import signal as _sig
            os.kill(pid, _sig.SIGTERM)
        return True
    except Exception:
        return False


# ═════════════════
# SOCKET HELPERS
# ═════════════════
def _get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _port_is_open(host: str, port: int, timeout: float = 0.5) -> bool:
    probe = "127.0.0.1" if host in ("0.0.0.0", "") else host
    try:
        with socket.create_connection((probe, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError):
        return False


def _wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
    probe = "127.0.0.1" if host in ("0.0.0.0", "") else host
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((probe, port), timeout=0.5):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.2)
    return False


def _print_banner(mode, host, port, env, debug):
    url_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    lan_ip = _get_lan_ip() if host == "0.0.0.0" else None

    print("=" * 60)
    print(f"  SARI-SARI STORE POS - {mode}")
    print("=" * 60)
    print(f"  Local:        http://{url_host}:{port}")
    if lan_ip:
        print(f"  Network:      http://{lan_ip}:{port}")
    print(f"  Environment:  {env}")
    print(f"  Debug:        {debug}")
    print("=" * 60)
    sys.stdout.flush()


# ════════════════
# IMPORT HELPER
# ════════════════

def _import_app():
    """Return (app, config)."""
    try:
        from backend.app import app
        from backend.config import config
        return app, config
    except ModuleNotFoundError as e:
        print("=" * 60)
        print("  FATAL: Cannot import backend.app")
        print("=" * 60)
        print(f"  Error: {e}")
        print(f"  project_root: {project_root}")
        backend_path = project_root / "backend"
        print(f"  Checking {backend_path}: "
              f"{'exists' if backend_path.exists() else 'MISSING'}")
        print("=" * 60)
        sys.stdout.flush()
        raise


# ═══════════════════════════════════════
# SERVER (foreground — used by --serve)
# ═══════════════════════════════════════
def run_server():
    """Production web server in the FOREGROUND."""
    try:
        app, config = _import_app()
    except Exception as e:
        print(f"[ERROR] Cannot load app: {e}")
        import traceback
        traceback.print_exc()
        return 1

    try:
        from waitress import serve
    except ImportError:
        print("[ERROR] waitress not installed.")
        return 1

    # Write our PID so --stop and --status can find us
    _write_pid(os.getpid())

    _print_banner("PRODUCTION (Waitress)", config.HOST, config.PORT,
                  config.APP_ENV, False)
    print("  Press Ctrl+C to stop")
    print("=" * 60)
    sys.stdout.flush()

    try:
        serve(
            app,
            host=config.HOST,
            port=config.PORT,
            threads=8,
            connection_limit=200,
            cleanup_interval=30,
            channel_timeout=120,
            ident="Sari-Sari-POS",
        )
    except KeyboardInterrupt:
        print("\n[server] Stopped by user.")
    except Exception as e:
        print(f"[server] Crashed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        _clear_pid()

    return 0


def run_web():
    """Development server (Flask debug)."""
    try:
        app, config = _import_app()
        _print_banner("DEV SERVER", config.HOST, config.PORT,
                      config.APP_ENV, config.DEBUG)
        app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
    except KeyboardInterrupt:
        print("\nServer stopped.")
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1
    return 0


# ══════════════════
# GUI (foreground)
# ══════════════════
def run_gui():
    """Desktop GUI only."""
    try:
        from frontend.gui.main import main as gui_main
        print("=" * 60)
        print("  SARI-SARI STORE POS SYSTEM - GUI MODE")
        print("=" * 60)
        sys.stdout.flush()
        gui_main()
    except ImportError as e:
        print(f"[ERROR] Cannot import GUI: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"[ERROR] GUI crashed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    return 0


# ══════════════════════
# DETACHED SERVER SPAWN
# ══════════════════════

def _spawn_detached_server():
    """
    Spawn the server as a DETACHED subprocess that survives
    after this process exits.

    In frozen mode:  sys.executable is SariSariPOS.exe
                     We re-invoke it with --serve.
    In source mode:  sys.executable is python.exe
                     We re-invoke `python run.py --serve`.
    """
    if getattr(sys, 'frozen', False):
        # Frozen: relaunch the exe with --serve
        cmd = [sys.executable, '--serve']
    else:
        # Source: relaunch `python run.py --serve`
        script = str(Path(__file__).resolve())
        cmd = [sys.executable, script, '--serve']

    log_dir = DATA_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = log_dir / "server_stdout.log"
    stderr_log = log_dir / "server_stderr.log"

    if os.name == 'nt':
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NO_WINDOW = 0x08000000
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        creationflags = (
            DETACHED_PROCESS
            | CREATE_NEW_PROCESS_GROUP
            | CREATE_NO_WINDOW
            | CREATE_BREAKAWAY_FROM_JOB
        )
    else:
        creationflags = 0

    try:
        out_f = open(str(stdout_log), 'ab')
        err_f = open(str(stderr_log), 'ab')
    except Exception:
        out_f = subprocess.DEVNULL
        err_f = subprocess.DEVNULL

    try:
        kwargs = {
            'stdin': subprocess.DEVNULL,
            'stdout': out_f,
            'stderr': err_f,
            'close_fds': True,
            'cwd': str(APP_DIR),
        }
        if os.name == 'nt':
            kwargs['creationflags'] = creationflags
        else:
            kwargs['preexec_fn'] = os.setsid

        proc = subprocess.Popen(cmd, **kwargs)
        return proc
    except Exception as e:
        print(f"[app] Failed to spawn server: {e}")
        return None
    finally:
        try:
            if out_f not in (subprocess.DEVNULL, None):
                out_f.close()
            if err_f not in (subprocess.DEVNULL, None):
                err_f.close()
        except Exception:
            pass


# ═════════════════════
# UNIFIED MODE (--app)
# ═════════════════════

def run_app():
    try:
        _, config = _import_app()
    except Exception as e:
        print(f"[ERROR] Cannot load config: {e}")
        return 1

    host = config.HOST
    port = config.PORT
    url_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    lan_ip = _get_lan_ip() if host == "0.0.0.0" else None

    print("=" * 60)
    print("  SARI-SARI STORE POS SYSTEM - UNIFIED APP")
    print("=" * 60)
    print(f"  Environment:  {config.APP_ENV}")
    print("=" * 60)
    sys.stdout.flush()

    # ── 1. Check if a server is already running ──
    if _port_is_open(host, port):
        print(f"  Server already running on port {port}.")
        server_was_already_running = True
    else:
        # ── 2. Clean up any stale PID file ──
        existing_pid = _read_pid()
        if existing_pid is not None and not _is_process_alive(existing_pid):
            print(f"  Cleaning stale PID {existing_pid}.")
            _clear_pid()

        # ── 3. Spawn the detached server ──
        print("  Starting server (detached)...")
        proc = _spawn_detached_server()
        if proc is None:
            print("  [ERROR] Could not spawn server.")
            return 1
        print(f"  Server process spawned (PID {proc.pid}).")
        print("  The server will keep running after you close the GUI.")
        print()
        print("  Waiting for server to be ready (up to 30s)...")

        if not _wait_for_server(host, port, timeout=30.0):
            print()
            print("  [ERROR] Server did not start within 30 seconds.")
            print(f"  Check: {DATA_ROOT / 'logs' / 'server_stderr.log'}")
            return 1

        print("  Server ready.")
        server_was_already_running = False

    # ── 4. Show banner ──
    print("=" * 60)
    print(f"  Web app:      http://{url_host}:{port}")
    if lan_ip:
        print(f"  LAN access:   http://{lan_ip}:{port}")
    print("=" * 60)
    print("  Launching desktop app...")
    print("  (The web app will keep running after you close the GUI.)")
    print("  To stop the server:  run.py --stop")
    print("=" * 60)
    sys.stdout.flush()

    # ── 5. Run the GUI in this process ──
    try:
        from frontend.gui.main import main as gui_main
        gui_main()
    except Exception as e:
        print(f"[ERROR] GUI crashed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # ── 6. GUI closed. Report state ──
    print()
    print("=" * 60)
    print("  Desktop app closed.")
    if server_was_already_running:
        print("  Server was already running (untouched).")
    else:
        print("  Server is still running in the background.")
    print(f"  Web app:  http://{url_host}:{port}")
    print(f"  To stop:  run.py --stop")
    print("=" * 60)
    sys.stdout.flush()

    return 0


# ══════════════
# STOP / STATUS
# ══════════════

def run_stop():
    print("=" * 60)
    print("  STOPPING SERVER")
    print("=" * 60)

    pid = _read_pid()

    if pid is not None and _is_process_alive(pid):
        print(f"  Found PID: {pid}")
        print("  Terminating...")
        _kill_process(pid)

        deadline = time.time() + 5
        while time.time() < deadline:
            if not _is_process_alive(pid):
                break
            time.sleep(0.2)

        if _is_process_alive(pid):
            print(f"  [WARN] PID {pid} still alive.")
            return 1

        _clear_pid()
        print("  Server stopped.")
        print("=" * 60)
        return 0

    if pid is not None:
        print(f"  Stale PID {pid} (process not alive).")
        _clear_pid()

    # Fallback: kill by process name (Windows)
    if os.name == 'nt':
        try:
            result = subprocess.run(
                ['taskkill', '/IM', 'SariSariPOS.exe', '/F', '/T'],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                print("  Killed SariSariPOS.exe process(es).")
                print("=" * 60)
                return 0
        except Exception:
            pass

    print("  No running server found.")
    print("=" * 60)
    return 1


def run_status():
    print("=" * 60)
    print("  SERVER STATUS")
    print("=" * 60)

    pid = _read_pid()
    if pid is not None:
        alive = _is_process_alive(pid)
        print(f"  PID file:    {PID_FILE}")
        print(f"  PID:         {pid}")
        print(f"  Alive:       {'yes' if alive else 'NO (stale)'}")
    else:
        print(f"  PID file:    (not found)")
        print(f"  PID:         —")

    # Probe the port
    from backend.config import config
    host = config.HOST
    port = config.PORT
    open_ = _port_is_open(host, port)
    url_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    print(f"  Port {port}:     {'OPEN' if open_ else 'CLOSED'}")
    if open_:
        print(f"  URL:         http://{url_host}:{port}")
    print("=" * 60)
    return 0


# ══════════════
# UTILITY MODES
# ══════════════

def init_database():
    try:
        from backend.app import create_app
        from backend.config import config
        print("=" * 60)
        print("  INITIALIZING DATABASE")
        print("=" * 60)
        app = create_app()
        with app.app_context():
            from backend.database.connection import init_db
            init_db()
        print(f"  DB path: {config.DB_PATH}")
        print("  Owner:   admin / admin123")
        print("  Cashier: cashier / cashier123")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1


def run_backup():
    script = APP_DIR / "scripts" / "backup_db.py"
    if not script.exists():
        script = project_root / "scripts" / "backup_db.py"
    if not script.exists():
        print(f"[ERROR] backup_db.py not found")
        return 1
    return subprocess.run([sys.executable, str(script)]).returncode


def check_routes():
    try:
        app, _ = _import_app()
    except Exception as e:
        print(f"[ERROR] Failed to load app: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("=" * 80)
    print("  REGISTERED ROUTES")
    print("=" * 80)
    routes = sorted(app.url_map.iter_rules(), key=lambda r: str(r))
    for rule in routes:
        methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        print(f"  {methods:<12} {str(rule):<50} -> {rule.endpoint}")
    print("=" * 80)
    print(f"  Total: {len(routes)} routes")
    print("=" * 80)
    return 0


# ═════
# CLI
# ═════

def main():
    parser = argparse.ArgumentParser(description="Sari-Sari Store POS")
    parser.add_argument("--app", action="store_true",
                        help="Server (detached) + GUI")
    parser.add_argument("--serve", action="store_true",
                        help="Web server only (foreground)")
    parser.add_argument("--gui", action="store_true",
                        help="GUI only")
    parser.add_argument("--stop", action="store_true",
                        help="Stop the running server")
    parser.add_argument("--status", action="store_true",
                        help="Show server status")
    parser.add_argument("--init-db", action="store_true",
                        help="Initialize the database")
    parser.add_argument("--backup", action="store_true",
                        help="Manual DB backup")
    parser.add_argument("--check-routes", action="store_true",
                        help="Print all registered routes")
    parser.add_argument("--web", action="store_true",
                        help="Dev web server (Flask debug)")
    parser.add_argument("--host", type=str)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()

    if args.host:
        os.environ["HOST"] = args.host
    if args.port:
        os.environ["PORT"] = str(args.port)

    if args.init_db:
        sys.exit(init_database())
    if args.backup:
        sys.exit(run_backup())
    if args.check_routes:
        sys.exit(check_routes())
    if args.stop:
        sys.exit(run_stop())
    if args.status:
        sys.exit(run_status())

    if args.app:
        sys.exit(run_app())
    if args.serve:
        sys.exit(run_server())
    if args.gui:
        sys.exit(run_gui())
    if args.web:
        sys.exit(run_web())

    # No mode specified → run the dev server for convenience
    sys.exit(run_web())


if __name__ == "__main__":
    main()
