"""Croatian speech-to-text with classla/wav2vec2-xls-r-parlaspeech-hr, on the CPU.

Input is 16 kHz mono float32 PCM (server.py converts the phone recording with ffmpeg).
The model was trained on parliament speech and outputs lowercase text without
punctuation, which is enough for the router, which matches word stems.
"""
import threading

import numpy as np
from transformers import pipeline

STT_MODEL = "classla/wav2vec2-xls-r-parlaspeech-hr"
SAMPLE_RATE = 16000

_asr = None
_lock = threading.Lock()


def _get_asr():
    global _asr
    if _asr is None:
        _asr = pipeline("automatic-speech-recognition", model=STT_MODEL, device=-1)
    return _asr


def transcribe(pcm: np.ndarray) -> str:
    """Return the text of one recording. Empty string if nothing was recognized."""
    with _lock:
        out = _get_asr()({"raw": pcm, "sampling_rate": SAMPLE_RATE})
    return out["text"].strip()
