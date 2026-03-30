import { useEffect, useRef, useState } from 'react';
import { sendMessage } from '../api';
import type { ChatResponse, Clue } from '../api';

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

const BADGE: Record<string, { label: string; cls: string }> = {
  '是':    { label: '是 ✓',    cls: 'badge--yes' },
  '不是':  { label: '不是 ✗',  cls: 'badge--no' },
  '无关':  { label: '无关 —',  cls: 'badge--na' },
  '部分正确': { label: '部分正确 △', cls: 'badge--partial' },
};

function JudgmentBadge({ judgment }: { judgment: string }) {
  const cfg = BADGE[judgment] ?? { label: judgment, cls: 'badge--na' };
  return (
    <span className={`judgment-badge ${cfg.cls}`}>{cfg.label}</span>
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
  cluePanelRef?: React.RefObject<HTMLDivElement>;
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
}: ChatPanelProps) {
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
        { role: 'dm', text: res.response, judgment: res.judgment },
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
      const msg = err instanceof Error ? err.message : '网络错误，请重试';
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
            向AI裁判提问吧！提出是非问题来推断故事的真相。
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
                  🔍 你发现了新线索：<strong>{m.clueTitle}</strong>
                </button>
              </div>
            );
          }
          return (
            <div key={i} className={`message message--${m.role}`}>
              {m.role === 'dm' && <JudgmentBadge judgment={m.judgment} />}
              <div className="message-bubble">{m.text}</div>
            </div>
          );
        })}

        {loading && (
          <div className="message message--dm">
            <div className="dm-thinking">裁判思考中…</div>
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
          placeholder={disabled ? '游戏已结束' : '提出是非问题，例如：男人是故意的吗？'}
          disabled={loading || disabled}
          maxLength={200}
          autoComplete="off"
        />
        <button
          className="btn btn-primary"
          onClick={handleSend}
          disabled={loading || disabled || !input.trim()}
        >
          发送
        </button>
      </div>
    </div>
  );
}
