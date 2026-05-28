"""
actions/process_killer.py

Terminates a Windows process by name when a rule fires.

Config params:
    process_name:  e.g. "chrome.exe"
    graceful:      If true, attempt SIGTERM first; fall back to SIGKILL.
                   On Windows, psutil.terminate() sends SIGTERM equivalent.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import psutil

from audio_sentinel.actions.base import BaseAction

logger = logging.getLogger(__name__)


class ProcessKillerAction(BaseAction):
    def __init__(self, params: Dict[str, Any]) -> None:
        super().__init__(params)
        self._process_name: str = params.get("process_name", "")
        self._graceful: bool = bool(params.get("graceful", True))

        if not self._process_name:
            raise ValueError("ProcessKillerAction requires 'process_name' param.")

    def execute(self, context: Dict[str, Any]) -> None:
        if not self._process_name:
            return

        killed: list[str] = []
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                if proc.info["name"].lower() == self._process_name.lower():
                    pid = proc.info["pid"]
                    if self._graceful:
                        proc.terminate()
                        logger.info(
                            "Sent SIGTERM to '%s' (PID %d) [rule=%s]",
                            self._process_name,
                            pid,
                            context.get("rule_name"),
                        )
                    else:
                        proc.kill()
                        logger.info(
                            "Killed '%s' (PID %d) [rule=%s]",
                            self._process_name,
                            pid,
                            context.get("rule_name"),
                        )
                    killed.append(str(pid))
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                logger.warning("Could not kill '%s': %s", self._process_name, exc)

        if not killed:
            logger.debug(
                "ProcessKillerAction: no running process named '%s'",
                self._process_name,
            )