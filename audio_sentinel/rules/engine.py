"""
rules/engine.py

Evaluates a list of RuleConfig objects against a ClassificationResult
and fires any matching actions.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from audio_sentinel.actions.registry import build_action
from audio_sentinel.classification.classifier import ClassificationResult
from audio_sentinel.utils.config import RuleConfig

logger = logging.getLogger(__name__)


class RuleEngine:
    """
    Evaluates classification results against configured rules and
    dispatches actions for any matches.

    Args:
        rules: List of RuleConfig loaded from config.yaml.
    """

    def __init__(self, rules: List[RuleConfig]) -> None:
        self._rules = rules
        # Pre-build action instances so we don't reconstruct on every event
        self._rule_actions = {
            rule.name: [
                build_action(ac.type, dict(ac.params))
                for ac in rule.actions
            ]
            for rule in rules
        }
        logger.info("RuleEngine initialised with %d rule(s).", len(rules))

    def evaluate(self, result: ClassificationResult) -> None:
        """
        Test a single ClassificationResult against all rules.
        Fires actions for every rule that matches.
        """
        for rule in self._rules:
            if self._matches(rule, result):
                context = self._build_context(rule, result)
                logger.debug("Rule '%s' matched. Dispatching actions.", rule.name)
                for action in self._rule_actions[rule.name]:
                    try:
                        action.execute(context)
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "Action '%s' raised an exception for rule '%s': %s",
                            type(action).__name__,
                            rule.name,
                            exc,
                            exc_info=True,
                        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _matches(rule: RuleConfig, result: ClassificationResult) -> bool:
        # 1. Confidence gate
        if result.confidence < rule.min_confidence:
            return False

        # 2. dB gate
        if result.db < rule.min_db:
            return False

        # 3. Class label gate — substring match against any configured class
        label_lower = result.label.lower()
        for pattern in rule.yamnet_classes:
            if pattern == "" or pattern in label_lower:
                return True

        return False

    @staticmethod
    def _build_context(rule: RuleConfig, result: ClassificationResult) -> Dict[str, Any]:
        return {
            "rule_name": rule.name,
            "label": result.label,
            "confidence": result.confidence,
            "db": result.db,
        }