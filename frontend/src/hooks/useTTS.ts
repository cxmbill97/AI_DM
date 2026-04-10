/**
 * useTTS — Edge TTS playback hook.
 *
 * Fetches MP3 from GET /api/tts?text=…&lang=… and plays it via the Web Audio
 * HTMLAudioElement API.  Only one clip plays at a time; a new speak() call
 * stops whatever is currently playing before starting.
 *
 * `speaking` is true while audio is playing.
 * `stop()` cancels immediately.
 */

import { useCallback, useRef, useState } from 'react';

const TTS_STORAGE_KEY = 'tts_enabled';

export function useTTSSetting() {
  const [ttsEnabled, setTtsEnabledState] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(TTS_STORAGE_KEY);
      // Default: true — audio on by default
      return stored === null ? true : stored === 'true';
    } catch {
      return true;
    }
  });

  function toggleTTS() {
    setTtsEnabledState((prev) => {
      const next = !prev;
      try { localStorage.setItem(TTS_STORAGE_KEY, String(next)); } catch { /* ignore */ }
      return next;
    });
  }

  return { ttsEnabled, toggleTTS };
}

export function useTTS(language: string) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [speaking, setSpeaking] = useState(false);

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setSpeaking(false);
  }, []);

  const speak = useCallback(async (text: string) => {
    if (!text.trim()) return;

    // Stop whatever is currently playing
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    setSpeaking(true);
    try {
      const url = `/api/tts?text=${encodeURIComponent(text)}&lang=${language}`;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => setSpeaking(false);
      audio.onerror = () => setSpeaking(false);
      await audio.play();
    } catch {
      setSpeaking(false);
    }
  }, [language]);

  return { speak, stop, speaking };
}
