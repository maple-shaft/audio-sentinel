"""
actions/registry.py

Maps action type strings (from config.yaml) to action classes.
Register new action types here.
"""
from __future__ import annotations

from typing import Any, Dict, Type

from audio_sentinel.actions.base import BaseAction
from audio_sentinel.actions.logger import LogAction
from audio_sentinel.actions.process_killer import ProcessKillerAction

_REGISTRY: Dict[str, Type[BaseAction]] = {
    "log": LogAction,
    "kill_process": ProcessKillerAction,
}


def build_action(action_type: str, params: Dict[str, Any]) -> BaseAction:
    """
    Instantiate an action by type string.

    Raises:
        KeyError: if action_type is not registered.
    """
    cls = _REGISTRY.get(action_type)
    if cls is None:
        raise KeyError(
            f"Unknown action type '{action_type}'. "
            f"Available: {list(_REGISTRY.keys())}"
        )
    return cls(params)