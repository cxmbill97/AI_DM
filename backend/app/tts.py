"""Edge TTS synthesis — on-demand MP3 generation with file-based cache.

Cache key: MD5(voice:text) → tts_cache/{key}.mp3
Cache hit:  ~0ms (filesystem read)
Cache miss: ~200-400ms (network call to Edge TTS servers)

Text is capped at 300 chars before synthesis; DM responses are already short.
The cache directory is capped at MAX_CACHE_FILES entries; oldest files are
evicted when the limit is exceeded.
"""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Voice config
# ---------------------------------------------------------------------------

VOICES: dict[str, str] = {
    "zh": "zh-CN-YunjianNeural",  # dramatic male — good for mystery DM
    "en": "en-US-GuyNeural",
}

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

# Use an absolute path so the cache is always relative to this source file,
# regardless of where uvicorn is launched from.
CACHE_DIR = Path(__file__).parent.parent / "tts_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
MAX_CACHE_FILES = 200


def _evict_cache_if_needed() -> None:
    """Remove oldest MP3 files if the cache exceeds MAX_CACHE_FILES."""
    files = sorted(CACHE_DIR.glob("*.mp3"), key=lambda f: f.stat().st_mtime)
    while len(files) > MAX_CACHE_FILES:
        files.pop(0).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def synthesize(text: str, language: str = "zh") -> bytes:
    """Return MP3 bytes for *text* in the given *language*.

    Uses a file cache keyed by (voice, text hash).  Cache hits skip the
    network call entirely.  On any synthesis error, raises the exception
    so the endpoint can return an appropriate HTTP error.
    """
    text = text[:300].strip()
    if not text:
        return b""

    voice = VOICES.get(language, VOICES["zh"])
    key = hashlib.md5(f"{voice}:{text}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{key}.mp3"

    if cache_path.exists():
        logger.debug("TTS cache hit: %s", key)
        return cache_path.read_bytes()

    logger.debug("TTS cache miss — calling Edge TTS: voice=%s text=%r", voice, text[:60])
    communicate = edge_tts.Communicate(text, voice)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])

    mp3_bytes = buf.getvalue()

    cache_path.write_bytes(mp3_bytes)
    _evict_cache_if_needed()

    return mp3_bytes
