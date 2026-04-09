"""Tests for the TTS synthesis service and /api/tts endpoint.

All tests mock edge_tts.Communicate so no real network calls are made.
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_MP3 = b"ID3" + b"\x00" * 100  # minimal fake MP3 header


async def _fake_stream(chunks):
    """Async generator that yields a list of chunks."""
    for chunk in chunks:
        yield chunk


def _make_mock_communicate(audio_bytes: bytes = FAKE_MP3):
    """Return a patched edge_tts.Communicate class that yields one audio chunk."""
    mock_instance = MagicMock()
    mock_instance.stream = MagicMock(return_value=_fake_stream([{"type": "audio", "data": audio_bytes}]))
    mock_cls = MagicMock(return_value=mock_instance)
    return mock_cls


# ---------------------------------------------------------------------------
# Test 1: synthesize() returns bytes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesize_returns_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tts.CACHE_DIR", tmp_path)

    with patch("edge_tts.Communicate", _make_mock_communicate(FAKE_MP3)):
        # Re-import to pick up the monkeypatched CACHE_DIR
        import importlib
        import app.tts as tts_mod
        importlib.reload(tts_mod)
        monkeypatch.setattr("app.tts.CACHE_DIR", tmp_path)

        result = await tts_mod.synthesize("测试文本", "zh")

    assert isinstance(result, bytes)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# Test 2: cache hit skips network call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_skips_network(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tts.CACHE_DIR", tmp_path)

    # Pre-populate cache with known key
    voice = "zh-CN-YunjianNeural"
    text = "缓存测试"
    key = hashlib.md5(f"{voice}:{text}".encode()).hexdigest()
    (tmp_path / f"{key}.mp3").write_bytes(b"cached_audio")

    with patch("edge_tts.Communicate") as mock_cls:
        from app.tts import synthesize
        result = await synthesize(text, "zh")

    # Network should never have been called
    mock_cls.assert_not_called()
    assert result == b"cached_audio"


# ---------------------------------------------------------------------------
# Test 3: cache eviction kicks in at MAX_CACHE_FILES
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_eviction(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tts.CACHE_DIR", tmp_path)
    monkeypatch.setattr("app.tts.MAX_CACHE_FILES", 3)

    # Seed 3 existing cache files with distinct mtime ordering
    import time
    for i in range(3):
        p = tmp_path / f"old_{i:03d}.mp3"
        p.write_bytes(b"old")
        # Touch with increasing mtime
        t = time.time() - (10 - i)
        import os
        os.utime(p, (t, t))

    # Synthesize one more — should evict the oldest
    with patch("edge_tts.Communicate", _make_mock_communicate(FAKE_MP3)):
        from app.tts import synthesize, _evict_cache_if_needed
        voice = "zh-CN-YunjianNeural"
        text = "新文本"
        key = hashlib.md5(f"{voice}:{text}".encode()).hexdigest()
        cache_path = tmp_path / f"{key}.mp3"
        cache_path.write_bytes(FAKE_MP3)
        _evict_cache_if_needed()

    remaining = list(tmp_path.glob("*.mp3"))
    assert len(remaining) <= 3


# ---------------------------------------------------------------------------
# Test 4: /api/tts returns 400 for empty text
# ---------------------------------------------------------------------------

def test_tts_endpoint_empty_text():
    client = TestClient(app)
    resp = client.get("/api/tts?text=&lang=zh")
    assert resp.status_code == 400


def test_tts_endpoint_whitespace_text():
    client = TestClient(app)
    resp = client.get("/api/tts?text=   &lang=zh")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test 5: /api/tts returns audio/mpeg on success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tts_endpoint_returns_audio(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tts.CACHE_DIR", tmp_path)

    with patch("edge_tts.Communicate", _make_mock_communicate(FAKE_MP3)):
        # Pre-seed cache so TestClient (sync) can find it without async issues
        voice = "zh-CN-YunjianNeural"
        text = "欢迎来到推理之夜"
        key = hashlib.md5(f"{voice}:{text}".encode()).hexdigest()
        (tmp_path / f"{key}.mp3").write_bytes(FAKE_MP3)

        client = TestClient(app)
        resp = client.get(f"/api/tts?text={text}&lang=zh")

    assert resp.status_code == 200
    assert "audio/mpeg" in resp.headers["content-type"]
    assert len(resp.content) > 0


# ---------------------------------------------------------------------------
# Test 6: text is capped at 300 chars
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesize_caps_text_at_300(tmp_path, monkeypatch):
    monkeypatch.setattr("app.tts.CACHE_DIR", tmp_path)

    captured: list[str] = []

    def capturing_communicate(text, voice):
        captured.append(text)
        return _make_mock_communicate(FAKE_MP3)(text, voice)

    long_text = "A" * 500
    with patch("edge_tts.Communicate", capturing_communicate):
        from app.tts import synthesize
        await synthesize(long_text, "en")

    assert len(captured[0]) <= 300
