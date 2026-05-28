"""
tests/test_processor.py

Unit tests for audio/processor.py — no audio hardware required.
"""
import numpy as np
import pytest

from audio_sentinel.audio.processor import WindowAccumulator, rms_to_dbfs


# ---------------------------------------------------------------------------
# rms_to_dbfs
# ---------------------------------------------------------------------------

class TestRmsToDbfs:
    def test_silence_is_very_negative(self):
        silence = np.zeros(512, dtype=np.float32)
        db = rms_to_dbfs(silence)
        assert db < -90.0

    def test_full_scale_sine_is_near_zero(self):
        # A full-scale sine wave has RMS = 1/sqrt(2) ≈ 0.707 → ~ -3 dBFS
        t = np.linspace(0, 1, 16000, dtype=np.float32)
        sine = np.sin(2 * np.pi * 440 * t)
        db = rms_to_dbfs(sine)
        assert -4.0 < db < -2.0

    def test_half_amplitude_is_6db_quieter(self):
        t = np.linspace(0, 1, 16000, dtype=np.float32)
        full = np.sin(2 * np.pi * 440 * t)
        half = full * 0.5
        db_full = rms_to_dbfs(full)
        db_half = rms_to_dbfs(half)
        assert abs((db_full - db_half) - 6.0) < 0.1

    def test_returns_float(self):
        chunk = np.random.uniform(-0.5, 0.5, 512).astype(np.float32)
        result = rms_to_dbfs(chunk)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# WindowAccumulator
# ---------------------------------------------------------------------------

class TestWindowAccumulator:
    def test_returns_none_until_full(self):
        acc = WindowAccumulator(window_samples=1024)
        chunk = np.zeros(256, dtype=np.float32)
        assert acc.push(chunk) is None
        assert acc.push(chunk) is None
        assert acc.push(chunk) is None

    def test_emits_window_when_full(self):
        acc = WindowAccumulator(window_samples=1024)
        chunk = np.ones(256, dtype=np.float32)
        result = None
        for _ in range(4):
            result = acc.push(chunk)
        assert result is not None
        assert len(result) == 1024

    def test_window_has_correct_dtype(self):
        acc = WindowAccumulator(window_samples=512)
        chunk = np.ones(512, dtype=np.float32)
        result = acc.push(chunk)
        assert result is not None
        assert result.dtype == np.float32

    def test_overflow_carried_to_next_window(self):
        # Push 600 samples into a 512-sample window
        acc = WindowAccumulator(window_samples=512)
        chunk = np.arange(600, dtype=np.float32)
        window = acc.push(chunk)
        assert window is not None
        assert len(window) == 512
        # 88 samples should remain buffered
        assert acc._buffered_samples == 88

    def test_reset_clears_buffer(self):
        acc = WindowAccumulator(window_samples=1024)
        acc.push(np.zeros(256, dtype=np.float32))
        assert acc._buffered_samples == 256
        acc.reset()
        assert acc._buffered_samples == 0

    def test_window_values_are_correct(self):
        acc = WindowAccumulator(window_samples=4)
        result = acc.push(np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32))
        assert result is not None
        np.testing.assert_array_equal(result, [1.0, 2.0, 3.0, 4.0])
