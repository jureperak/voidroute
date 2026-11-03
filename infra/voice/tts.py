"""Croatian speech synthesis with SpeechT5 (nikolab/speecht5_tts_hr), on the CPU.

The model card limits quality to sequences of about 20 words, so the text is
split into short phrases first. Phrases are synthesized one by one and joined
with a short pause.
"""
import os
import re
import threading
import wave
from pathlib import Path

import numpy as np
import torch
from transformers import SpeechT5ForTextToSpeech, SpeechT5HifiGan, SpeechT5Processor

SPEECHT5_BASE = "microsoft/speecht5_tts"          # processor (tokenizer) of the base model
SPEECHT5_HR = "nikolab/speecht5_tts_hr"           # Croatian fine-tune
SPEECHT5_VOCODER = "microsoft/speecht5_hifigan"   # mel spectrogram -> waveform
SPEAKER_XVECTOR = Path(os.environ["SPEAKER_XVECTOR"])  # 512 floats, one voice
SAMPLE_RATE = 16000                               # SpeechT5 output rate
MAX_WORDS = 12                                    # below the ~20-word limit from the model card
PAUSE_S = 0.15

_CLAUSE_END = re.compile(r"(?<=[.,;:!?])\s+")

# SpeechT5's character vocabulary has no č ć š ž đ. Without this they become
# <unk> and are lost. Spelling them with letters it knows approximates the sound.
_SPELLING = str.maketrans({
    "č": "ch", "ć": "ch", "š": "sh", "ž": "zh", "đ": "dj",
    "Č": "Ch", "Ć": "Ch", "Š": "Sh", "Ž": "Zh", "Đ": "Dj",
})


def split_for_tts(text: str, max_words: int = MAX_WORDS) -> list[str]:
    """Split at punctuation, then cap each phrase at max_words.

    Clauses longer than max_words are cut into word groups. Short neighbouring
    clauses are merged again while the result stays within max_words.
    """
    pieces: list[str] = []
    for clause in _CLAUSE_END.split(text.strip()):
        words = clause.split()
        while len(words) > max_words:
            pieces.append(" ".join(words[:max_words]))
            words = words[max_words:]
        if words:
            pieces.append(" ".join(words))

    phrases: list[str] = []
    for piece in pieces:
        if phrases and len(phrases[-1].split()) + len(piece.split()) <= max_words:
            phrases[-1] += " " + piece
        else:
            phrases.append(piece)
    return phrases


def for_speecht5(text: str) -> str:
    return text.translate(_SPELLING)


class Speaker:
    """Loads the model once. Synthesis calls must not run in parallel."""

    def __init__(self) -> None:
        self.processor = SpeechT5Processor.from_pretrained(SPEECHT5_BASE)
        self.model = SpeechT5ForTextToSpeech.from_pretrained(SPEECHT5_HR).eval()
        self.vocoder = SpeechT5HifiGan.from_pretrained(SPEECHT5_VOCODER).eval()
        self.voice = torch.tensor(np.load(SPEAKER_XVECTOR), dtype=torch.float32).reshape(1, -1)
        self._lock = threading.Lock()

    def _phrase(self, phrase: str) -> np.ndarray:
        inputs = self.processor(text=for_speecht5(phrase), return_tensors="pt")
        with torch.no_grad():
            wav = self.model.generate_speech(inputs["input_ids"], self.voice,
                                             vocoder=self.vocoder)
        return wav.numpy()

    def to_wav(self, text: str, path: Path) -> float:
        """Write the speech for text to a 16-bit mono WAV. Returns its length in seconds."""
        silence = np.zeros(int(SAMPLE_RATE * PAUSE_S), dtype=np.float32)
        parts: list[np.ndarray] = []
        with self._lock:
            for phrase in split_for_tts(text):
                parts.append(self._phrase(phrase))
                parts.append(silence)
        audio = np.concatenate(parts[:-1]) if parts else silence
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm.tobytes())
        return len(pcm) / SAMPLE_RATE


_speaker: Speaker | None = None


def get_speaker() -> Speaker:
    global _speaker
    if _speaker is None:
        _speaker = Speaker()
    return _speaker
