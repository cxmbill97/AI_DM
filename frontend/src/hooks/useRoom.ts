/**
 * WebSocket hook for multiplayer room connections.
 *
 * Supports both turtle_soup (Phase 2-3) and murder_mystery (Phase 4).
 * Game type is detected from the room_snapshot message.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentTrace, Clue, PrivateClue, RoomPlayer } from '../api';
import { useT } from '../i18n';

// ---------------------------------------------------------------------------
// Turtle soup message shapes
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
  // Turtle soup fields
  player_name?: string;
  judgment?: string;
  response?: string;
  truth_progress?: number;
  clue_unlocked?: Clue | null;
  hint?: string | null;
  truth?: string | null;
  // Murder mystery fields
  text?: string;
  phase?: string;
  clue?: { id: string; title: string; content: string } | null;
  trace?: AgentTrace | null;
  timestamp: number;
  // Streaming state (murder mystery)
  streaming?: boolean;
  streamId?: string;
}

export interface InterventionMsg {
  type: 'dm_intervention';
  text: string;
  reason: string;
  timestamp: number;
}

// ---------------------------------------------------------------------------
// Murder mystery message shapes
// ---------------------------------------------------------------------------

export interface PhaseChangeMsg {
  type: 'phase_change';
  new_phase: string;
  duration: number | null;
  description: string;
  timestamp: number;
}

export interface CharAssignedMsg {
  type: 'character_assigned';
  player_name: string;
  char_id: string;
  char_name: string;
  public_bio: string;
  timestamp: number;
}

export interface ClueFoundMsg {
  type: 'clue_found';
  text: string;
  clue: { id: string; title: string; content: string };
  timestamp: number;
}

export interface VoteCastMsg {
  type: 'vote_cast';
  text: string;
  count: number;
  total: number;
  timestamp: number;
}

export interface VoteResultMsg {
  type: 'vote_result';
  status: string;
  winner: string | null;
  tally: Record<string, number>;
  is_correct: boolean;
  text: string;
  timestamp: number;
}

export interface PhaseBlockedMsg {
  type: 'phase_blocked';
  text: string;
  timestamp: number;
}

export type RoomMessage =
  | SystemMsg
  | PlayerMsg
  | DmResponseMsg
  | InterventionMsg
  | PhaseChangeMsg
  | CharAssignedMsg
  | ClueFoundMsg
  | VoteCastMsg
  | VoteResultMsg
  | PhaseBlockedMsg;

// ---------------------------------------------------------------------------
// Private chat message types (turtle soup only)
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
// Murder mystery specific state types
// ---------------------------------------------------------------------------

export interface MmCharInfo {
  id: string;
  name: string;
  public_bio: string;
}

export interface MyCharInfo {
  char_id: string;
  char_name: string;
  secret_bio: string;
  personal_script: string | null;
}

export interface VoteResultInfo {
  status: string;
  winner: string | null;
  tally: Record<string, number>;
  is_correct: boolean;
  text: string;
}

export interface ReconstructionQuestion {
  index: number;
  total: number;
  question_id: string;
  question: string;
}

export interface ReconstructionResult {
  question_id: string;
  index: number;
  result: 'correct' | 'partial' | 'wrong';
  score: number;
  total_score: number;
  text: string;
}

export interface ReconstructionComplete {
  total_score: number;
  max_score: number;
  pct: number;
  text: string;
}

// ---------------------------------------------------------------------------
// Puzzle/script info from room_snapshot
// ---------------------------------------------------------------------------

export interface RoomPuzzleInfo {
  title: string;
  surface: string;
  puzzle_id: string;
}

export interface ScriptTheme {
  primary_color: string;
  bg_tone: string;
  era: string;
  setting: string;
  dm_persona: string;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

export function useRoom(roomId: string, token: string) {
  const { t } = useT();

  // Shared state
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

  // Turtle soup private chat
  const [privateClues, setPrivateClues] = useState<PrivateClue[]>([]);
  const [privateMessages, setPrivateMessages] = useState<PrivateMessage[]>([]);
  const [leakWarning, setLeakWarning] = useState<string | null>(null);

  // Murder mystery state
  const [gameType, setGameType] = useState<'turtle_soup' | 'murder_mystery'>('turtle_soup');
  const [mmPhase, setMmPhase] = useState<string | null>(null);
  const [mmTimeRemaining, setMmTimeRemaining] = useState<number | null>(null);
  const [mmRequiredPlayers, setMmRequiredPlayers] = useState<number>(2);
  const [mmGameMode, setMmGameMode] = useState<'whodunit' | 'reconstruction'>('whodunit');
  const [characters, setCharacters] = useState<MmCharInfo[]>([]);
  const [myChar, setMyChar] = useState<MyCharInfo | null>(null);
  const [voteCandidates, setVoteCandidates] = useState<MmCharInfo[] | null>(null);
  const [voteCount, setVoteCount] = useState<{ count: number; total: number } | null>(null);
  const [voteResult, setVoteResult] = useState<VoteResultInfo | null>(null);
  const [hasVoted, setHasVoted] = useState(false);
  const [skipVotes, setSkipVotes] = useState<{ voted: number; needed: number } | null>(null);
  const [hasSkipVoted, setHasSkipVoted] = useState(false);
  // Script theme (murder mystery only)
  const [scriptTheme, setScriptTheme] = useState<ScriptTheme | null>(null);

  // Reconstruction mode state
  const [reconstructionQuestion, setReconstructionQuestion] = useState<ReconstructionQuestion | null>(null);
  const [reconstructionResults, setReconstructionResults] = useState<ReconstructionResult[]>([]);
  const [reconstructionComplete, setReconstructionComplete] = useState<ReconstructionComplete | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const mountedRef = useRef(true);
  // Tracks the streamId of the currently-streaming DM message
  const streamingIdRef = useRef<string | null>(null);

  // Note: mmTimeRemaining is the server-authoritative initial value for the current phase.
  // PhaseBar.tsx handles its own client-side countdown from this seed — no duplicate interval here.

  const appendMessage = useCallback((msg: RoomMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const addClue = useCallback((clue: Clue | { id: string; title: string; content: string }) => {
    setClues((prev) => {
      if (prev.some((c) => c.id === clue.id)) return prev;
      return [...prev, { ...clue, unlock_keywords: [] } as Clue];
    });
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    // Explicit protocol detection so wss:// is used when the page is served over
    // HTTPS (ngrok / cloudflare tunnel). Relative WebSocket URLs are non-standard
    // and silently break in some browsers when the page protocol is https:.
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${roomId}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      setConnected(true);
      setError(null);
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

      if (type === 'players_update') {
        setPlayers(data.players as RoomPlayer[]);
        return;
      }

      if (type === 'room_snapshot') {
        retriesRef.current = 0;
        const gt = (data.game_type as string) ?? 'turtle_soup';
        setGameType(gt as 'turtle_soup' | 'murder_mystery');

        if (gt === 'murder_mystery') {
          setMmPhase((data.current_phase as string) ?? null);
          setMmTimeRemaining((data.time_remaining as number | null) ?? null);
          setMmRequiredPlayers((data.required_players as number) ?? 2);
          setMmGameMode(((data.game_mode as string) ?? 'whodunit') as 'whodunit' | 'reconstruction');
          setCharacters((data.characters as MmCharInfo[]) ?? []);
          setPlayers(data.players as RoomPlayer[]);
          setPuzzle({
            title: data.title as string,
            surface: '',
            puzzle_id: data.script_id as string,
          });
          if (data.theme) setScriptTheme(data.theme as ScriptTheme);
        } else {
          setPuzzle({
            title: data.title as string,
            surface: data.surface as string,
            puzzle_id: data.puzzle_id as string,
          });
          setPlayers(data.players as RoomPlayer[]);
        }
        return;
      }

      if (type === 'system') {
        appendMessage({
          type: 'system',
          text: data.text as string,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        });
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
        appendMessage({
          type: 'dm_intervention',
          text: data.text as string,
          reason: (data.reason as string) ?? 'silence',
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        });
        return;
      }

      if (type === 'dm_response') {
        setDmTyping(false);
        const msg: DmResponseMsg = {
          type: 'dm_response',
          player_name: data.player_name as string | undefined,
          judgment: data.judgment as string | undefined,
          response: data.response as string | undefined,
          truth_progress: (data.truth_progress as number | undefined),
          clue_unlocked: (data.clue_unlocked as Clue | null | undefined) ?? null,
          hint: (data.hint as string | null | undefined) ?? null,
          truth: (data.truth as string | null | undefined) ?? null,
          // MM fields
          text: data.text as string | undefined,
          phase: data.phase as string | undefined,
          clue: (data.clue as { id: string; title: string; content: string } | null | undefined) ?? null,
          trace: (data.trace as AgentTrace | null | undefined) ?? null,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        };
        appendMessage(msg);
        if (msg.truth_progress !== undefined) setProgress(msg.truth_progress);
        if (msg.clue_unlocked) {
          addClue(msg.clue_unlocked);
          setCluesByPlayer((prev) => ({ ...prev, [msg.player_name ?? '']: (prev[msg.player_name ?? ''] ?? 0) + 1 }));
        }
        if (msg.truth) setTruth(msg.truth);
        return;
      }

      // ---- Murder mystery: clue found ----
      if (type === 'clue_found') {
        setDmTyping(false);
        const clueData = data.clue as { id: string; title: string; content: string };
        if (clueData) addClue(clueData);
        appendMessage({
          type: 'clue_found',
          text: (data.text as string) ?? '',
          clue: clueData,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        });
        return;
      }

      // ---- Murder mystery: phase change ----
      if (type === 'phase_change') {
        const newPhase = data.new_phase as string;
        setMmPhase(newPhase);
        setMmTimeRemaining((data.duration as number | null) ?? null);
        // Reset vote/skip state on phase change
        if (newPhase !== 'voting') {
          setVoteCount(null);
          setHasVoted(false);
        }
        setSkipVotes(null);
        setHasSkipVoted(false);
        appendMessage({
          type: 'phase_change',
          new_phase: newPhase,
          duration: (data.duration as number | null) ?? null,
          description: (data.description as string) ?? newPhase,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        });
        return;
      }

      // ---- Murder mystery: skip vote update ----
      if (type === 'skip_vote_update') {
        setSkipVotes({
          voted: data.voted as number,
          needed: data.needed as number,
        });
        return;
      }

      // ---- Murder mystery: character assigned ----
      if (type === 'character_assigned') {
        setPlayers((prev) => prev.map((p) =>
          p.name === (data.player_name as string)
            ? { ...p, character: data.char_id as string }
            : p,
        ));
        appendMessage({
          type: 'character_assigned',
          player_name: data.player_name as string,
          char_id: data.char_id as string,
          char_name: data.char_name as string,
          public_bio: data.public_bio as string,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        });
        return;
      }

      // ---- Murder mystery: my character secret (private) ----
      if (type === 'character_secret') {
        setMyChar({
          char_id: data.char_id as string,
          char_name: data.char_name as string,
          secret_bio: data.secret_bio as string,
          personal_script: (data.personal_script as string | null) ?? null,
        });
        return;
      }

      // ---- Murder mystery: vote prompt ----
      if (type === 'vote_prompt') {
        setVoteCandidates((data.candidates as MmCharInfo[]) ?? []);
        appendMessage({
          type: 'system',
          text: (data.text as string) ?? t('voting.phase_started'),
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        });
        return;
      }

      // ---- Murder mystery: vote cast (anonymous count) ----
      if (type === 'vote_cast') {
        setVoteCount({ count: data.count as number, total: data.total as number });
        appendMessage({
          type: 'vote_cast',
          text: data.text as string,
          count: data.count as number,
          total: data.total as number,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        });
        return;
      }

      // ---- Murder mystery: vote result ----
      if (type === 'vote_result') {
        const result: VoteResultInfo = {
          status: data.status as string,
          winner: (data.winner as string | null) ?? null,
          tally: (data.tally as Record<string, number>) ?? {},
          is_correct: (data.is_correct as boolean) ?? false,
          text: data.text as string,
        };
        setVoteResult(result);
        appendMessage({
          type: 'vote_result',
          ...result,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        });
        return;
      }

      // ---- Turtle soup: private clue delivery ----
      if (type === 'private_clue') {
        const incoming = (data.clues as PrivateClue[]) ?? [];
        setPrivateClues((prev) => {
          const existingIds = new Set(prev.map((c) => c.id));
          return [...prev, ...incoming.filter((c) => !existingIds.has(c.id))];
        });
        return;
      }

      // ---- Turtle soup: private DM response ----
      if (type === 'private_dm_response') {
        setPrivateMessages((prev) => [
          ...prev,
          {
            type: 'private_dm_response',
            response: data.response as string,
            timestamp: (data.timestamp as number) ?? Date.now() / 1000,
          },
        ]);
        return;
      }

      // ---- Turtle soup: leak warning ----
      if (type === 'leak_warning') {
        setLeakWarning(data.text as string);
        setTimeout(() => setLeakWarning(null), 4000);
        return;
      }

      // ---- Server-controlled typing indicator (explicit override) ----
      if (type === 'dm_typing') {
        setDmTyping(data.typing as boolean);
        return;
      }

      // ---- Murder mystery streaming: judgment arrives first ----
      if (type === 'dm_stream_start') {
        setDmTyping(false); // streaming bubble replaces the typing dots
        const streamId = crypto.randomUUID();
        streamingIdRef.current = streamId;
        // Insert a placeholder DM message with judgment badge, no text yet
        const placeholder: DmResponseMsg = {
          type: 'dm_response',
          player_name: data.player_name as string | undefined,
          judgment: data.judgment as string | undefined,
          text: '',
          streaming: true,
          streamId,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        };
        appendMessage(placeholder);
        return;
      }

      // ---- Murder mystery streaming: append token chunk ----
      if (type === 'dm_stream_chunk') {
        const sid = streamingIdRef.current;
        if (sid) {
          setMessages((prev) =>
            prev.map((m) =>
              m.type === 'dm_response' && (m as DmResponseMsg).streamId === sid
                ? { ...m, text: ((m as DmResponseMsg).text ?? '') + (data.text as string) }
                : m,
            ),
          );
        }
        return;
      }

      // ---- Murder mystery streaming: finalize ----
      if (type === 'dm_stream_end') {
        const sid = streamingIdRef.current;
        streamingIdRef.current = null;
        setDmTyping(false);
        if (sid) {
          setMessages((prev) =>
            prev.map((m) => {
              if (m.type !== 'dm_response') return m;
              const dm = m as DmResponseMsg;
              if (dm.streamId !== sid) return m;
              // If backend flagged a safety replace, swap the accumulated text
              const finalText = (data.replace as string | undefined) ?? dm.text ?? '';
              return {
                ...dm,
                text: finalText,
                streaming: false,
                clue: (data.clue as DmResponseMsg['clue']) ?? null,
                trace: (data.trace as AgentTrace | null | undefined) ?? null,
              };
            }),
          );
          // Add clue to sidebar if found
          const clueData = data.clue as { id: string; title: string; content: string } | null;
          if (clueData) addClue(clueData);
        }
        return;
      }

      // ---- phase_blocked: show as error in chat ----
      if (type === 'phase_blocked') {
        setDmTyping(false);
        appendMessage({
          type: 'phase_blocked',
          text: data.text as string,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        });
        return;
      }

      // ---- Reconstruction: current question ----
      if (type === 'reconstruction_question') {
        setReconstructionQuestion({
          index: data.index as number,
          total: data.total as number,
          question_id: data.question_id as string,
          question: data.question as string,
        });
        return;
      }

      // ---- Reconstruction: answer scored ----
      if (type === 'reconstruction_result') {
        const res: ReconstructionResult = {
          question_id: data.question_id as string,
          index: data.index as number,
          result: data.result as 'correct' | 'partial' | 'wrong',
          score: data.score as number,
          total_score: data.total_score as number,
          text: data.text as string,
        };
        setReconstructionResults((prev) => [...prev, res]);
        appendMessage({
          type: 'system',
          text: res.text,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        });
        return;
      }

      // ---- Reconstruction: all questions done ----
      if (type === 'reconstruction_complete') {
        const complete: ReconstructionComplete = {
          total_score: data.total_score as number,
          max_score: data.max_score as number,
          pct: data.pct as number,
          text: data.text as string,
        };
        setReconstructionComplete(complete);
        setReconstructionQuestion(null);
        appendMessage({
          type: 'system',
          text: complete.text,
          timestamp: (data.timestamp as number) ?? Date.now() / 1000,
        });
        return;
      }
    };

    ws.onerror = () => {};

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      wsRef.current = null;

      if (retriesRef.current < MAX_RETRIES) {
        retriesRef.current += 1;
        // eslint-disable-next-line react-hooks/immutability
        setTimeout(connect, RETRY_DELAY_MS);
      } else {
        setError(t('room.disconnect_error'));
      }
    };
  }, [roomId, token, appendMessage, addClue]);

  useEffect(() => {
    mountedRef.current = true;
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
    setDmTyping(true);
  }, []);

  const sendPrivateMessage = useCallback((text: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    setPrivateMessages((prev) => [
      ...prev,
      { type: 'private_question', text, timestamp: Date.now() / 1000 },
    ]);
    ws.send(JSON.stringify({ type: 'private_chat', text }));
  }, []);

  const sendVote = useCallback((targetCharId: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'vote', target: targetCharId }));
    setHasVoted(true);
  }, []);

  const sendSkipVote = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'skip_phase' }));
    setHasSkipVoted(true);
  }, []);

  const sendReconstructionAnswer = useCallback((answer: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'reconstruction_answer', answer }));
  }, []);

  return {
    // Shared
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
    // Turtle soup
    privateClues,
    privateMessages,
    leakWarning,
    sendPrivateMessage,
    // Murder mystery
    gameType,
    mmPhase,
    mmTimeRemaining,
    characters,
    myChar,
    voteCandidates,
    voteCount,
    voteResult,
    hasVoted,
    sendVote,
    skipVotes,
    hasSkipVoted,
    sendSkipVote,
    mmRequiredPlayers,
    mmGameMode,
    // Reconstruction
    reconstructionQuestion,
    reconstructionResults,
    reconstructionComplete,
    sendReconstructionAnswer,
    // Theme
    scriptTheme,
  };
}
