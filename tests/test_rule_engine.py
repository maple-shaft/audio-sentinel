"""
tests/test_rule_engine.py

Unit tests for rules/engine.py.
All action side effects are mocked — no real actions fire.
"""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch, call

from audio_sentinel.classification.classifier import ClassificationResult
from audio_sentinel.rules.engine import RuleEngine
from audio_sentinel.utils.config import ActionConfig, RuleConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_rule(
    name="test_rule",
    yamnet_classes=("child",),
    min_confidence=0.5,
    min_db=-30.0,
    actions=None,
) -> RuleConfig:
    if actions is None:
        actions = [ActionConfig(type="log", params={"level": "WARNING", "message": "fired"})]
    return RuleConfig(
        name=name,
        description="",
        yamnet_classes=list(yamnet_classes),
        min_confidence=min_confidence,
        min_db=min_db,
        actions=actions,
    )


def make_result(label="Child speech", confidence=0.8, db=-18.0) -> ClassificationResult:
    return ClassificationResult(
        label=label,
        confidence=confidence,
        db=db,
        all_scores=np.zeros(521, dtype=np.float32),
    )


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------

class TestRuleEngineMatching:
    def test_matching_result_fires_action(self):
        rule = make_rule(yamnet_classes=["child"], min_confidence=0.5, min_db=-30.0)
        engine = RuleEngine([rule])
        action = MagicMock()
        engine._rule_actions["test_rule"] = [action]

        engine.evaluate(make_result(label="Child speech", confidence=0.8, db=-18.0))
        action.execute.assert_called_once()

    def test_confidence_below_threshold_does_not_fire(self):
        rule = make_rule(min_confidence=0.9)
        engine = RuleEngine([rule])
        action = MagicMock()
        engine._rule_actions["test_rule"] = [action]

        engine.evaluate(make_result(confidence=0.5))
        action.execute.assert_not_called()

    def test_db_below_threshold_does_not_fire(self):
        rule = make_rule(min_db=-10.0)
        engine = RuleEngine([rule])
        action = MagicMock()
        engine._rule_actions["test_rule"] = [action]

        engine.evaluate(make_result(db=-30.0))
        action.execute.assert_not_called()

    def test_label_mismatch_does_not_fire(self):
        rule = make_rule(yamnet_classes=["dog"])
        engine = RuleEngine([rule])
        action = MagicMock()
        engine._rule_actions["test_rule"] = [action]

        engine.evaluate(make_result(label="Child speech"))
        action.execute.assert_not_called()

    def test_empty_pattern_matches_everything(self):
        rule = make_rule(yamnet_classes=[""])
        engine = RuleEngine([rule])
        action = MagicMock()
        engine._rule_actions["test_rule"] = [action]

        engine.evaluate(make_result(label="Dog barking"))
        action.execute.assert_called_once()

    def test_substring_match_is_case_insensitive(self):
        rule = make_rule(yamnet_classes=["child"])  # lowercase in config
        engine = RuleEngine([rule])
        action = MagicMock()
        engine._rule_actions["test_rule"] = [action]

        # YAMNet label has mixed case
        engine.evaluate(make_result(label="Child speech, kid speaking"))
        action.execute.assert_called_once()

    def test_multiple_rules_can_fire_independently(self):
        rule_a = make_rule(name="rule_a", yamnet_classes=["child"])
        rule_b = make_rule(name="rule_b", yamnet_classes=["speech"])
        engine = RuleEngine([rule_a, rule_b])

        action_a = MagicMock()
        action_b = MagicMock()
        engine._rule_actions["rule_a"] = [action_a]
        engine._rule_actions["rule_b"] = [action_b]

        engine.evaluate(make_result(label="Child speech"))
        action_a.execute.assert_called_once()
        action_b.execute.assert_called_once()

    def test_action_exception_does_not_crash_engine(self):
        rule = make_rule()
        engine = RuleEngine([rule])
        action = MagicMock()
        action.execute.side_effect = RuntimeError("boom")
        engine._rule_actions["test_rule"] = [action]

        # Should not raise
        engine.evaluate(make_result())

    def test_context_passed_to_action(self):
        rule = make_rule(yamnet_classes=["child"])
        engine = RuleEngine([rule])
        action = MagicMock()
        engine._rule_actions["test_rule"] = [action]

        result = make_result(label="Child speech", confidence=0.82, db=-19.5)
        engine.evaluate(result)

        ctx = action.execute.call_args[0][0]
        assert ctx["rule_name"] == "test_rule"
        assert ctx["label"] == "Child speech"
        assert pytest.approx(ctx["confidence"], abs=0.01) == 0.82
        assert pytest.approx(ctx["db"], abs=0.1) == -19.5
