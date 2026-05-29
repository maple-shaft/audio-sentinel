"""
service_wrapper.py

Runs audio-sentinel as a Windows Service using only the Python standard
library (ctypes). No pywin32 or other third-party package required.

Register with: scripts/install-service.ps1
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import datetime
import os
import sys
import traceback

# pythonw.exe (used by SCM) has no console, so all three stdio handles are None.
# Any library that calls sys.stderr.write() (TensorFlow, absl-py, logging, etc.)
# will raise AttributeError before we can catch it.  Redirect to os.devnull
# before any non-stdlib import runs.
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r", encoding="utf-8")

# ---------------------------------------------------------------------------
# Windows service API — types, structures, and constants
# ---------------------------------------------------------------------------

_advapi32 = ctypes.windll.advapi32
_kernel32  = ctypes.windll.kernel32

SERVICE_WIN32_OWN_PROCESS = 0x0010
SERVICE_STOPPED           = 1
SERVICE_START_PENDING     = 2
SERVICE_STOP_PENDING      = 3
SERVICE_RUNNING           = 4
SERVICE_ACCEPT_STOP       = 0x0001
SERVICE_CONTROL_STOP      = 1
NO_ERROR                  = 0

# Callback types matching the Windows ABI
_HandlerFn     = ctypes.WINFUNCTYPE(None, ctypes.wintypes.DWORD)
_ServiceMainFn = ctypes.WINFUNCTYPE(
    None, ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.c_wchar_p)
)


class _SERVICE_STATUS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType",             ctypes.wintypes.DWORD),
        ("dwCurrentState",            ctypes.wintypes.DWORD),
        ("dwControlsAccepted",        ctypes.wintypes.DWORD),
        ("dwWin32ExitCode",           ctypes.wintypes.DWORD),
        ("dwServiceSpecificExitCode", ctypes.wintypes.DWORD),
        ("dwCheckPoint",              ctypes.wintypes.DWORD),
        ("dwWaitHint",                ctypes.wintypes.DWORD),
    ]


class _SERVICE_TABLE_ENTRY(ctypes.Structure):
    _fields_ = [
        ("lpServiceName", ctypes.c_wchar_p),
        ("lpServiceProc", _ServiceMainFn),
    ]


_advapi32.RegisterServiceCtrlHandlerW.restype  = ctypes.wintypes.HANDLE
_advapi32.RegisterServiceCtrlHandlerW.argtypes = [ctypes.c_wchar_p, _HandlerFn]
_advapi32.SetServiceStatus.restype             = ctypes.wintypes.BOOL
_advapi32.SetServiceStatus.argtypes            = [ctypes.wintypes.HANDLE,
                                                   ctypes.POINTER(_SERVICE_STATUS)]
_advapi32.StartServiceCtrlDispatcherW.restype  = ctypes.wintypes.BOOL
_advapi32.StartServiceCtrlDispatcherW.argtypes = [ctypes.POINTER(_SERVICE_TABLE_ENTRY)]

# ---------------------------------------------------------------------------
# Project root and venv site-packages — both must be on sys.path before any
# application imports.  When the SCM launches pythonw.exe directly (not via
# the activate script), Python's automatic venv detection is unreliable and
# .pth files inside site-packages (required by torch / tensorflow) are only
# processed when site.addsitedir() is called — a raw sys.path append is not
# enough.
# ---------------------------------------------------------------------------

import site as _site

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_VENV_SITE = os.path.join(_PROJECT_ROOT, ".venv", "Lib", "site-packages")
if os.path.isdir(_VENV_SITE):
    _site.addsitedir(_VENV_SITE)   # adds dir + processes all .pth files

# SentinelDaemon is NOT imported here.  torch + TensorFlow load transitively
# through it and can take 30-60 s on a cold start — long enough to exceed the
# SCM dispatcher timeout before StartServiceCtrlDispatcher is even called.
# The import is deferred to inside _svc_main, after the first checkpoint.

# ---------------------------------------------------------------------------
# Early debug log — written before the sentinel logger exists.
# Captures every step so a failure anywhere in startup is visible.
# Delete or set _DEBUG_LOG = None to silence it once the service is stable.
# ---------------------------------------------------------------------------

_DEBUG_LOG = os.path.join(_PROJECT_ROOT, "logs", "service_debug.log")


def _dbg(msg: str) -> None:
    """Append a timestamped line to the debug log, silently ignoring I/O errors."""
    try:
        os.makedirs(os.path.dirname(_DEBUG_LOG), exist_ok=True)
        with open(_DEBUG_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Service state (module-level keeps ctypes callbacks alive for the GC)
# ---------------------------------------------------------------------------

_SVC_NAME = "AudioSentinel"
_svc_handle: ctypes.wintypes.HANDLE | None = None
_daemon = None  # type: ignore[assignment]  # SentinelDaemon, imported lazily


def _report_status(state: int, wait_hint: int = 0, checkpoint: int = 0) -> None:
    status = _SERVICE_STATUS(
        dwServiceType             = SERVICE_WIN32_OWN_PROCESS,
        dwCurrentState            = state,
        dwControlsAccepted        = SERVICE_ACCEPT_STOP if state == SERVICE_RUNNING else 0,
        dwWin32ExitCode           = NO_ERROR,
        dwServiceSpecificExitCode = 0,
        dwCheckPoint              = checkpoint,
        dwWaitHint                = wait_hint,
    )
    _advapi32.SetServiceStatus(_svc_handle, ctypes.byref(status))


@_HandlerFn
def _ctrl_handler(control: int) -> None:
    """Called by the SCM on any service control code (stop, interrogate, etc.)."""
    _dbg(f"_ctrl_handler: control={control}")
    if control == SERVICE_CONTROL_STOP and _daemon is not None:
        _report_status(SERVICE_STOP_PENDING, wait_hint=5000)
        _daemon.stop()


@_ServiceMainFn
def _svc_main(argc: int, argv) -> None:
    """Service entry point called by StartServiceCtrlDispatcher."""
    global _svc_handle, _daemon

    _dbg("_svc_main: entered")

    try:
        _svc_handle = _advapi32.RegisterServiceCtrlHandlerW(_SVC_NAME, _ctrl_handler)
        _dbg(f"_svc_main: RegisterServiceCtrlHandlerW -> {_svc_handle}")
        if not _svc_handle:
            err = _kernel32.GetLastError()
            _dbg(f"_svc_main: RegisterServiceCtrlHandlerW failed, error={err}")
            return

        _report_status(SERVICE_START_PENDING, wait_hint=60_000, checkpoint=1)
        _dbg("_svc_main: checkpoint 1 reported — importing SentinelDaemon")

        # Lazy import: torch + TensorFlow load transitively here.
        from audio_sentinel.sentinel_daemon import SentinelDaemon  # noqa: E402
        _dbg("_svc_main: SentinelDaemon imported")

        _report_status(SERVICE_START_PENDING, wait_hint=60_000, checkpoint=2)
        _dbg("_svc_main: checkpoint 2 reported — initialising daemon")

        os.chdir(_PROJECT_ROOT)
        config_path = os.path.join(
            _PROJECT_ROOT, "audio_sentinel", "config", "config.yaml"
        )

        _daemon = SentinelDaemon(config_path=config_path)
        _dbg("_svc_main: SentinelDaemon initialised — reporting SERVICE_RUNNING")

        _report_status(SERVICE_RUNNING)
        _dbg("_svc_main: SERVICE_RUNNING reported — entering run loop")

        _daemon.run()
        _dbg("_svc_main: run() returned cleanly")

    except Exception:
        _dbg(f"_svc_main: UNHANDLED EXCEPTION\n{traceback.format_exc()}")
    finally:
        _dbg("_svc_main: reporting SERVICE_STOPPED")
        _report_status(SERVICE_STOPPED)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    _dbg(f"main: starting — PROJECT_ROOT={_PROJECT_ROOT}")
    _dbg(f"main: venv site-packages present={os.path.isdir(_VENV_SITE)}")
    _dbg(f"main: sys.path={sys.path}")

    table = (_SERVICE_TABLE_ENTRY * 2)()
    table[0].lpServiceName = _SVC_NAME
    table[0].lpServiceProc = _svc_main

    _dbg("main: calling StartServiceCtrlDispatcherW")
    if not _advapi32.StartServiceCtrlDispatcherW(table):
        err = _kernel32.GetLastError()
        _dbg(f"main: StartServiceCtrlDispatcherW failed, error={err}")
        sys.exit(
            f"StartServiceCtrlDispatcher failed (error {err}).\n"
            "This process must be started by the Windows SCM.\n"
            "Register it first with: scripts\\install-service.ps1"
        )

    _dbg("main: StartServiceCtrlDispatcherW returned (service stopped)")


if __name__ == "__main__":
    main()
