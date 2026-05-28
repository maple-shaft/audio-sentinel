"""
tests/test_config.py

Unit tests for utils/config.py — no I/O side effects beyond tmp files.
"""
import os
import textwrap

import pytest

from audio_sentinel.utils.config import (
    ActionConfig,
    DaemonConfig,
    RuleConfig,
    SentinelConfig,
    load_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_config(tmp_path, content: str) -> str:
    p = tmp_path / "config.yaml"
    p.write_text(textwrap.dedent(content))
    return str(p)


# ---------------------------------------------------------------------------
# DaemonConfig
# ---------------------------------------------------------------------------

class TestDaemonConfig:
    def test_defaults(self):
        cfg = DaemonConfig.from_dict({})
        assert cfg.sample_rate == 16000
        assert cfg.chunk_ms == 32
        assert cfg.vad_threshold == 0.5
        assert cfg.device is None

    def test_overrides(self):
        cfg = DaemonConfig.from_dict({"sample_rate": 8000, "vad_threshold": 0.8})
        assert cfg.sample_rate == 8000
        assert cfg.vad_threshold == 0.8


# ---------------------------------------------------------------------------
# RuleConfig
# ---------------------------------------------------------------------------

class TestRuleConfig:
    def test_parses_basic_rule(self):
        d = {
            "name": "test_rule",
            "description": "A test rule",
            "yamnet_classes": ["Child", "Scream"],
            "min_confidence": 0.7,
            "min_db": -25.0,
            "actions": [
                {"type": "log", "level": "WARNING", "message": "hi"}
            ],
        }
        rule = RuleConfig.from_dict(d)
        assert rule.name == "test_rule"
        assert rule.min_confidence == 0.7
        assert rule.min_db == -25.0
        assert len(rule.actions) == 1
        assert rule.actions[0].type == "log"

    def test_yamnet_classes_lowercased(self):
        rule = RuleConfig.from_dict({
            "name": "r",
            "yamnet_classes": ["CHILD", "Scream"],
            "actions": [],
        })
        assert rule.yamnet_classes == ["child", "scream"]

    def test_missing_actions_defaults_to_empty(self):
        rule = RuleConfig.from_dict({"name": "r", "yamnet_classes": []})
        assert rule.actions == []


# ---------------------------------------------------------------------------
# load_config (integration)
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_loads_valid_config(self, tmp_path):
        path = write_config(tmp_path, """
            daemon:
              sample_rate: 16000
              chunk_ms: 32
              vad_threshold: 0.5
              log_level: DEBUG
              log_file: logs/test.log
            rules:
              - name: child_test
                description: test
                yamnet_classes:
                  - child
                min_confidence: 0.6
                min_db: -20.0
                actions:
                  - type: log
                    level: WARNING
                    message: "detected {label}"
        """)
        cfg = load_config(path)
        assert isinstance(cfg, SentinelConfig)
        assert cfg.daemon.sample_rate == 16000
        assert len(cfg.rules) == 1
        assert cfg.rules[0].name == "child_test"

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent/path/config.yaml")

    def test_empty_rules_list(self, tmp_path):
        path = write_config(tmp_path, """
            daemon:
              sample_rate: 16000
            rules: []
        """)
        cfg = load_config(path)
        assert cfg.rules == []
