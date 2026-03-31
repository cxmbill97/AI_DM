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

export interface ScriptSummary {
  id: string;
  title: string;
  difficulty: string;
  player_count: number;
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

export function listScripts(): Promise<ScriptSummary[]> {
  return apiFetch('/api/scripts');
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
  character?: string; // char_id assigned (murder mystery only)
}

export interface RoomState {
  room_id: string;
  puzzle_id: string;
  title: string;
  surface: string;
  players: RoomPlayer[];
  phase: string;
  game_type: string;
}

export interface CreateRoomOptions {
  game_type?: 'turtle_soup' | 'murder_mystery';
  puzzle_id?: string;
  script_id?: string;
}

/**
 * Create a new multiplayer room.
 * Accepts either a puzzle_id string (backward compat) or a CreateRoomOptions object.
 */
export function createRoom(
  options?: string | CreateRoomOptions,
): Promise<{ room_id: string; game_type: string }> {
  let body: Record<string, unknown>;
  if (typeof options === 'string' || options === undefined) {
    body = { game_type: 'turtle_soup', puzzle_id: options ?? null };
  } else {
    body = { game_type: options.game_type ?? 'turtle_soup', ...options };
  }
  return apiFetch('/api/rooms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function getRoom(roomId: string): Promise<RoomState> {
  return apiFetch(`/api/rooms/${roomId}`);
}
