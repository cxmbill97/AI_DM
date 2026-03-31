import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { CluePanel } from '../components/CluePanel';
import { PlayerList } from '../components/PlayerList';
import { PuzzleCard } from '../components/PuzzleCard';
import { HintBar } from '../components/HintBar';
import { PrivateCluePanel } from '../components/PrivateCluePanel';
import { PhaseBar } from '../components/PhaseBar';
import { ScriptCard } from '../components/ScriptCard';
import { VotePanel } from '../components/VotePanel';
import { useRoom } from '../hooks/useRoom';
import type {
  CharAssignedMsg,
  ClueFoundMsg,
  DmResponseMsg,
  InterventionMsg,
  PhaseBlockedMsg,
  PhaseChangeMsg,
  PlayerMsg,
  PrivateMessage,
  RoomMessage,
  SystemMsg,
  VoteCastMsg,
  VoteResultMsg,
} from '../hooks/useRoom';
import type { RoomPlayer } from '../api';

// ---------------------------------------------------------------------------
// Avatar color system
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
  // Murder mystery mode: no judgment, just text
  const isMM = msg.text !== undefined && msg.judgment === undefined;

  if (isMM) {
    return (
      <div className="room-msg room-msg--dm">
        <div className="room-dm-header">
          <span className="room-dm-label">DM</span>
          {msg.player_name && <span className="room-dm-asker">对 {msg.player_name} 的回复</span>}
          <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
        </div>
        <div className="room-bubble room-bubble--dm">{msg.text}</div>
        {msg.clue && (
          <div className="room-clue-notice">🔍 发现新线索：{msg.clue.title}</div>
        )}
      </div>
    );
  }

  return (
    <div className="room-msg room-msg--dm">
      <div className="room-dm-header">
        <span className="room-dm-label">DM</span>
        <span className="room-dm-asker">对 {msg.player_name} 的回复</span>
        <span className="room-dm-judgment">{judgmentLabel(msg.judgment ?? '')}</span>
        <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
      </div>
      <div className="room-bubble room-bubble--dm">{msg.response}</div>
      {msg.clue_unlocked && (
        <div className="room-clue-notice">🔍 发现新线索：{msg.clue_unlocked.title}</div>
      )}
      {msg.hint && <div className="room-hint-notice">💡 {msg.hint}</div>}
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

function PhaseChangeBubble({ msg }: { msg: PhaseChangeMsg }) {
  return (
    <div className="room-msg room-msg--phase-change">
      <span className="phase-change-icon">🔔</span>
      <span className="phase-change-text">{msg.description}</span>
      <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
    </div>
  );
}

function CharAssignedBubble({ msg }: { msg: CharAssignedMsg }) {
  return (
    <div className="room-msg room-msg--system">
      <span>🎭 {msg.player_name} 扮演 <strong>{msg.char_name}</strong></span>
      <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
    </div>
  );
}

function ClueFoundBubble({ msg }: { msg: ClueFoundMsg }) {
  return (
    <div className="room-msg room-msg--clue-found">
      <span className="clue-found-icon">🔍</span>
      <span>{msg.text}</span>
      {msg.clue && <strong className="clue-found-title"> {msg.clue.title}</strong>}
      <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
    </div>
  );
}

function VoteCastBubble({ msg }: { msg: VoteCastMsg }) {
  return (
    <div className="room-msg room-msg--system">
      <span>🗳 {msg.text} ({msg.count}/{msg.total})</span>
      <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
    </div>
  );
}

function VoteResultBubble({ msg }: { msg: VoteResultMsg }) {
  return (
    <div className="room-msg room-msg--dm">
      <div className="room-bubble room-bubble--dm">{msg.text}</div>
      <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
    </div>
  );
}

function PhaseBlockedBubble({ msg }: { msg: PhaseBlockedMsg }) {
  return (
    <div className="room-msg room-msg--phase-blocked">
      <span>⛔ {msg.text}</span>
      <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
    </div>
  );
}

function MessageList({ msgs, playerName, dmTyping }: { msgs: RoomMessage[]; playerName: string; dmTyping: boolean }) {
  return (
    <>
      {msgs.map((m, i) => {
        if (m.type === 'system') return <SystemBubble key={i} msg={m} />;
        if (m.type === 'player_message') return <PlayerBubble key={i} msg={m} isSelf={m.player_name === playerName} />;
        if (m.type === 'dm_response') return <DmBubble key={i} msg={m} />;
        if (m.type === 'dm_intervention') return <InterventionBubble key={i} msg={m} />;
        if (m.type === 'phase_change') return <PhaseChangeBubble key={i} msg={m} />;
        if (m.type === 'character_assigned') return <CharAssignedBubble key={i} msg={m} />;
        if (m.type === 'clue_found') return <ClueFoundBubble key={i} msg={m} />;
        if (m.type === 'vote_cast') return <VoteCastBubble key={i} msg={m} />;
        if (m.type === 'vote_result') return <VoteResultBubble key={i} msg={m} />;
        if (m.type === 'phase_blocked') return <PhaseBlockedBubble key={i} msg={m} />;
        return null;
      })}
      {dmTyping && <DmTypingBubble />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Private chat area (turtle soup only)
// ---------------------------------------------------------------------------

function PrivateChatArea({ msgs, dmTyping }: { msgs: PrivateMessage[]; dmTyping: boolean }) {
  return (
    <>
      {msgs.length === 0 && (
        <div className="room-private-empty">
          向DM私密提问，其他玩家不会看到你们的对话
        </div>
      )}
      {msgs.map((m, i) => {
        if (m.type === 'private_question') {
          return (
            <div key={i} className="room-msg room-msg--private-q">
              <div className="room-bubble room-bubble--private">{m.text}</div>
              <span className="private-badge">私密提问</span>
              <span className="room-msg-time">{formatTime(m.timestamp)}</span>
            </div>
          );
        }
        return (
          <div key={i} className="room-msg room-msg--dm room-msg--private-dm">
            <div className="room-dm-header">
              <span className="room-dm-label">DM</span>
              <span className="private-badge">🔒 仅你可见</span>
              <span className="room-msg-time" style={{ marginLeft: 'auto' }}>{formatTime(m.timestamp)}</span>
            </div>
            <div className="room-bubble room-bubble--dm">{m.response}</div>
          </div>
        );
      })}
      {dmTyping && <DmTypingBubble />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Intro modal
// ---------------------------------------------------------------------------

function IntroModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-icon">🔐</div>
        <h3 className="modal-title">信息不对等游戏</h3>
        <p className="modal-body">
          每位玩家持有不同的秘密线索。<br />
          你可以用自己的话描述你知道的内容，<br />
          但不能直接展示原始线索文字。<br />
          合作拼出完整真相即可获胜！
        </p>
        <button className="btn btn-primary" onClick={onClose} style={{ width: '100%' }}>
          知道了，开始游戏
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Share bar
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
// Multiplayer review screen (turtle soup game over)
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
  let mvpName: string | null = null;
  let maxClues = 0;
  for (const p of players) {
    const c = cluesByPlayer[p.name] ?? 0;
    if (c > maxClues) { maxClues = c; mvpName = p.name; }
    else if (c === maxClues && maxClues > 0) { mvpName = null; }
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

  const playerName: string = (location.state as { playerName?: string })?.playerName ?? '';

  const {
    messages, players, clues, connected, progress, truth, puzzle, error,
    questionsByPlayer, cluesByPlayer, dmTyping, sendMessage,
    privateClues, privateMessages, leakWarning, sendPrivateMessage,
    // Murder mystery
    gameType, mmPhase, mmTimeRemaining, characters, myChar,
    voteCandidates, voteCount, voteResult, hasVoted, sendVote,
  } = useRoom(roomId, playerName);

  const [input, setInput] = useState('');
  const [showCluePanel, setShowCluePanel] = useState(false);
  const cluePanelRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Turtle soup private chat state
  const [chatMode, setChatMode] = useState<'public' | 'private'>('public');
  const [privateInput, setPrivateInput] = useState('');
  const [showPrivatePanel, setShowPrivatePanel] = useState(false);
  const [showIntroModal, setShowIntroModal] = useState(false);
  const hasShownIntroRef = useRef(false);
  const privateEndRef = useRef<HTMLDivElement>(null);
  const privatePanelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (privateClues.length > 0 && !hasShownIntroRef.current) {
      hasShownIntroRef.current = true;
      setShowIntroModal(true);
    }
  }, [privateClues.length]);

  const scrollToBottom = () => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  function handleSend() {
    const text = input.trim();
    if (!text || !connected || !!truth) return;
    sendMessage(text);
    setInput('');
    setTimeout(scrollToBottom, 50);
  }

  function handlePrivateSend() {
    const text = privateInput.trim();
    if (!text || !connected || !!truth) return;
    sendPrivateMessage(text);
    setPrivateInput('');
    setTimeout(() => privateEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }

  if (!playerName) {
    return (
      <div className="lobby-screen" style={{ textAlign: 'center', paddingTop: 80 }}>
        <p className="error-text">缺少玩家名，请从大厅进入</p>
        <button className="btn btn-primary" onClick={() => navigate('/')}>返回大厅</button>
      </div>
    );
  }

  // Turtle soup game over
  if (gameType === 'turtle_soup' && truth) {
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

  // -------------------------------------------------------------------------
  // Murder mystery layout
  // -------------------------------------------------------------------------

  if (gameType === 'murder_mystery') {
    const activePhase = mmPhase ?? 'opening';
    const isVoting = activePhase === 'voting';
    const isReveal = activePhase === 'reveal';

    // Build vote candidate list from characters
    const voteList = voteCandidates ?? characters;
    // Map winner char_id to name for VotePanel
    const voteResultForPanel = voteResult
      ? {
          winner: voteResult.winner,
          winner_name: voteResult.winner !== null
            ? (characters.find((c) => c.id === voteResult.winner)?.name ?? voteResult.winner)
            : null,
          is_correct: voteResult.is_correct,
          vote_counts: voteResult.tally,
          runoff: voteResult.status === 'runoff' || voteResult.status === 'runoff_tie',
        }
      : null;

    return (
      <div className="mm-screen">
        {showIntroModal && <IntroModal onClose={() => setShowIntroModal(false)} />}

        {/* Top: phase bar */}
        <div className="mm-phase-strip">
          <div className="mm-phase-strip-inner">
            <button className="btn btn-ghost mm-back-btn" onClick={() => navigate('/')} style={{ padding: '4px 10px' }}>
              ← 返回
            </button>
            <PhaseBar phase={activePhase} timeRemaining={mmTimeRemaining} />
            <div className="mm-conn-area">
              <span className="room-share-code" style={{ fontSize: 12 }}>#{roomId}</span>
              <span className={`conn-dot${connected ? ' conn-dot--on' : ''}`} />
            </div>
          </div>
        </div>

        {error && <div className="error-text mm-error">{error}</div>}

        {/* Body: three-column */}
        <div className="mm-body">
          {/* Left: script card */}
          <aside className="mm-left">
            {myChar ? (
              <ScriptCard
                charName={myChar.char_name}
                publicBio={
                  characters.find((c) => c.id === myChar.char_id)?.public_bio ?? ''
                }
                secretBio={myChar.secret_bio}
                personalScript={myChar.personal_script ?? undefined}
                phase={activePhase}
              />
            ) : (
              <div className="mm-no-char">
                <div className="mm-no-char-icon">🎭</div>
                <div>等待分配角色</div>
              </div>
            )}
            <PlayerList players={players} currentName={playerName} />
          </aside>

          {/* Center: chat */}
          <div className="mm-center">
            <WaitingBanner connectedCount={connectedCount} />
            <div className="room-chat mm-chat">
              <MessageList msgs={messages} playerName={playerName} dmTyping={dmTyping} />
              <div ref={chatEndRef} />
            </div>
            <div className="chat-input-row">
              <input
                className="chat-input"
                type="text"
                placeholder={
                  !connected ? '连接中…'
                  : isReveal ? '游戏已结束'
                  : isVoting ? '投票阶段，请在右侧投票'
                  : '输入消息，按回车发送…'
                }
                value={input}
                disabled={!connected || isReveal || isVoting}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
                }}
              />
              <button
                className="btn btn-primary"
                onClick={handleSend}
                disabled={!input.trim() || !connected || isReveal || isVoting}
              >
                发送
              </button>
            </div>
          </div>

          {/* Right: clues + vote */}
          <aside className="mm-right">
            <CluePanel clues={clues} panelRef={cluePanelRef} />
            <VotePanel
              phase={activePhase}
              candidates={voteList}
              hasVoted={hasVoted}
              voteResult={voteResultForPanel}
              onVote={sendVote}
              voteCount={voteCount?.count ?? 0}
              totalPlayers={players.length}
            />
            {isReveal && (
              <div style={{ textAlign: 'center', marginTop: 16 }}>
                <button className="btn btn-primary" onClick={() => navigate('/')}>
                  返回大厅
                </button>
              </div>
            )}
          </aside>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Turtle soup layout (unchanged)
  // -------------------------------------------------------------------------

  return (
    <div className="game-screen">
      {showIntroModal && <IntroModal onClose={() => setShowIntroModal(false)} />}

      <div className="game-main">
        <header className="game-header">
          <button className="btn btn-ghost" onClick={() => navigate('/')} style={{ padding: '4px 10px' }}>
            ← 返回
          </button>
          <span className="game-header-title">
            {puzzle?.title ?? '加载中…'}
            <span className="room-id-badge"> #{roomId}</span>
          </span>
          <div className="game-header-right">
            <span className={`conn-dot${connected ? ' conn-dot--on' : ''}`} />
            {privateClues.length > 0 && (
              <button
                className={`btn btn-ghost clue-toggle-btn${showPrivatePanel ? ' clue-toggle-btn--active' : ''}`}
                onClick={() => setShowPrivatePanel((v) => !v)}
                style={{ color: showPrivatePanel ? '#6b4fa8' : undefined }}
              >
                🔐{showPrivatePanel && <span className="clue-toggle-count" style={{ background: '#6b4fa8' }}>{privateClues.length}</span>}
              </button>
            )}
            <button
              className={`btn btn-ghost clue-toggle-btn${clueCount > 0 ? ' clue-toggle-btn--active' : ''}`}
              onClick={() => {
                setShowCluePanel((v) => !v);
                if (!showCluePanel) setTimeout(() => cluePanelRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
              }}
            >
              🔍{clueCount > 0 && <span className="clue-toggle-count">{clueCount}</span>}
            </button>
          </div>
        </header>

        <ShareBar roomId={roomId} />
        {error && <div className="error-text" style={{ padding: '8px 16px' }}>{error}</div>}
        {puzzle && <PuzzleCard title={puzzle.title} surface={puzzle.surface} />}
        <WaitingBanner connectedCount={connectedCount} />

        {privateClues.length > 0 && (
          <div className={`clue-panel-mobile${showPrivatePanel ? ' clue-panel-mobile--open' : ''}`}>
            <PrivateCluePanel clues={privateClues} panelRef={privatePanelRef} />
          </div>
        )}
        <div className={`clue-panel-mobile${showCluePanel ? ' clue-panel-mobile--open' : ''}`}>
          <CluePanel clues={clues} panelRef={cluePanelRef} />
        </div>

        {privateClues.length > 0 && (
          <div className="chat-mode-tabs">
            <button
              className={`chat-mode-tab${chatMode === 'public' ? ' chat-mode-tab--active' : ''}`}
              onClick={() => setChatMode('public')}
            >
              公聊
            </button>
            <button
              className={`chat-mode-tab${chatMode === 'private' ? ' chat-mode-tab--active chat-mode-tab--private' : ''}`}
              onClick={() => setChatMode('private')}
              disabled={!privateClues.length}
            >
              🔒 私聊DM
            </button>
          </div>
        )}

        <div className="room-chat">
          {chatMode === 'public' ? (
            <>
              <MessageList msgs={messages} playerName={playerName} dmTyping={dmTyping} />
              <div ref={chatEndRef} />
            </>
          ) : (
            <>
              <PrivateChatArea msgs={privateMessages} dmTyping={dmTyping} />
              <div ref={privateEndRef} />
            </>
          )}
        </div>

        {leakWarning && <div className="leak-warning">⚠️ {leakWarning}</div>}

        <div className="chat-input-row">
          {chatMode === 'public' ? (
            <>
              <input
                className="chat-input"
                type="text"
                placeholder={connected ? '输入问题，按回车发送…' : '连接中…'}
                value={input}
                disabled={!connected || !!truth}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
                }}
              />
              <button className="btn btn-primary" onClick={handleSend} disabled={!input.trim() || !connected || !!truth}>
                发送
              </button>
            </>
          ) : (
            <>
              <input
                className="chat-input chat-input--private"
                type="text"
                placeholder="向DM私密提问，其他玩家看不到…"
                value={privateInput}
                disabled={!connected || !!truth}
                onChange={(e) => setPrivateInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handlePrivateSend(); }
                }}
              />
              <button
                className="btn btn-primary"
                onClick={handlePrivateSend}
                disabled={!privateInput.trim() || !connected || !!truth}
                style={{ background: '#6b4fa8', borderColor: '#6b4fa8' }}
              >
                私聊
              </button>
            </>
          )}
        </div>

        <div className="game-bottom">
          <HintBar hints={[]} progress={progress} />
        </div>
      </div>

      <aside className="game-sidebar room-sidebar">
        {privateClues.length > 0 && <PrivateCluePanel clues={privateClues} />}
        <PlayerList players={players} currentName={playerName} />
        <CluePanel clues={clues} panelRef={cluePanelRef} />
      </aside>
    </div>
  );
}
