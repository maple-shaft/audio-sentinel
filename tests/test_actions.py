"""
tests/test_actions.py

Unit tests for the action implementations.
ProcessKillerAction uses psutil mocks — no real processes are touched.
"""
import logging
from unittest.mock import MagicMock, patch

import pytest

from audio_sentinel.actions.logger import LogAction
from audio_sentinel.actions.process_killer import ProcessKillerAction
from audio_sentinel.actions.registry import build_action


# ---------------------------------------------------------------------------
# LogAction
# ---------------------------------------------------------------------------

class TestLogAction:
    def test_logs_formatted_message(self, caplog):
        action = LogAction({"level": "WARNING", "message": "detected {label} at {db:.1f}"})
        with caplog.at_level(logging.WARNING):
            action.execute({"label": "Child speech", "db": -18.3, "rule_name": "r", "confidence": 0.8})
        assert "Child speech" in caplog.text
        assert "-18.3" in caplog.text

    def test_defaults_to_warning(self, caplog):
        action = LogAction({"message": "test"})
        with caplog.at_level(logging.WARNING):
            action.execute({"rule_name": "r", "label": "x", "confidence": 0.5, "db": -20.0})
        assert "test" in caplog.text

    def test_bad_format_key_does_not_raise(self, caplog):
        action = LogAction({"level": "WARNING", "message": "hello {nonexistent_key}"})
        with caplog.at_level(logging.WARNING):
            # Should not raise — falls back to error message
            action.execute({"rule_name": "r", "label": "x", "confidence": 0.5, "db": -20.0})


# ---------------------------------------------------------------------------
# ProcessKillerAction
# ---------------------------------------------------------------------------

class TestProcessKillerAction:
    def _make_mock_proc(self, name: str, pid: int):
        proc = MagicMock()
        proc.info = {"name": name, "pid": pid}
        return proc

    def test_terminates_matching_process(self):
        mock_proc = self._make_mock_proc("target.exe", 1234)

        with patch("audio_sentinel.actions.process_killer.psutil.process_iter", return_value=[mock_proc]):
            action = ProcessKillerAction({"process_name": "target.exe", "graceful": True})
            action.execute({"rule_name": "r", "label": "x", "confidence": 0.5, "db": -20.0})

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_not_called()

    def test_kills_forcefully_when_graceful_false(self):
        mock_proc = self._make_mock_proc("target.exe", 1234)

        with patch("audio_sentinel.actions.process_killer.psutil.process_iter", return_value=[mock_proc]):
            action = ProcessKillerAction({"process_name": "target.exe", "graceful": False})
            action.execute({"rule_name": "r", "label": "x", "confidence": 0.5, "db": -20.0})

        mock_proc.kill.assert_called_once()
        mock_proc.terminate.assert_not_called()

    def test_does_not_kill_non_matching_process(self):
        mock_proc = self._make_mock_proc("other.exe", 9999)

        with patch("audio_sentinel.actions.process_killer.psutil.process_iter", return_value=[mock_proc]):
            action = ProcessKillerAction({"process_name": "target.exe", "graceful": True})
            action.execute({"rule_name": "r", "label": "x", "confidence": 0.5, "db": -20.0})

        mock_proc.terminate.assert_not_called()

    def test_missing_process_name_raises(self):
        with pytest.raises(ValueError, match="process_name"):
            ProcessKillerAction({"graceful": True})

    def test_match_is_case_insensitive(self):
        mock_proc = self._make_mock_proc("Target.EXE", 42)

        with patch("audio_sentinel.actions.process_killer.psutil.process_iter", return_value=[mock_proc]):
            action = ProcessKillerAction({"process_name": "target.exe", "graceful": True})
            action.execute({"rule_name": "r", "label": "x", "confidence": 0.5, "db": -20.0})

        mock_proc.terminate.assert_called_once()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_builds_log_action(self):
        action = build_action("log", {"level": "INFO", "message": "hi"})
        assert isinstance(action, LogAction)

    def test_builds_kill_action(self):
        action = build_action("kill_process", {"process_name": "foo.exe"})
        assert isinstance(action, ProcessKillerAction)

    def test_unknown_type_raises(self):
        with pytest.raises(KeyError, match="unknown_type"):
            build_action("unknown_type", {})
