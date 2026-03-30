import { useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { CluePanel } from '../components/CluePanel';
import { PlayerList } from '../components/PlayerList';
import { PuzzleCard } from '../components/PuzzleCard';
import { HintBar } from '../components/HintBar';
import { useRoom } from '../hooks/useRoom';
import type { DmResponseMsg, InterventionMsg, PlayerMsg, RoomMessage, SystemMsg } from '../hooks/useRoom';
import type { RoomPlayer } from '../api';

// ---------------------------------------------------------------------------
// Avatar color system — deterministic from player name
// ---------------------------------------------------------------------------

const AVATAR_PALETTE = [
  { color: '#c17f3b', bg: '#fdf0dc' },
  { color: '#4a7fc1', bg: '#dceaf9' },
  { color: '#6ab04c', bg: '#e3f5d8' },
  { color: '#c14a7f', bg: '#f9dcea' },
  { color: '#7f4ac1', bg: '#ecdcf9' },
  { color: '#c1a24a', bg: '#f9f0dc' },
];

function playerColorIndex(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffff;
  return h % AVATAR_PALETTE.length;
}

function avatarStyle(name: string): React.CSSProperties {
  const p = AVATAR_PALETTE[playerColorIndex(name)];
  return { '--av-color': p.color, '--av-bg': p.bg } as React.CSSProperties;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function judgmentLabel(j: string): string {
  if (j === '是') return '✅ 是';
  if (j === '不是') return '❌ 不是';
  if (j === '部分正确') return '〽️ 部分正确';
  if (j === '无关') return '➖ 无关';
  return j;
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

// ---------------------------------------------------------------------------
// Message renderers
// ---------------------------------------------------------------------------

function SystemBubble({ msg }: { msg: SystemMsg }) {
  return (
    <div className="room-msg room-msg--system">
      <span>{msg.text}</span>
      <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
    </div>
  );
}

function PlayerBubble({ msg, isSelf }: { msg: PlayerMsg; isSelf: boolean }) {
  return (
    <div className={`room-msg room-msg--player${isSelf ? ' room-msg--self' : ''}`}>
      {!isSelf && (
        <div className="room-msg-name-row">
          <span className="player-avatar player-avatar--sm" style={avatarStyle(msg.player_name)}>
            {msg.player_name[0]}
          </span>
          <span className="room-msg-name">{msg.player_name}</span>
        </div>
      )}
      <div className="room-bubble">{msg.text}</div>
      <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
    </div>
  );
}

function InterventionBubble({ msg }: { msg: InterventionMsg }) {
  let label: string;
  if (msg.reason === 'hint') label = 'DM 💡 主动提示';
  else if (msg.reason === 'encouragement') label = 'DM 🎲 鼓励';
  else label = 'DM 💬 发话了';

  return (
    <div className="room-msg room-msg--intervention">
      <span className="room-dm-label">{label}</span>
      <span className="room-intervention-text">{msg.text}</span>
      <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
    </div>
  );
}

function DmBubble({ msg }: { msg: DmResponseMsg }) {
  return (
    <div className="room-msg room-msg--dm">
      <div className="room-dm-header">
        <span className="room-dm-label">DM</span>
        <span className="room-dm-asker">对 {msg.player_name} 的回复</span>
        <span className="room-dm-judgment">{judgmentLabel(msg.judgment)}</span>
        <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
      </div>
      <div className="room-bubble room-bubble--dm">{msg.response}</div>
      {msg.clue_unlocked && (
        <div className="room-clue-notice">
          🔍 发现新线索：{msg.clue_unlocked.title}
        </div>
      )}
      {msg.hint && (
        <div className="room-hint-notice">💡 {msg.hint}</div>
      )}
    </div>
  );
}

function DmTypingBubble() {
  return (
    <div className="room-msg room-msg--dm room-msg--typing">
      <span className="room-dm-label">DM</span>
      <span className="dm-typing-dots">
        <span /><span /><span />
      </span>
    </div>
  );
}

function MessageList({ msgs, playerName, dmTyping }: { msgs: RoomMessage[]; playerName: string; dmTyping: boolean }) {
  return (
    <>
      {msgs.map((m, i) => {
        if (m.type === 'system') return <SystemBubble key={i} msg={m} />;
        if (m.type === 'player_message')
          return <PlayerBubble key={i} msg={m} isSelf={m.player_name === playerName} />;
        if (m.type === 'dm_response') return <DmBubble key={i} msg={m} />;
        if (m.type === 'dm_intervention') return <InterventionBubble key={i} msg={m} />;
        return null;
      })}
      {dmTyping && <DmTypingBubble />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Share bar (room code + copy + mobile share)
// ---------------------------------------------------------------------------

function ShareBar({ roomId }: { roomId: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(roomId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function handleShare() {
    if (navigator.share) {
      navigator.share({ title: '加入我的海龟汤游戏', text: `房间码：${roomId}` }).catch(() => {});
    } else {
      handleCopy();
    }
  }

  return (
    <div className="room-share-bar">
      <span className="room-share-label">房间码</span>
      <span className="room-share-code">{roomId}</span>
      <button className="btn btn-ghost room-share-btn" onClick={handleShare} style={{ fontSize: 12, padding: '3px 10px' }}>
        {copied ? '✓ 已复制' : '复制邀请码'}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Waiting banner
// ---------------------------------------------------------------------------

function WaitingBanner({ connectedCount }: { connectedCount: number }) {
  if (connectedCount >= 2) return null;
  return (
    <div className="room-waiting-banner">
      ⏳ 等待玩家加入…（当前 {connectedCount} 人，至少需要 2 人开始）
    </div>
  );
}

// ---------------------------------------------------------------------------
// Multiplayer review screen (game over)
// ---------------------------------------------------------------------------

function MultiplayerReview({
  truth,
  players,
  questionsByPlayer,
  cluesByPlayer,
  onLeave,
}: {
  truth: string;
  players: RoomPlayer[];
  questionsByPlayer: Record<string, number>;
  cluesByPlayer: Record<string, number>;
  onLeave: () => void;
}) {
  // MVP = player with most clue unlocks (>0); ties broken by questions count
  let mvpName: string | null = null;
  let maxClues = 0;
  for (const p of players) {
    const c = cluesByPlayer[p.name] ?? 0;
    if (c > maxClues) { maxClues = c; mvpName = p.name; }
    else if (c === maxClues && maxClues > 0) { mvpName = null; } // tie → no MVP
  }

  return (
    <div className="mp-review-screen">
      <div className="end-celebration">
        <div className="end-emoji">🎉</div>
        <h2 className="end-title">真相大白！</h2>
      </div>

      <div className="end-section">
        <p className="end-section-label">🍜 汤底（真相）</p>
        <p className="end-truth-text">{truth}</p>
      </div>

      {players.length > 0 && (
        <div className="end-section">
          <p className="end-section-label">👥 本局战报</p>
          <div className="mp-player-stats">
            {players.map((p) => {
              const questions = questionsByPlayer[p.name] ?? 0;
              const clues = cluesByPlayer[p.name] ?? 0;
              const isMvp = mvpName === p.name;
              return (
                <div key={p.id} className="mp-player-stat-row">
                  <div className="mp-stat-avatar" style={avatarStyle(p.name)}>
                    {p.name[0]}
                  </div>
                  <span className="mp-stat-name">{p.name}</span>
                  {isMvp && <span className="mp-mvp-badge">🏆 MVP 推理王</span>}
                  <div className="mp-stat-nums">
                    <div className="mp-stat-num">
                      <div className="mp-stat-value">{questions}</div>
                      <div className="mp-stat-unit">提问</div>
                    </div>
                    <div className="mp-stat-num">
                      <div className="mp-stat-value">{clues}</div>
                      <div className="mp-stat-unit">线索</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div style={{ textAlign: 'center' }}>
        <button className="btn btn-primary" onClick={onLeave} style={{ minWidth: 140 }}>
          返回大厅
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RoomPage
// ---------------------------------------------------------------------------

export function RoomPage() {
  const { roomId = '' } = useParams<{ roomId: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  // Player name passed from LobbyPage via router state
  const playerName: string = (location.state as { playerName?: string })?.playerName ?? '';

  const {
    messages, players, clues, connected, progress, truth, puzzle, error,
    questionsByPlayer, cluesByPlayer, dmTyping, sendMessage,
  } = useRoom(roomId, playerName);

  const [input, setInput] = useState('');
  const [showCluePanel, setShowCluePanel] = useState(false);
  const cluePanelRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  function handleSend() {
    const text = input.trim();
    if (!text || !connected || !!truth) return;
    sendMessage(text);
    setInput('');
    setTimeout(scrollToBottom, 50);
  }

  if (!playerName) {
    return (
      <div className="lobby-screen" style={{ textAlign: 'center', paddingTop: 80 }}>
        <p className="error-text">缺少玩家名，请从大厅进入</p>
        <button className="btn btn-primary" onClick={() => navigate('/')}>返回大厅</button>
      </div>
    );
  }

  if (truth) {
    return (
      <MultiplayerReview
        truth={truth}
        players={players}
        questionsByPlayer={questionsByPlayer}
        cluesByPlayer={cluesByPlayer}
        onLeave={() => navigate('/')}
      />
    );
  }

  const clueCount = clues.length;
  const connectedCount = players.filter((p) => p.connected).length;

  return (
    <div className="game-screen">
      {/* Main column */}
      <div className="game-main">
        {/* Header */}
        <header className="game-header">
          <button className="btn btn-ghost" onClick={() => navigate('/')} style={{ padding: '4px 10px' }}>
            ← 返回
          </button>
          <span className="game-header-title">
            {puzzle?.title ?? '加载中…'}
            <span className="room-id-badge"> #{roomId}</span>
          </span>
          <div className="game-header-right">
            <span className={`conn-dot${connected ? ' conn-dot--on' : ''}`} title={connected ? '已连接' : '连接中…'} />
            <button
              className={`btn btn-ghost clue-toggle-btn${clueCount > 0 ? ' clue-toggle-btn--active' : ''}`}
              onClick={() => {
                setShowCluePanel((v) => !v);
                if (!showCluePanel) setTimeout(() => cluePanelRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
              }}
              aria-label="线索板"
            >
              🔍{clueCount > 0 && <span className="clue-toggle-count">{clueCount}</span>}
            </button>
          </div>
        </header>

        {/* Share bar */}
        <ShareBar roomId={roomId} />

        {error && <div className="error-text" style={{ padding: '8px 16px' }}>{error}</div>}

        {/* Puzzle surface */}
        {puzzle && <PuzzleCard title={puzzle.title} surface={puzzle.surface} />}

        {/* Waiting banner */}
        <WaitingBanner connectedCount={connectedCount} />

        {/* Mobile clue panel */}
        <div className={`clue-panel-mobile${showCluePanel ? ' clue-panel-mobile--open' : ''}`}>
          <CluePanel clues={clues} panelRef={cluePanelRef} />
        </div>

        {/* Chat messages */}
        <div className="room-chat">
          <MessageList msgs={messages} playerName={playerName} dmTyping={dmTyping} />
          <div ref={chatEndRef} />
        </div>

        {/* Input */}
        <div className="chat-input-row">
          <input
            className="chat-input"
            type="text"
            placeholder={connected ? '输入问题，按回车发送…' : '连接中…'}
            value={input}
            disabled={!connected || !!truth}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <button
            className="btn btn-primary"
            onClick={handleSend}
            disabled={!input.trim() || !connected || !!truth}
          >
            发送
          </button>
        </div>

        {/* Progress bar */}
        <div className="game-bottom">
          <HintBar hints={[]} progress={progress} />
        </div>
      </div>

      {/* Right sidebar */}
      <aside className="game-sidebar room-sidebar">
        <PlayerList players={players} currentName={playerName} />
        <CluePanel clues={clues} panelRef={cluePanelRef} />
      </aside>
    </div>
  );
}
