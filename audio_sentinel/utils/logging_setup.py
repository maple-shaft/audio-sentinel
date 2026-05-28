"""
utils/logging_setup.py
Configures colorlog for console and a plain rotating file handler.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

import colorlog


def setup_logging(log_level: str = "INFO", log_file: str = "logs/sentinel.log") -> None:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)

    # Console handler — coloured
    console = colorlog.StreamHandler()
    console.setLevel(level)
    console.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )
    )

    # File handler — plain, rotating at 5 MB, keep 3 backups
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console)
    root.addHandler(file_handler)
