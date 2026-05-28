"""
audio/capture.py

Opens the default (or configured) microphone and pushes 32ms mono chunks
into a thread-safe queue for downstream consumers.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioCapture:
    """
    Streams audio from a microphone into a thread-safe queue.

    Each item placed on the queue is a 1-D float32 numpy array of
    exactly `chunk_samples` samples, normalised to [-1.0, 1.0].
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_ms: int = 32,
        device: Optional[int] = None,
        maxqueue: int = 128,
    ) -> None:
        self.sample_rate = sample_rate
        self.chunk_samples = int(sample_rate * chunk_ms / 1000)
        self.device = device
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=maxqueue)
        self._stream: Optional[sd.InputStream] = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the audio stream. Non-blocking — audio arrives via callback."""
        logger.info(
            "Opening audio stream: device=%s, rate=%d Hz, chunk=%d samples",
            self.device or "default",
            self.sample_rate,
            self.chunk_samples,
        )
        self._stop_event.clear()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.chunk_samples,
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()
        logger.info("Audio stream started.")

    def stop(self) -> None:
        """Stop the audio stream gracefully."""
        self._stop_event.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("Audio stream stopped.")

    def read(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """
        Block until a chunk is available and return it.
        Returns None on timeout (allows callers to check stop conditions).
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def is_running(self) -> bool:
        return self._stream is not None and self._stream.active

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time,  # CData from sounddevice — not typed
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.debug("sounddevice status: %s", status)

        chunk = indata[:, 0].copy()  # mono, shape (chunk_samples,)

        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            # Drop the oldest chunk to make room — prefer fresh audio
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(chunk)
            except queue.Empty:
                pass