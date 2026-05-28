"""
classification/classifier.py

YAMNet wrapper via TensorFlow Hub.

YAMNet:
  - Expects 16kHz mono float32 waveform, ~975ms (15,600 samples)
  - Returns scores for 521 AudioSet classes
  - Model downloaded once and cached by tf.hub (~13 MB)

Source separation seam
----------------------
If/when a Separator is injected, it runs *before* classification.
The interface contract:

    class BaseSeparator(ABC):
        def separate(self, waveform: np.ndarray) -> list[np.ndarray]:
            \"\"\"Return a list of separated source waveforms.\"\"\"

For now, the separator slot is None and we classify the raw mix.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

import numpy as np
import tensorflow as tf
import tensorflow_hub as hub

logger = logging.getLogger(__name__)

_YAMNET_URL = "https://tfhub.dev/google/yamnet/1"
_YAMNET_CLASS_MAP_URL = (
    "https://raw.githubusercontent.com/tensorflow/models/master/"
    "research/audioset/yamnet/yamnet_class_map.csv"
)

_YAMNET_CLASS_MAP_CACHE = "./yamnet_class_map.csv"

@dataclass(frozen=True)
class ClassificationResult:
    label: str
    confidence: float
    db: float          # dBFS of the window this came from
    all_scores: np.ndarray   # full 521-class score vector (for debugging)


class YAMNetClassifier:
    """
    Classifies a ~975ms audio window using YAMNet.

    Args:
        confidence_min:  Ignore predictions below this score.
        separator:       Optional source separator (future extension point).
    """

    def __init__(
        self,
        confidence_min: float = 0.20,
        separator=None,         # BaseSeparator | None
    ) -> None:
        self.confidence_min = confidence_min
        self._separator = separator   # seam for future source separation

        logger.info("Loading YAMNet from TensorFlow Hub …")
        self._model = hub.load(_YAMNET_URL)
        self._class_names = self._load_class_names()
        logger.info("YAMNet loaded. %d classes available.", len(self._class_names))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, waveform: np.ndarray, db: float) -> List[ClassificationResult]:
        """
        Classify a waveform window.

        Args:
            waveform:  1-D float32 numpy array, ideally ~15600 samples.
            db:        Pre-computed dBFS for this window (passed through
                       to results so callers don't recompute).

        Returns:
            List of ClassificationResult sorted by confidence descending,
            filtered to >= confidence_min.  May be empty.
        """
        sources = self._separate(waveform)
        results: List[ClassificationResult] = []

        for source in sources:
            results.extend(self._classify_one(source, db))

        # Sort by confidence, best first
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _separate(self, waveform: np.ndarray) -> List[np.ndarray]:
        """Run source separator if available, otherwise pass through."""
        if self._separator is not None:
            return self._separator.separate(waveform)
        return [waveform]

    def _classify_one(self, waveform: np.ndarray, db: float) -> List[ClassificationResult]:
        tensor = tf.constant(waveform, dtype=tf.float32)
        scores, embeddings, spectrogram = self._model(tensor)

        # scores shape: (num_frames, 521) — average across frames
        mean_scores: np.ndarray = tf.reduce_mean(scores, axis=0).numpy()

        results = []
        for idx, score in enumerate(mean_scores):
            if score >= 0: # self.confidence_min:
                results.append(
                    ClassificationResult(
                        label=self._class_names[idx],
                        confidence=float(score),
                        db=db,
                        all_scores=mean_scores,
                    )
                )
        return results

    @staticmethod
    def _load_class_names() -> List[str]:
        """
        Load YAMNet class names.  TF Hub caches the model but not the CSV,
        so we fetch it once; it's tiny (< 20 KB).
        """
        import csv
        import urllib.request
        import io
        import os

        logger.debug("Fetching YAMNet class map …")

        try:
            with Path(_YAMNET_CLASS_MAP_CACHE) as class_map_path:
                content: str
                if not class_map_path.exists():
                    with urllib.request.urlopen(_YAMNET_CLASS_MAP_URL) as resp, class_map_path.open("w") as cf:
                        content = resp.read().decode("utf-8")
                        num = cf.write(content)
                        logger.info(f"Cached {_YAMNET_CLASS_MAP_CACHE}, number of bytes written: {num}")
                else:
                    with class_map_path.open("r") as cf:
                        content = cf.read()
                        logger.info(f"Cached {_YAMNET_CLASS_MAP_CACHE} read in...")

                reader = csv.DictReader(io.StringIO(content))
                # CSV columns: index, mid, display_name
                names = [row["display_name"] for row in reader]
                return names
        except Exception as e:
            logger.error(e)