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
  cluePanelRef,
  showTraces = false,
}: ChatPanelProps) {
  const { t } = useT();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

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

    try {
      const res: ChatResponse = await sendMessage(sessionId, text);

      setMessages((prev) => [
        ...prev,
        { role: 'dm', text: res.response, judgment: res.judgment, trace: res.trace ?? null },
      ]);
      onProgress(res.truth_progress);

      if (res.clue_unlocked) {
        onClueUnlocked?.(res.clue_unlocked);
        setMessages((prev) => [
          ...prev,
          { role: 'clue', clueId: res.clue_unlocked!.id, clueTitle: res.clue_unlocked!.title },
        ]);
      }
      if (res.hint) onHint(res.hint);
      if (res.truth) onFinish(res.truth);
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('game.network_error');
      setError(msg);
      // Remove the optimistically added player message on error
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
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
              {m.role === 'dm' && <JudgmentBadge judgment={m.judgment} />}
              <div className="message-bubble">{m.text}</div>
              {m.role === 'dm' && showTraces && m.trace && (
                <TracePanel trace={m.trace} />
              )}
            </div>
          );
        })}

        {loading && (
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
