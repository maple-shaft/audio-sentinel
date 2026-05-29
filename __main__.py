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
from audio_sentinel.sentinel_daemon import SentinelDaemon

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