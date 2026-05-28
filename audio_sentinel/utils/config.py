"""
utils/config.py
Loads and validates config/config.yaml into typed dataclasses.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Action config
# ---------------------------------------------------------------------------

@dataclass
class ActionConfig:
    type: str                        # "log" | "kill_process"
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionConfig":
        action_type = d.pop("type")
        return cls(type=action_type, params=d)


# ---------------------------------------------------------------------------
# Rule config
# ---------------------------------------------------------------------------

@dataclass
class RuleConfig:
    name: str
    description: str
    yamnet_classes: List[str]
    min_confidence: float
    min_db: float
    actions: List[ActionConfig]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RuleConfig":
        actions = [ActionConfig.from_dict(dict(a)) for a in d.get("actions", [])]
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            yamnet_classes=[c.lower() for c in d.get("yamnet_classes", [])],
            min_confidence=float(d.get("min_confidence", 0.5)),
            min_db=float(d.get("min_db", -20.0)),
            actions=actions,
        )


# ---------------------------------------------------------------------------
# Daemon config
# ---------------------------------------------------------------------------

@dataclass
class DaemonConfig:
    sample_rate: int = 16000
    chunk_ms: int = 32
    yamnet_window_ms: int = 975
    device: Optional[int] = None
    vad_threshold: float = 0.5
    speech_fraction_min: float = 0.3
    classifier_confidence_min: float = 0.20
    log_level: str = "INFO"
    log_file: str = "logs/sentinel.log"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DaemonConfig":
        return cls(
            sample_rate=int(d.get("sample_rate", 16000)),
            chunk_ms=int(d.get("chunk_ms", 32)),
            yamnet_window_ms=int(d.get("yamnet_window_ms", 975)),
            device=d.get("device", None),
            vad_threshold=float(d.get("vad_threshold", 0.5)),
            speech_fraction_min=float(d.get("speech_fraction_min", 0.3)),
            classifier_confidence_min=float(d.get("classifier_confidence_min", 0.20)),
            log_level=d.get("log_level", "INFO"),
            log_file=d.get("log_file", "logs/sentinel.log"),
        )


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------

@dataclass
class SentinelConfig:
    daemon: DaemonConfig
    rules: List[RuleConfig]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SentinelConfig":
        return cls(
            daemon=DaemonConfig.from_dict(d.get("daemon", {})),
            rules=[RuleConfig.from_dict(r) for r in d.get("rules", [])],
        )


def load_config(path: str = "config/config.yaml") -> SentinelConfig:
    """Load and parse the YAML config file."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    return SentinelConfig.from_dict(raw)
