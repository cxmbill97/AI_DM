/**
 * Typed fetch() wrappers for the AI DM backend.
 * All /api/* requests are proxied to localhost:8000 by Vite.
 */

// ---------------------------------------------------------------------------
// Types (mirror backend Pydantic models)
// ---------------------------------------------------------------------------

export interface PuzzleSummary {
  id: string;
  title: string;
  difficulty: string;
  tags: string[];
}

export interface StartResponse {
  session_id: string;
  puzzle_id: string;
  title: string;
  surface: string;
}

export interface PrivateClue {
  id: string;
  title: string;
  content: string;
}

export interface Clue {
  id: string;
  title: string;
  content: string;
  unlock_keywords: string[];
}

export interface ChatResponse {
  judgment: string; // 是 / 不是 / 无关 / 部分正确
  response: string;
  truth_progress: number; // 0.0 – 1.0
  should_hint: boolean;
  hint?: string;
  truth?: string; // set when truth_progress >= 1.0 (game over)
  clue_unlocked?: Clue; // newly unlocked clue this turn, if any
}

// ---------------------------------------------------------------------------
// Internal helper
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export function listPuzzles(): Promise<PuzzleSummary[]> {
  return apiFetch('/api/puzzles');
}

export function startGame(puzzleId?: string): Promise<StartResponse> {
  return apiFetch('/api/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ puzzle_id: puzzleId ?? null }),
  });
}

export function sendMessage(
  sessionId: string,
  message: string,
): Promise<ChatResponse> {
  return apiFetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

// ---------------------------------------------------------------------------
// Multiplayer room types + calls
// ---------------------------------------------------------------------------

export interface RoomPlayer {
  id: string;
  name: string;
  connected: boolean;
}

export interface RoomState {
  room_id: string;
  puzzle_id: string;
  title: string;
  surface: string;
  players: RoomPlayer[];
  phase: string;
}

export function createRoom(puzzleId?: string): Promise<{ room_id: string }> {
  return apiFetch('/api/rooms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ puzzle_id: puzzleId ?? null }),
  });
}

export function getRoom(roomId: string): Promise<RoomState> {
  return apiFetch(`/api/rooms/${roomId}`);
}
