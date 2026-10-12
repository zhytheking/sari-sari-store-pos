import os
import sys
from pathlib import Path


def _project_root() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]

#Absolute path to the PID file. Parent dir is created if needed
def pid_file_path() -> Path:   
    p = _project_root() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p / "server.pid"

#Write the current process's PID to the file
def write_pid(pid: int) -> None:
    pid_file_path().write_text(str(pid), encoding='utf-8')


def read_pid():
    p = pid_file_path()
    if not p.exists():
        return None
    try:
        return int(p.read_text(encoding='utf-8').strip())
    except (ValueError, OSError):
        return None


def clear_pid() -> None:
    try:
        pid_file_path().unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
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
    except (OSError, ProcessLookupError):
        return False
    except Exception:
        return False


def kill_process(pid: int) -> bool:
    if not is_process_alive(pid):
        return True
    try:
        if os.name == 'nt':
            import subprocess
            subprocess.run(
                ['taskkill', '/PID', str(pid), '/F'],
                capture_output=True,
                check=False,
            )
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False
