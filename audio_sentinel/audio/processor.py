"""
audio/processor.py

Accumulates small VAD chunks into larger windows suitable for YAMNet,
and provides RMS → dBFS conversion utilities.
"""
from __future__ import annotations

import numpy as np


# Minimum float value to avoid log(0)
_EPS = 1e-9


def rms_to_dbfs(samples: np.ndarray) -> float:
    """
    Compute RMS energy of a float32 audio array and return dBFS.

    dBFS is relative to full-scale (1.0). Silence ≈ -96 dBFS.
    A loud signal close to clipping ≈ -3 dBFS.

    Args:
        samples: 1-D float32 array, values in [-1.0, 1.0]

    Returns:
        dBFS value (always <= 0.0 for normalised audio)
    """
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
    return 20.0 * np.log10(max(rms, _EPS))


class WindowAccumulator:
    """
    Collects small chunks (e.g. 32ms VAD frames) and emits larger
    windows (e.g. 975ms for YAMNet) as numpy arrays, along with the
    fraction of samples in that window that were flagged as speech.

    Every chunk is accumulated regardless of VAD status so YAMNet
    always sees a contiguous, properly-sized time window.  The caller
    uses the returned speech_fraction to decide whether to act on the
    classification result.

    Usage:
        acc = WindowAccumulator(window_samples=15600)
        for chunk, is_speech in stream:
            result = acc.push(chunk, is_speech)
            if result is not None:
                window, speech_fraction = result
                # classify window, then gate on speech_fraction
    """

    def __init__(self, window_samples: int) -> None:
        self.window_samples = window_samples
        self._buffer: list[np.ndarray] = []
        # Parallel list: (n_samples, is_speech) for each buffered chunk
        self._chunk_speech: list[tuple[int, bool]] = []
        self._buffered_samples: int = 0

    def push(self, chunk: np.ndarray, is_speech: bool = True) -> tuple[np.ndarray, float] | None:
        """
        Add a chunk to the accumulator.

        Args:
            chunk:     1-D float32 audio samples.
            is_speech: VAD label for this chunk.

        Returns:
            (window, speech_fraction) once enough samples have accumulated,
            where speech_fraction ∈ [0, 1] is the proportion of the window
            that was labelled as speech.  Returns None while still filling.
        """
        self._buffer.append(chunk)
        self._chunk_speech.append((len(chunk), is_speech))
        self._buffered_samples += len(chunk)

        if self._buffered_samples >= self.window_samples:
            flat = np.concatenate(self._buffer)
            window = flat[: self.window_samples].astype(np.float32)
            overflow = flat[self.window_samples :]

            # Tally speech samples that fall inside the emitted window,
            # and build the leftover speech-flag list for the next window.
            window_speech_samples = 0
            remaining = self.window_samples
            overflow_speech_flags: list[tuple[int, bool]] = []
            for n, flag in self._chunk_speech:
                if remaining <= 0:
                    overflow_speech_flags.append((n, flag))
                else:
                    take = min(n, remaining)
                    if flag:
                        window_speech_samples += take
                    remaining -= take
                    leftover = n - take
                    if leftover > 0:
                        overflow_speech_flags.append((leftover, flag))

            speech_fraction = window_speech_samples / self.window_samples

            self._buffer = [overflow] if len(overflow) > 0 else []
            self._chunk_speech = overflow_speech_flags
            self._buffered_samples = len(overflow)
            return window, speech_fraction

        return None

    def reset(self) -> None:
        self._buffer = []
        self._chunk_speech = []
        self._buffered_samples = 0