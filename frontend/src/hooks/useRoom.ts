/**
 * WebSocket hook for multiplayer room connections.
 *
 * Connects to ws://localhost:8000/ws/{roomId}?player_name={name}
 * (Vite dev server proxies /ws → backend).
 *
 * Exposes:
 *   messages           — chronological chat + system + DM messages
 *   players            — current player list (updated from room_snapshot + system events)
 *   clues              — unlocked clues accumulated this session
 *   connected          — WebSocket open?
 *   progress           — truth_progress 0–1
 *   truth              — set when game is won
 *   puzzle             — { title, surface } from room_snapshot
 *   sendMessage        — send a { type: "chat" } message
 *   privateClues       — this player's private clues (from private_clue WS message)
 *   privateMessages    — private DM chat exchange
 *   leakWarning        — non-null when server sends leak_warning; auto-clears after 4s
 *   sendPrivateMessage — send a { type: "private_chat" } message
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Clue, PrivateClue, RoomPlayer } from '../api';

// ---------------------------------------------------------------------------
// Message shape union (rendered by RoomPage)
// ---------------------------------------------------------------------------

export interface SystemMsg {
  type: 'system';
  text: string;
  timestamp: number;
}

export interface PlayerMsg {
  type: 'player_message';
  player_name: string;
  text: string;
  timestamp: number;
}

export interface DmResponseMsg {
  type: 'dm_response';
  player_name: string;
  judgment: string;
  response: string;
  truth_progress: number;
  clue_unlocked: Clue | null;
  hint: string | null;
  truth: string | null;
  timestamp: number;
}

export interface InterventionMsg {
  type: 'dm_intervention';
  text: string;
  reason: string; // "silence" | "encouragement" | "hint"
  timestamp: number;
}

export type RoomMessage = SystemMsg | PlayerMsg | DmResponseMsg | InterventionMsg;

// ---------------------------------------------------------------------------
// Private chat message types
// ---------------------------------------------------------------------------

export interface PrivatePlayerMsg {
  type: 'private_question';
  text: string;
  timestamp: number;
}

export interface PrivateDMMsg {
  type: 'private_dm_response';
  response: string;
  timestamp: number;
}

export type PrivateMessage = PrivatePlayerMsg | PrivateDMMsg;

// ---------------------------------------------------------------------------
// Puzzle info from room_snapshot
// ---------------------------------------------------------------------------

export interface RoomPuzzleInfo {
  title: string;
  surface: string;
  puzzle_id: string;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

export function useRoom(roomId: string, playerName: string) {
  const [messages, setMessages] = useState<RoomMessage[]>([]);
  const [players, setPlayers] = useState<RoomPlayer[]>([]);
  const [clues, setClues] = useState<Clue[]>([]);
  const [connected, setConnected] = useState(false);
  const [progress, setProgress] = useState(0);
  const [truth, setTruth] = useState<string | null>(null);
  const [puzzle, setPuzzle] = useState<RoomPuzzleInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [questionsByPlayer, setQuestionsByPlayer] = useState<Record<string, number>>({});
  const [cluesByPlayer, setCluesByPlayer] = useState<Record<string, number>>({});
  const [dmTyping, setDmTyping] = useState(false);

  // Phase 3: private clues + private chat + leak warning
  const [privateClues, setPrivateClues] = useState<PrivateClue[]>([]);
  const [privateMessages, setPrivateMessages] = useState<PrivateMessage[]>([]);
  const [leakWarning, setLeakWarning] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const mountedRef = useRef(true);

  const appendMessage = useCallback((msg: RoomMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const addClue = useCallback((clue: Clue) => {
    setClues((prev) => {
      if (prev.some((c) => c.id === clue.id)) return prev;
      return [...prev, clue];
    });
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const params = new URLSearchParams({ player_name: playerName });
    const url = `/ws/${roomId}?${params.toString()}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      setConnected(true);
      setError(null);
      // Don't reset retriesRef here — reset only after a stable room_snapshot
      // to prevent infinite retry loops when the server immediately closes.
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return;
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(event.data as string) as Record<string, unknown>;
      } catch {
        return;
      }

      const type = data.type as string;

      if (type === 'error') {
        setError(data.text as string);
        return;
      }

      if (type === 'room_snapshot') {
        retriesRef.current = 0; // stable connection — reset retry counter
        setPuzzle({
          title: data.title as string,
          surface: data.surface as string,
          puzzle_id: data.puzzle_id as string,
        });
        setPlayers(data.players as RoomPlayer[]);
        return;
      }

      if (type === 'system') {
        const msg: SystemMsg = {
          type: 'system',
          text: data.text as string,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        };
        appendMessage(msg);
        return;
      }

      if (type === 'player_message') {
        const msg: PlayerMsg = {
          type: 'player_message',
          player_name: data.player_name as string,
          text: data.text as string,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        };
        appendMessage(msg);
        setQuestionsByPlayer((prev) => ({ ...prev, [msg.player_name]: (prev[msg.player_name] ?? 0) + 1 }));
        setDmTyping(true);
        return;
      }

      if (type === 'dm_intervention') {
        const msg: InterventionMsg = {
          type: 'dm_intervention',
          text: data.text as string,
          reason: (data.reason as string) ?? 'silence',
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        };
        appendMessage(msg);
        return;
      }

      if (type === 'dm_response') {
        const msg: DmResponseMsg = {
          type: 'dm_response',
          player_name: data.player_name as string,
          judgment: data.judgment as string,
          response: data.response as string,
          truth_progress: data.truth_progress as number,
          clue_unlocked: (data.clue_unlocked as Clue | null) ?? null,
          hint: (data.hint as string | null) ?? null,
          truth: (data.truth as string | null) ?? null,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        };
        setDmTyping(false);
        appendMessage(msg);
        setProgress(msg.truth_progress);
        if (msg.clue_unlocked) addClue(msg.clue_unlocked);
        if (msg.clue_unlocked) setCluesByPlayer((prev) => ({ ...prev, [msg.player_name]: (prev[msg.player_name] ?? 0) + 1 }));
        if (msg.truth) setTruth(msg.truth);
        return;
      }

      // ---- Phase 3: private clue delivery ----
      if (type === 'private_clue') {
        const incoming = (data.clues as PrivateClue[]) ?? [];
        setPrivateClues((prev) => {
          const existingIds = new Set(prev.map((c) => c.id));
          return [...prev, ...incoming.filter((c) => !existingIds.has(c.id))];
        });
        return;
      }

      // ---- Phase 3: private DM response ----
      if (type === 'private_dm_response') {
        const msg: PrivateDMMsg = {
          type: 'private_dm_response',
          response: data.response as string,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        };
        setPrivateMessages((prev) => [...prev, msg]);
        return;
      }

      // ---- Phase 3: leak warning ----
      if (type === 'leak_warning') {
        const txt = data.text as string;
        setLeakWarning(txt);
        // Auto-clear after 4s
        setTimeout(() => setLeakWarning(null), 4000);
        return;
      }
    };

    ws.onerror = () => {
      // onclose will fire next; handle retry there
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      wsRef.current = null;

      if (retriesRef.current < MAX_RETRIES) {
        retriesRef.current += 1;
        setTimeout(connect, RETRY_DELAY_MS);
      } else {
        setError('连接断开，请刷新页面重试');
      }
    };
  }, [roomId, playerName, appendMessage, addClue]);

  useEffect(() => {
    mountedRef.current = true;
    // Defer by one tick so React StrictMode's synchronous cleanup can cancel
    // this timer before the WebSocket is ever created, preventing a race where
    // two connections open simultaneously and the server rejects the second as
    // "name already in use".
    const timer = setTimeout(connect, 0);
    return () => {
      clearTimeout(timer);
      mountedRef.current = false;
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((text: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'chat', text }));
  }, []);

  const sendPrivateMessage = useCallback((text: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    // Optimistically add to local private messages
    setPrivateMessages((prev) => [
      ...prev,
      { type: 'private_question', text, timestamp: Date.now() / 1000 },
    ]);
    ws.send(JSON.stringify({ type: 'private_chat', text }));
  }, []);

  return {
    messages,
    players,
    clues,
    connected,
    progress,
    truth,
    puzzle,
    error,
    questionsByPlayer,
    cluesByPlayer,
    dmTyping,
    sendMessage,
    privateClues,
    privateMessages,
    leakWarning,
    sendPrivateMessage,
  };
}
