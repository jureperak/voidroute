"""Voice pipeline: one transcript in, one spoken reply out on the TV.

server.py records and transcribes; this module routes the transcript, asks the
LLM, synthesizes speech with SpeechT5 (tts.py) and casts it to the TV. Push-to-talk only:
nothing listens between button presses.
"""
import asyncio
import json
import os
import random
import re
import threading
import time
import uuid
from pathlib import Path

import httpx
import pychromecast
import tts
import weather

OLLAMA_URL = os.environ["OLLAMA_URL"]
LLM_MODEL = os.environ["LLM_MODEL"]
JF_URL = os.environ["JELLYFIN_URL"]
JF_KEY = os.environ["JELLYFIN_API_KEY"]
PUBLIC_BASE_URL = os.environ["PUBLIC_BASE_URL"]
TV_NAME = os.environ["TV_NAME"]
TV_IP = os.environ["TV_IP"]
TV_UUID = os.environ["TV_UUID"]

TV_MODEL = "2021/22 Philips UHD Android TV"  # as reported by Cast discovery
CLIP_DIR = Path("/tmp/tts")
FILLER_DIR = CLIP_DIR / "fillers"
CLIP_TTL_S = 900

SYSTEM_PROMPT = """Ti si glasovni asistent u domu korisnika. Govoriš hrvatski, neformalno (na "ti"), opušteno i prijateljski.
Uvijek vrati JSON s poljem "speech": što ćeš reći naglas. Najviše dvije kratke rečenice, bez popisa i markdowna. Ne počinji uvodnim frazama, filer je već izrečen.
Nikad ne izmišljaj činjenice. Nemaš pristup internetu ni aktualnim podacima. Ako nisi siguran, reci to."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"speech": {"type": "string"}},
    "required": ["speech"],
}

FILLERS = ["E evo sekunda, odmah provjeravam.", "Evo sad ću.", "Momentak, pogledam."]

# Stems, not exact words: the STT writes "puste" and "glasbu" for "pusti" and "glazbu"
MEDIA_RE = re.compile(r"\b(?:pust|reprodu)\w*\s+(.+?)\s+na\s+(?:televiz\w*|tv)\b", re.IGNORECASE)
PAUSE_RE = re.compile(r"\bpauz\w*", re.IGNORECASE)
STOP_RE = re.compile(r"\b(?:zaustavi|prekini)\w*", re.IGNORECASE)


_cast = None
_cast_lock = threading.Lock()  # one Cast command at a time
_tv_lock = asyncio.Lock()      # one clip on the TV at a time
_now_playing = None            # (url, mime) of the music on the TV
FILLER_CLIPS = []


def jf_headers():
    return {"X-Emby-Token": JF_KEY}


def _tv():
    global _cast
    if _cast is None:
        c = pychromecast.get_chromecast_from_host(
            (TV_IP, 8009, uuid.UUID(TV_UUID), TV_MODEL, TV_NAME), timeout=15)
        c.wait(timeout=15)
        _cast = c
    return _cast


def _cast_call(fn):
    """Run one Cast command. On failure, drop the connection so the next call reconnects."""
    global _cast
    with _cast_lock:
        try:
            return fn(_tv().media_controller)
        except Exception:
            _cast = None
            raise


def _play(url, mime):
    def fn(mc):
        mc.play_media(url, mime)
        mc.block_until_active(timeout=10)
    _cast_call(fn)


def _synth(text, path):
    return tts.get_speaker().to_wav(text, path)


def _prune_clips():
    cutoff = time.time() - CLIP_TTL_S
    for p in CLIP_DIR.glob("*.wav"):
        if p.stat().st_mtime < cutoff:
            p.unlink(missing_ok=True)


async def init_fillers():
    """Pre-synthesize the filler lines once, so they play instantly."""
    FILLER_DIR.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(FILLERS):
        path = FILLER_DIR / f"{i}.wav"
        dur = await asyncio.to_thread(_synth, text, path)
        FILLER_CLIPS.append((f"{PUBLIC_BASE_URL}/tts/fillers/{i}.wav", dur))


async def _say(text, local=None):
    print("ODGOVOR:", text, flush=True)
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    path = CLIP_DIR / f"{time.time_ns()}.wav"
    dur = await asyncio.to_thread(_synth, text, path)
    await asyncio.to_thread(_prune_clips)
    await _play_clip(f"{PUBLIC_BASE_URL}/tts/{path.name}", dur, local)


async def _play_clip(url, dur, local=None):
    """Play a speech clip. Cast replaces the current media, so music is restarted after it.

    With local set (a list), the clip URL is collected for the caller to play instead.
    """
    if local is not None:
        local.append(url)
        return
    async with _tv_lock:
        await asyncio.to_thread(_play, url, "audio/wav")
        await asyncio.sleep(dur + 0.3)
        if _now_playing:
            await asyncio.to_thread(_play, *_now_playing)


async def _find_track(http, query):
    r = await http.get(f"{JF_URL}/Items", headers=jf_headers(), params={
        "searchTerm": query, "IncludeItemTypes": "Audio", "Recursive": "true", "Limit": 1})
    r.raise_for_status()
    items = r.json().get("Items", [])
    return items[0] if items else None


async def _start_music(item):
    global _now_playing
    async with _tv_lock:
        _now_playing = (f"{PUBLIC_BASE_URL}/music/{item['Id']}", "audio/mpeg")
        await asyncio.to_thread(_play, *_now_playing)


async def _ask_llm(http, text):
    body = {"model": LLM_MODEL, "stream": False, "think": False, "format": RESPONSE_SCHEMA,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": text}],
            "options": {"temperature": 0.3, "num_ctx": 2048}}
    r = await http.post(f"{OLLAMA_URL}/api/chat", json=body)
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


async def handle(text, http, local=None):
    """Route one transcript. local (a list) collects speech clip URLs instead of casting them.

    Music always goes to the TV, even in local mode.
    """
    global _now_playing

    m = MEDIA_RE.search(text)
    if m:
        try:
            item = await _find_track(http, m.group(1))
        except httpx.HTTPError:
            await _say("Ne mogu trenutno pristupiti glazbi.", local)
            return
        if item is None:
            await _say(f"Nisam pronašao {m.group(1)}.", local)
            return
        await _say(f"Puštam {item['Name']}.", local)
        await _start_music(item)
        return

    if PAUSE_RE.search(text):
        await asyncio.to_thread(_cast_call, lambda mc: mc.pause())
        return

    if STOP_RE.search(text):
        _now_playing = None
        await asyncio.to_thread(_cast_call, lambda mc: mc.stop())
        return

    # Weather is looked up, not generated: the LLM has no live data
    if weather.WEATHER_RE.search(text):
        try:
            speech = await weather.answer(http, text)
        except (httpx.HTTPError, KeyError, ValueError):
            speech = "Ne mogu trenutno dohvatiti vremensku prognozu."
        await _say(speech, local)
        return

    # Question or chat: play a filler at once, then answer while the LLM works
    filler_url, filler_dur = random.choice(FILLER_CLIPS)
    filler = asyncio.create_task(_play_clip(filler_url, filler_dur, local))
    reply = await _ask_llm(http, text)
    await _say(reply["speech"], local)
    await filler
