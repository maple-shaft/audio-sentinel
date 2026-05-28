"""
service_wrapper.py

Runs audio-sentinel as a proper Windows Service via pywin32.
The SCM entry point — register it with scripts/install-service.ps1.

Requires: pip install pywin32
"""
from __future__ import annotations

import os
import sys

import servicemanager
import win32event
import win32service
import win32serviceutil

# Ensure the project root is on sys.path when running as a service
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from audio_sentinel.__main__ import SentinelDaemon  # noqa: E402


class AudioSentinelService(win32serviceutil.ServiceFramework):
    _svc_name_ = "AudioSentinel"
    _svc_display_name_ = "Audio Sentinel"
    _svc_description_ = (
        "Monitors microphone input and triggers configurable actions on detected sound events."
    )

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self._scm_stop = win32event.CreateEvent(None, 0, 0, None)
        self._daemon: SentinelDaemon | None = None
        self._config_path = os.path.join(
            _PROJECT_ROOT, "audio_sentinel", "config", "config.yaml"
        )

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self._daemon is not None:
            self._daemon.stop()
        win32event.SetEvent(self._scm_stop)

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        os.chdir(_PROJECT_ROOT)
        self._daemon = SentinelDaemon(config_path=self._config_path)
        self._daemon.run()  # blocks until daemon.stop() is called from SvcStop
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, ""),
        )


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Started by the SCM — connect the dispatcher and signal SERVICE_RUNNING
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(AudioSentinelService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Manual install/uninstall: python service_wrapper.py install|remove|start|stop
        win32serviceutil.HandleCommandLine(AudioSentinelService)
