/**
 * useTraceStream — subscribes to the SSE trace stream for a room.
 *
 * Returns an array of AgentTrace objects (newest first, capped at 20).
 * Automatically reconnects on error after a 3s back-off.
 * Cleans up the EventSource on unmount.
 */

import { useEffect, useRef, useState } from 'react';
import type { AgentTrace } from '../api';

const MAX_TRACES = 20;

export function useTraceStream(roomId: string, enabled: boolean): AgentTrace[] {
  const [traces, setTraces] = useState<AgentTrace[]>([]);
  const esRef = useRef<EventSource | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled || !roomId) return;

    function connect() {
      const es = new EventSource(`/api/rooms/${roomId}/traces/live`);
      esRef.current = es;

      es.onmessage = (e) => {
        try {
          const trace: AgentTrace = JSON.parse(e.data);
          setTraces((prev) => [trace, ...prev].slice(0, MAX_TRACES));
        } catch {
          // malformed event — skip
        }
      };

      es.onerror = () => {
        es.close();
        esRef.current = null;
        // Reconnect after 3s
        retryRef.current = setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      esRef.current?.close();
      esRef.current = null;
      if (retryRef.current) clearTimeout(retryRef.current);
    };
  }, [roomId, enabled]);

  // Reset traces when disabled
  useEffect(() => {
    if (!enabled) setTraces([]);
  }, [enabled]);

  return traces;
}
