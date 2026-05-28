"""
service_wrapper.py

Runs audio-sentinel as a Windows Service using only the Python standard
library (ctypes). No pywin32 or other third-party package required.

Register with: scripts/install-service.ps1
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import sys

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
# Project root — must be resolved before any relative imports or chdir calls
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from audio_sentinel.sentinel_daemon import SentinelDaemon  # noqa: E402

# ---------------------------------------------------------------------------
# Service state (module-level keeps ctypes callbacks alive for the GC)
# ---------------------------------------------------------------------------

_SVC_NAME = "AudioSentinel"
_svc_handle: ctypes.wintypes.HANDLE | None = None
_daemon: SentinelDaemon | None = None


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
    if control == SERVICE_CONTROL_STOP and _daemon is not None:
        _report_status(SERVICE_STOP_PENDING, wait_hint=5000)
        _daemon.stop()


@_ServiceMainFn
def _svc_main(argc: int, argv) -> None:
    """Service entry point called by StartServiceCtrlDispatcher."""
    global _svc_handle, _daemon

    _svc_handle = _advapi32.RegisterServiceCtrlHandlerW(_SVC_NAME, _ctrl_handler)
    if not _svc_handle:
        return

    _report_status(SERVICE_START_PENDING, wait_hint=10_000, checkpoint=1)

    os.chdir(_PROJECT_ROOT)
    config_path = os.path.join(_PROJECT_ROOT, "audio_sentinel", "config", "config.yaml")

    try:
        _daemon = SentinelDaemon(config_path=config_path)
        _report_status(SERVICE_RUNNING)
        _daemon.run()          # blocks until _daemon.stop() is called from _ctrl_handler
    finally:
        _report_status(SERVICE_STOPPED)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Build the dispatch table: one named entry + NULL sentinel
    table = (_SERVICE_TABLE_ENTRY * 2)()
    table[0].lpServiceName = _SVC_NAME
    table[0].lpServiceProc = _svc_main

    if not _advapi32.StartServiceCtrlDispatcherW(table):
        err = _kernel32.GetLastError()
        sys.exit(
            f"StartServiceCtrlDispatcher failed (error {err}).\n"
            "This process must be started by the Windows SCM.\n"
            "Register it first with: scripts\\install-service.ps1"
        )


if __name__ == "__main__":
    main()
