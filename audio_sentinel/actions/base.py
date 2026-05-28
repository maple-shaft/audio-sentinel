"""
actions/base.py

Abstract interface that all actions must implement.
To add a new action type:
  1. Subclass BaseAction
  2. Implement execute()
  3. Register the type string in actions/registry.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseAction(ABC):
    """
    An action triggered by the rule engine.

    Args:
        params: Dict of action-specific parameters from config.yaml.
    """

    def __init__(self, params: Dict[str, Any]) -> None:
        self.params = params

    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> None:
        """
        Perform the action.

        Args:
            context: Runtime event data passed by the rule engine, e.g.:
                {
                    "rule_name": "child_voice_loud",
                    "label":     "Child speech, kid speaking",
                    "confidence": 0.82,
                    "db":        -18.3,
                }
        """
        ...