# audio-sentinel

A lightweight Windows daemon that monitors the default microphone audio stream and triggers configurable actions when specific sound sources exceed a decibel threshold.

## Architecture

```
Microphone → Ring Buffer (50ms chunks)
                    ↓
            Silero VAD  (is a human present?)
                    ↓ (if voice activity detected)
            YAMNet      (what class of sound is it?)
                    ↓
            RMS → dB(A) estimate per window
                    ↓
            Rule Engine (source_class + dB > threshold?)
                    ↓
            Action Dispatcher (log / kill process / [extensible])
```

## Components

| Module | Responsibility |
|---|---|
| `audio/capture.py` | Sounddevice stream → thread-safe ring buffer |
| `audio/processor.py` | Chunk slicing, RMS → dB conversion |
| `classification/vad.py` | Silero VAD wrapper |
| `classification/classifier.py` | YAMNet wrapper, returns (label, confidence) |
| `rules/engine.py` | Evaluates rules against classified events |
| `actions/base.py` | Abstract action interface |
| `actions/logger.py` | Log-to-file action |
| `actions/process_killer.py` | Kill process by name action |
| `utils/config.py` | Loads and validates config.yaml |

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Download YAMNet model (see below), then:

```bash
python -m audio_sentinel
```

## Configuration

Edit `config/config.yaml` to define rules, thresholds, and actions.

## Extending

- **New actions**: subclass `actions/base.py:BaseAction` and register in `config.yaml`
- **Source separation**: the classifier pipeline in `classification/classifier.py` has a placeholder interface for a `Separator` to be injected before classification

## Notes

- Source separation is intentionally not implemented yet — the architecture leaves a clean seam for it
- dB estimates are RMS-based approximations on the mixed signal, not true per-source SPL
