/**
 * useTraceSetting — persists the "Show Traces" developer toggle in localStorage.
 *
 * Off by default. Traces are developer-facing debug info, not game content.
 */

import { useState } from 'react';

const STORAGE_KEY = 'ai_dm_show_traces';

export function useTraceSetting() {
  const [showTraces, setShowTraces] = useState<boolean>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  function toggleTraces() {
    setShowTraces((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, String(next));
      } catch { /* ignore localStorage errors */ }
      return next;
    });
  }

  return { showTraces, toggleTraces };
}
