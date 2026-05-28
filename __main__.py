"""
audio_sentinel/__main__.py

Entry point for the audio-sentinel daemon.

Usage:
    python -m audio_sentinel
    python -m audio_sentinel --config path/to/config.yaml
    python -m audio_sentinel --list-devices
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time

import sounddevice as sd

from audio_sentinel.audio.capture import AudioCapture
from audio_sentinel.audio.processor import WindowAccumulator, rms_to_dbfs
from audio_sentinel.classification.classifier import YAMNetClassifier
from audio_sentinel.classification.vad import SileroVAD
from audio_sentinel.rules.engine import RuleEngine
from audio_sentinel.utils.config import load_config
from audio_sentinel.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="audio-sentinel",
        description="Monitors the microphone and triggers actions on sound events.",
    )
    parser.add_argument(
        "--config",
        default="audio_sentinel/config/config.yaml",
        metavar="PATH",
        help="Path to config.yaml (default: config/config.yaml)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Print available audio input devices and exit.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------

class SentinelDaemon:
    """
    Orchestrates the full pipeline:
        AudioCapture → WindowAccumulator → YAMNetClassifier → SileroVAD(gate) → RuleEngine

    Every captured chunk is pushed to the accumulator so YAMNet always sees a
    contiguous, properly-sized time window.  VAD labels are tracked per chunk;
    once a window is classified the result is only forwarded to the rule engine
    if the window's speech fraction meets the configured minimum.

    Runs on the calling thread; intended to be the main thread.
    Signal handlers (SIGINT / SIGTERM) trigger a graceful shutdown.
    """

    def __init__(self, config_path: str = "config/config.yaml") -> None:
        self._config = load_config(config_path)
        cfg = self._config.daemon

        setup_logging(cfg.log_level, cfg.log_file)
        logger.info("audio-sentinel starting up.")

        # Audio capture
        self._capture = AudioCapture(
            sample_rate=cfg.sample_rate,
            chunk_ms=cfg.chunk_ms,
            device=cfg.device,
        )

        # VAD
        self._vad = SileroVAD(
            threshold=cfg.vad_threshold,
            sample_rate=cfg.sample_rate,
        )

        # Window accumulator — receives every chunk; speech fraction is tracked
        # per-chunk so the caller can gate on it after classification.
        yamnet_window_samples = int(cfg.sample_rate * cfg.yamnet_window_ms / 1000)
        self._accumulator = WindowAccumulator(window_samples=yamnet_window_samples)

        # Classifier
        self._classifier = YAMNetClassifier(
            confidence_min=cfg.classifier_confidence_min,
        )

        # Rule engine
        self._rule_engine = RuleEngine(self._config.rules)

        # Shutdown flag
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the daemon loop. Blocks until stopped."""
        self._register_signal_handlers()
        self._capture.start()

        logger.info(
            "Daemon running. Listening on device: %s",
            self._config.daemon.device or "system default",
        )
        logger.info("Press Ctrl+C to stop.\n")

        try:
            self._loop()
        finally:
            self._shutdown()

    def stop(self) -> None:
        """Signal the daemon to stop gracefully."""
        logger.info("Stop requested.")
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        cfg = self._config.daemon

        while not self._stop_event.is_set():
            chunk = self._capture.read(timeout=0.5)
            if chunk is None:
                # Timeout — just loop back and check stop_event
                continue

            # --- VAD (label only; does not gate accumulation) ---------------
            is_speech, vad_confidence = self._vad.is_speech(chunk)
            logger.debug("VAD: is_speech=%s  confidence=%.3f", is_speech, vad_confidence)
            
            #TODO: Remove
            is_speech = True

            # --- Accumulate every chunk into a YAMNet-sized window ----------
            result = self._accumulator.push(chunk, is_speech)
            if result is None:
                # Not enough samples yet
                continue

            window, speech_fraction = result
            logger.debug("Window speech_fraction=%.2f", speech_fraction)

            # --- VAD gate: skip windows that are mostly silence -------------
            if speech_fraction < cfg.speech_fraction_min:
                logger.debug(
                    "Window skipped — speech_fraction %.2f < %.2f",
                    speech_fraction,
                    cfg.speech_fraction_min,
                )
                continue

            # --- dB estimate ------------------------------------------------
            db = rms_to_dbfs(window)
            logger.debug("Window dBFS: %.1f", db)

            # --- Classify ---------------------------------------------------
            results = self._classifier.classify(window, db)

            if not results:
                logger.debug("Classifier returned no results above threshold.")
                continue

            # --- Rule engine ------------------------------------------------
            for result in results:
                if result.confidence > 0.01:
                    logger.info(
                        "Detected: %-40s  conf=%.2f  dBFS=%.1f",
                        result.label,
                        result.confidence,
                        result.db,
                    )
                    self._rule_engine.evaluate(result)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _shutdown(self) -> None:
        logger.info("Shutting down …")
        self._capture.stop()
        logger.info("audio-sentinel stopped cleanly.")

    def _register_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum: int, frame) -> None:
        logger.info("Signal %d received — stopping.", signum)
        self._stop_event.set()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    if args.list_devices:
        print("\nAvailable audio input devices:\n")
        print(sd.query_devices())
        sys.exit(0)

    daemon = SentinelDaemon(config_path=args.config)
    daemon.run()


if __name__ == "__main__":
    main()