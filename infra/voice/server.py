"""HTTP side of the voice assistant. Run by uvicorn on port 8000, behind Caddy.

  GET  /                 push-to-talk page for the phone
  POST /talk             one recording (webm/mp4) in, one spoken reply out
  GET  /tts/...          speech clips the TV fetches
  GET  /music/{item_id}  Jellyfin audio, proxied so the API key never reaches the TV
"""
import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import assistant
import stt

HERE = Path(__file__).resolve().parent
HEX32 = re.compile(r"[0-9a-f]{32}")


@asynccontextmanager
async def lifespan(app):
    await assistant.init_fillers()
    yield


app = FastAPI(lifespan=lifespan)
assistant.CLIP_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/tts", StaticFiles(directory=assistant.CLIP_DIR), name="tts")


async def to_pcm16k(blob: bytes) -> np.ndarray:
    """Browser recording (webm or mp4) -> 16 kHz mono float32 PCM."""
    p = await asyncio.create_subprocess_exec(
        "ffmpeg", "-loglevel", "error", "-i", "pipe:0",
        "-f", "s16le", "-ac", "1", "-ar", "16000", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate(blob)
    return np.frombuffer(out, np.int16).astype(np.float32) / 32768


@app.get("/")
async def index():
    return FileResponse(HERE / "index.html")


@app.post("/talk")
async def talk(request: Request, local: bool = False):
    """One recording in. The reply goes to the TV, or with ?local=true its clip URLs are returned."""
    pcm = await to_pcm16k(await request.body())
    if pcm.size < 8000:  # under half a second: an accidental tap
        return {"ok": False, "reason": "too short"}
    text = await asyncio.to_thread(stt.transcribe, pcm)
    if not text:
        return {"ok": False, "reason": "nothing heard"}
    print("TI:", text, flush=True)
    spoken = [] if local else None
    async with httpx.AsyncClient(timeout=120) as http:
        await assistant.handle(text, http, spoken)
    return {"ok": True, "text": text, "audio": spoken or []}


@app.get("/music/{item_id}")
async def music(item_id: str):
    if not HEX32.fullmatch(item_id):
        raise HTTPException(status_code=404)

    async def stream():
        async with httpx.AsyncClient(timeout=None) as http:
            async with http.stream("GET", f"{assistant.JF_URL}/Audio/{item_id}/stream.mp3",
                                   headers=assistant.jf_headers()) as r:
                async for chunk in r.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), media_type="audio/mpeg")
