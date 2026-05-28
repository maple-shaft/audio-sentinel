"""
classification/vad.py

Thin wrapper around Silero VAD (PyTorch hub).

Silero VAD expects:
  - 16 kHz mono float32 tensor
  - chunk size of exactly 512 samples (32ms) at 16kHz

The model is downloaded once and cached by torch.hub (~1 MB).
"""
from __future__ import annotations

import logging
from typing import Tuple

import numpy as np
import torch

logger = logging.getLogger(__name__)

_SILERO_REPO = "snakers4/silero-vad"
_SILERO_MODEL = "silero_vad"


class SileroVAD:
    """
    Wraps Silero VAD for per-chunk voice activity detection.

    Args:
        threshold:    Confidence threshold above which speech is detected.
        sample_rate:  Must be 16000.
    """

    # Silero VAD only supports these chunk sizes at 16kHz
    SUPPORTED_CHUNK_SAMPLES = (256, 512, 768, 1024)

    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000) -> None:
        if sample_rate != 16000:
            raise ValueError("SileroVAD only supports 16000 Hz sample rate.")

        self.threshold = threshold
        self.sample_rate = sample_rate

        logger.info("Loading Silero VAD model from torch.hub …")
        self._model, _ = torch.hub.load(
            repo_or_dir=_SILERO_REPO,
            model=_SILERO_MODEL,
            force_reload=False,
            trust_repo=True,
            verbose=False,
        )
        self._model.eval()
        logger.info("Silero VAD loaded.")

    def is_speech(self, chunk: np.ndarray) -> Tuple[bool, float]:
        """
        Predict whether a chunk of audio contains speech.

        Args:
            chunk: 1-D float32 numpy array.  Length should ideally be one
                   of SUPPORTED_CHUNK_SAMPLES; it will be zero-padded or
                   truncated to the nearest supported size automatically.

        Returns:
            (is_speech, confidence) tuple.
        """
        chunk = self._normalise_length(chunk)
        tensor = torch.from_numpy(chunk).unsqueeze(0)  # (1, samples)

        with torch.no_grad():
            confidence: float = self._model(tensor, self.sample_rate).item()

        return confidence >= self.threshold, confidence

    def reset_state(self) -> None:
        """Reset internal RNN state — call between unrelated audio segments."""
        self._model.reset_states()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalise_length(self, chunk: np.ndarray) -> np.ndarray:
        target = self._nearest_supported(len(chunk))
        if len(chunk) == target:
            return chunk
        if len(chunk) < target:
            return np.pad(chunk, (0, target - len(chunk)))
        return chunk[:target]

    @staticmethod
    def _nearest_supported(n: int) -> int:
        supported = SileroVAD.SUPPORTED_CHUNK_SAMPLES
        return min(supported, key=lambda s: abs(s - n))