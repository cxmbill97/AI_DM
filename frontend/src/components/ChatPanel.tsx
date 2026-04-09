import { useEffect, useRef, useState } from 'react';
import { sendMessage } from '../api';
import type { AgentTrace, ChatResponse, Clue } from '../api';
import { TracePanel } from './TracePanel';
import { useT } from '../i18n';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PlayerMessage {
  role: 'player';
  text: string;
}

interface DMMessage {
  role: 'dm';
  text: string;
  judgment: string;
  trace?: AgentTrace | null;
  streaming?: boolean;
  streamId?: string;
}

interface ClueNoticeMessage {
  role: 'clue';
  clueId: string;
  clueTitle: string;
}

type Message = PlayerMessage | DMMessage | ClueNoticeMessage;

// ---------------------------------------------------------------------------
// Judgment badge config
// ---------------------------------------------------------------------------

const BADGE_CLS: Record<string, string> = {
  '是': 'badge--yes', '不是': 'badge--no', '无关': 'badge--na', '部分正确': 'badge--partial',
  'Yes': 'badge--yes', 'No': 'badge--no', 'Irrelevant': 'badge--na', 'Partially correct': 'badge--partial',
};
const BADGE_KEY: Record<string, string> = {
  '是': 'judgment.yes', '不是': 'judgment.no', '无关': 'judgment.irrelevant', '部分正确': 'judgment.partial',
  'Yes': 'judgment.yes', 'No': 'judgment.no', 'Irrelevant': 'judgment.irrelevant', 'Partially correct': 'judgment.partial',
};

function JudgmentBadge({ judgment }: { judgment: string }) {
  const { t } = useT();
  const cls = BADGE_CLS[judgment] ?? 'badge--na';
  const label = BADGE_KEY[judgment] ? t(BADGE_KEY[judgment]) : judgment;
  return (
    <span className={`judgment-badge ${cls}`}>{label}</span>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ChatPanelProps {
  sessionId: string;
  disabled: boolean;
  onHint: (hint: string) => void;
  onProgress: (progress: number) => void;
  onFinish: (truth: string) => void;
  onQuestionAsked: () => void;
  onClueUnlocked?: (clue: Clue) => void;
  onDmResponse?: (text: string) => void;
  cluePanelRef?: React.RefObject<HTMLDivElement | null>;
  showTraces?: boolean;
}

export function ChatPanel({
  sessionId,
  disabled,
  onHint,
  onProgress,
  onFinish,
  onQuestionAsked,
  onClueUnlocked,
  onDmResponse,
  cluePanelRef,
  showTraces = false,
}: ChatPanelProps) {
  const { t } = useT();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamingIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, loading]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading || disabled) return;

    setInput('');
    setError(null);
    setLoading(true);
    setMessages((prev) => [...prev, { role: 'player', text }]);
    onQuestionAsked();

    // Insert streaming placeholder bubble
    const sid = crypto.randomUUID();
    streamingIdRef.current = sid;
    setMessages((prev) => [...prev, { role: 'dm', text: '', judgment: '', streaming: true, streamId: sid }]);

    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;

    let fullText = '';

    try {
      const resp = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: text }),
        signal: abort.signal,
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') break;

          let payload: Record<string, unknown>;
          try { payload = JSON.parse(raw) as Record<string, unknown>; }
          catch { continue; }

          if (payload.event === 'chunk') {
            fullText += payload.text as string;
            const snapshot = fullText;
            // Yield to event loop so React flushes and browser paints between chunks
            await new Promise<void>((r) => setTimeout(r, 0));
            setMessages((prev) =>
              prev.map((m) =>
                m.role === 'dm' && (m as DMMessage).streamId === sid
                  ? { ...m, text: snapshot }
                  : m,
              ),
            );
          } else if (payload.event === 'end') {
            const judgment = payload.judgment as string;
            setMessages((prev) =>
              prev.map((m) =>
                m.role === 'dm' && (m as DMMessage).streamId === sid
                  ? { ...m, judgment, streaming: false }
                  : m,
              ),
            );
            streamingIdRef.current = null;
            // Trigger TTS only now — text is complete, voice and display are aligned
            onDmResponse?.(fullText);
            onProgress(payload.truth_progress as number);
            const clue = payload.clue_unlocked as Clue | null | undefined;
            if (clue) {
              onClueUnlocked?.(clue);
              setMessages((prev) => [...prev, { role: 'clue', clueId: clue.id, clueTitle: clue.title }]);
            }
            if (payload.hint) onHint(payload.hint as string);
            if (payload.truth) onFinish(payload.truth as string);
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : t('game.network_error');
      setError(msg);
      // Remove the streaming placeholder + player message on error
      setMessages((prev) => prev.filter((m) => !(m.role === 'dm' && (m as DMMessage).streamId === sid)).slice(0, -1));
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="chat-panel">
      {/* Message list */}
      <div className="message-list">
        {messages.length === 0 && (
          <p className="chat-empty">
            {t('game.chat_empty')}
          </p>
        )}

        {messages.map((m, i) => {
          if (m.role === 'clue') {
            return (
              <div key={i} className="message message--clue">
                <button
                  className="clue-notice"
                  onClick={() =>
                    cluePanelRef?.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                  }
                >
                  {t('game.new_clue_notice')}<strong>{m.clueTitle}</strong>
                </button>
              </div>
            );
          }
          return (
            <div key={i} className={`message message--${m.role}`}>
              {m.role === 'dm' && !m.streaming && <JudgmentBadge judgment={m.judgment} />}
              <div className={`message-bubble${m.role === 'dm' && m.streaming ? ' message-bubble--streaming' : ''}`}>
                {m.text}
                {m.role === 'dm' && m.streaming && <span className="dm-cursor" aria-hidden="true" />}
              </div>
              {m.role === 'dm' && !m.streaming && showTraces && m.trace && (
                <TracePanel trace={m.trace} />
              )}
            </div>
          );
        })}

        {loading && !streamingIdRef.current && (
          <div className="message message--dm">
            <div className="dm-thinking">{t('game.judge_thinking')}</div>
          </div>
        )}

        {error && (
          <div className="chat-error">⚠️ {error}</div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input row */}
      <div className="chat-input-row">
        <input
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? t('game.game_over_placeholder') : t('game.ask_placeholder')}
          disabled={loading || disabled}
          maxLength={200}
          autoComplete="off"
        />
        <button
          className="btn btn-primary"
          onClick={handleSend}
          disabled={loading || disabled || !input.trim()}
        >
          {t('game.send')}
        </button>
      </div>
    </div>
  );
}
