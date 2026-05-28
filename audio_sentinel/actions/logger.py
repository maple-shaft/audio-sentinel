"""
actions/logger.py

Writes a formatted log entry when a rule fires.
Config params:
    level:   Python log level name (DEBUG | INFO | WARNING | ERROR)
    message: Format string; supports {rule_name}, {label}, {confidence}, {db}
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from audio_sentinel.actions.base import BaseAction

logger = logging.getLogger(__name__)


class LogAction(BaseAction):
    def __init__(self, params: Dict[str, Any]) -> None:
        super().__init__(params)
        level_name = params.get("level", "WARNING").upper()
        self._level = getattr(logging, level_name, logging.WARNING)
        self._message_template = params.get("message", "Rule fired: {rule_name}")

    def execute(self, context: Dict[str, Any]) -> None:
        try:
            message = self._message_template.format(**context)
        except KeyError as exc:
            message = f"[LogAction format error: {exc}] raw context: {context}"

        logger.log(self._level, message)