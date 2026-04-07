import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../auth';
import { CluePanel } from '../components/CluePanel';
import { PlayerList } from '../components/PlayerList';
import { PuzzleCard } from '../components/PuzzleCard';
import { HintBar } from '../components/HintBar';
import { PrivateCluePanel } from '../components/PrivateCluePanel';
import { PhaseBar } from '../components/PhaseBar';
import { ReconstructionPanel } from '../components/ReconstructionPanel';
import { ScriptCard } from '../components/ScriptCard';
import { TraceFeed } from '../components/TraceFeed';
import { TracePanel } from '../components/TracePanel';
import { VotePanel } from '../components/VotePanel';
import { LanguageToggle } from '../components/LanguageToggle';
import { useRoom } from '../hooks/useRoom';
import { useTraceSetting } from '../hooks/useTraceSetting';
import { useT } from '../i18n';
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
  { color: '#c4a35a', bg: '#2a2010' },
  { color: '#60a5fa', bg: '#0d1a2e' },
  { color: '#4ade80', bg: '#0a1f12' },
  { color: '#f472b6', bg: '#2a0d1a' },
  { color: '#a78bfa', bg: '#160d2a' },
  { color: '#fb923c', bg: '#2a1200' },
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

const JUDGMENT_KEY: Record<string, string> = {
  '是': 'judgment.yes',
  '不是': 'judgment.no',
  '部分正确': 'judgment.partial',
  '无关': 'judgment.irrelevant',
  'Yes': 'judgment.yes',
  'No': 'judgment.no',
  'Partially correct': 'judgment.partial',
  'Irrelevant': 'judgment.irrelevant',
};

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
  const { t } = useT();
  let label: string;
  if (msg.reason === 'hint') label = t('dm.hint_label');
  else if (msg.reason === 'encouragement') label = t('dm.encourage_label');
  else label = t('dm.note_label');

  return (
    <div className="room-msg room-msg--intervention">
      <span className="room-dm-label">{label}</span>
      <span className="room-intervention-text">{msg.text}</span>
      <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
    </div>
  );
}

// Gradually reveal text character-by-character regardless of chunk size.
// This makes streaming feel smooth even when the LLM returns large chunks.
function StreamingText({ fullText, isStreaming }: { fullText: string; isStreaming: boolean }) {
  const [displayed, setDisplayed] = useState(0);
  const fullTextRef = useRef(fullText);

  // Keep ref in sync with latest text without restarting the interval
  useEffect(() => {
    fullTextRef.current = fullText;
  });

  useEffect(() => {
    const id = setInterval(() => {
      setDisplayed((prev) => {
        const target = fullTextRef.current.length;
        if (prev >= target) return prev;
        return Math.min(prev + 4, target); // ~4 chars per 25ms ≈ 160 chars/sec
      });
    }, 25);
    return () => clearInterval(id);
  }, []); // single interval for the lifetime of this component

  const shown = fullText.slice(0, displayed);
  const showCursor = isStreaming || displayed < fullText.length;
  return (
    <>
      {shown}
      {showCursor && <span className="dm-stream-cursor" />}
    </>
  );
}

function DmBubble({ msg, showTraces }: { msg: DmResponseMsg; showTraces: boolean }) {
  const { t } = useT();
  // Streaming MM message (judgment visible, text accumulating)
  const isStreaming = msg.streaming === true;
  // Murder mystery mode: text field present
  const isMM = msg.text !== undefined || isStreaming;

  if (isMM) {
    const judgmentKey = JUDGMENT_KEY[msg.judgment ?? ''];
    return (
      <div className="room-msg room-msg--dm">
        <div className="room-dm-header">
          <span className="room-dm-label">DM</span>
          {msg.player_name && <span className="room-dm-asker">{t('dm.reply_to', { name: msg.player_name })}</span>}
          {msg.judgment && (
            <span className="room-dm-judgment">
              {judgmentKey ? t(judgmentKey) : msg.judgment}
            </span>
          )}
          <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
        </div>
        <div className="room-bubble room-bubble--dm">
          <StreamingText fullText={msg.text ?? ''} isStreaming={isStreaming} />
        </div>
        {!isStreaming && msg.clue && (
          <div className="room-clue-notice">{t('dm.new_clue')}{msg.clue.title}</div>
        )}
        {!isStreaming && showTraces && msg.trace && <TracePanel trace={msg.trace} />}
      </div>
    );
  }

  return (
    <div className="room-msg room-msg--dm">
      <div className="room-dm-header">
        <span className="room-dm-label">DM</span>
        <span className="room-dm-asker">{t('dm.reply_to', { name: msg.player_name ?? '' })}</span>
        <span className="room-dm-judgment">{JUDGMENT_KEY[msg.judgment ?? ''] ? t(JUDGMENT_KEY[msg.judgment ?? '']) : (msg.judgment ?? '')}</span>
        <span className="room-msg-time">{formatTime(msg.timestamp)}</span>
      </div>
      <div className="room-bubble room-bubble--dm">{msg.response}</div>
      {msg.clue_unlocked && (
        <div className="room-clue-notice">{t('dm.new_clue')}{msg.clue_unlocked.title}</div>
      )}
      {msg.hint && <div className="room-hint-notice">💡 {msg.hint}</div>}
      {showTraces && msg.trace && <TracePanel trace={msg.trace} />}
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
  const { t } = useT();
  return (
    <div className="room-msg room-msg--system">
      <span>{t('mm.char_plays', { player: msg.player_name, char: msg.char_name })}</span>
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

function MessageList({ msgs, playerName, dmTyping, showTraces }: {
  msgs: RoomMessage[];
  playerName: string;
  dmTyping: boolean;
  showTraces: boolean;
}) {
  return (
    <>
      {msgs.map((m, i) => {
        const key = m.type === 'dm_response' && (m as DmResponseMsg).streamId
          ? (m as DmResponseMsg).streamId!
          : i;
        if (m.type === 'system') return <SystemBubble key={key} msg={m} />;
        if (m.type === 'player_message') return <PlayerBubble key={key} msg={m} isSelf={m.player_name === playerName} />;
        if (m.type === 'dm_response') return <DmBubble key={key} msg={m} showTraces={showTraces} />;
        if (m.type === 'dm_intervention') return <InterventionBubble key={key} msg={m} />;
        if (m.type === 'phase_change') return <PhaseChangeBubble key={key} msg={m} />;
        if (m.type === 'character_assigned') return <CharAssignedBubble key={key} msg={m} />;
        if (m.type === 'clue_found') return <ClueFoundBubble key={key} msg={m} />;
        if (m.type === 'vote_cast') return <VoteCastBubble key={key} msg={m} />;
        if (m.type === 'vote_result') return <VoteResultBubble key={key} msg={m} />;
        if (m.type === 'phase_blocked') return <PhaseBlockedBubble key={key} msg={m} />;
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
  const { t } = useT();
  return (
    <>
      {msgs.length === 0 && (
        <div className="room-private-empty">
          {t('room.private_empty')}
        </div>
      )}
      {msgs.map((m, i) => {
        if (m.type === 'private_question') {
          return (
            <div key={i} className="room-msg room-msg--private-q">
              <div className="room-bubble room-bubble--private">{m.text}</div>
              <span className="private-badge">{t('room.private_question_badge')}</span>
              <span className="room-msg-time">{formatTime(m.timestamp)}</span>
            </div>
          );
        }
        return (
          <div key={i} className="room-msg room-msg--dm room-msg--private-dm">
            <div className="room-dm-header">
              <span className="room-dm-label">DM</span>
              <span className="private-badge">{t('room.private_dm_badge')}</span>
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
  const { t } = useT();
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-icon">🔐</div>
        <h3 className="modal-title">{t('room.intro_title')}</h3>
        <p className="modal-body" style={{ whiteSpace: 'pre-line' }}>
          {t('room.intro_body')}
        </p>
        <button className="btn btn-primary" onClick={onClose} style={{ width: '100%' }}>
          {t('room.intro_ok')}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Share bar
// ---------------------------------------------------------------------------

function ShareBar({ roomId }: { roomId: string }) {
  const { t } = useT();
  const [copied, setCopied] = useState(false);

  // Build the full invite URL using the current host — works on both localhost
  // and LAN IPs (e.g. http://192.168.1.42:5173/room/ABC123).
  const inviteUrl = `${window.location.protocol}//${window.location.host}/room/${roomId}`;

  function handleCopy() {
    navigator.clipboard.writeText(inviteUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function handleShare() {
    if (navigator.share) {
      navigator.share({ title: '加入我的游戏', url: inviteUrl }).catch(() => {});
    } else {
      handleCopy();
    }
  }

  return (
    <div className="room-share-bar">
      <span className="room-share-label">{t('room.code_label')}</span>
      <span className="room-share-code">{roomId}</span>
      <span className="room-share-url">{inviteUrl}</span>
      <button className="btn btn-ghost room-share-btn" onClick={handleShare} style={{ fontSize: 12, padding: '3px 10px' }}>
        {copied ? t('room.copied') : t('room.copy_invite')}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Waiting banner
// ---------------------------------------------------------------------------

function WaitingBanner({ connectedCount, requiredPlayers = 2 }: { connectedCount: number; requiredPlayers?: number }) {
  const { t } = useT();
  if (connectedCount >= requiredPlayers) return null;
  return (
    <div className="room-waiting-banner">
      {t('room.waiting_banner', { n: connectedCount })}
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

  const { t } = useT();

  return (
    <div className="mp-review-screen">
      <div className="end-celebration">
        <div className="end-emoji">🎉</div>
        <h2 className="end-title">{t('room.review_title')}</h2>
      </div>

      <div className="end-section">
        <p className="end-section-label">{t('room.review_truth')}</p>
        <p className="end-truth-text">{truth}</p>
      </div>

      {players.length > 0 && (
        <div className="end-section">
          <p className="end-section-label">{t('room.review_scoreboard')}</p>
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
                  {isMvp && <span className="mp-mvp-badge">{t('room.mvp')}</span>}
                  <div className="mp-stat-nums">
                    <div className="mp-stat-num">
                      <div className="mp-stat-value">{questions}</div>
                      <div className="mp-stat-unit">{t('room.stat_questions')}</div>
                    </div>
                    <div className="mp-stat-num">
                      <div className="mp-stat-value">{clues}</div>
                      <div className="mp-stat-unit">{t('room.stat_clues')}</div>
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
          {t('room.back_lobby')}
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
  const navigate = useNavigate();
  const { user } = useAuth();
  const token = localStorage.getItem('ai_dm_token') ?? '';
  const playerName = user?.name ?? '';

  const {
    messages, players, clues, connected, progress, truth, puzzle, error,
    questionsByPlayer, cluesByPlayer, dmTyping, sendMessage,
    privateClues, privateMessages, leakWarning, sendPrivateMessage,
    // Murder mystery
    gameType, mmPhase, mmTimeRemaining, characters, myChar,
    voteCandidates, voteCount, voteResult, hasVoted, sendVote,
    skipVotes, hasSkipVoted, sendSkipVote,
    mmRequiredPlayers, mmGameMode,
    reconstructionQuestion, reconstructionResults, reconstructionComplete, sendReconstructionAnswer,
    scriptTheme,
  } = useRoom(roomId, token);

  const { t } = useT();
  const { showTraces, toggleTraces } = useTraceSetting();
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
      // eslint-disable-next-line react-hooks/set-state-in-effect
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
        <p className="error-text">{t('room.no_player_name')}</p>
        <button className="btn btn-primary" onClick={() => navigate('/')}>{t('room.back_lobby')}</button>
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
    const isReconstruction = activePhase === 'reconstruction';
    const isListenOnly = activePhase === 'opening' || activePhase === 'reading';

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

    const themeStyle = scriptTheme
      ? ({
          '--theme-primary': scriptTheme.primary_color,
          '--theme-bg': scriptTheme.bg_tone === 'warm' ? '#1a1208' : scriptTheme.bg_tone === 'eerie' ? '#0a0f0a' : scriptTheme.bg_tone === 'cold' ? '#080d14' : scriptTheme.bg_tone === 'natural' ? '#0d1208' : '#0e0c18',
        } as React.CSSProperties)
      : {};

    return (
      <div className="mm-screen" style={themeStyle}>
        {showIntroModal && <IntroModal onClose={() => setShowIntroModal(false)} />}

        {/* Top: phase bar */}
        <div className="mm-phase-strip">
          <div className="mm-phase-strip-inner">
            <button className="btn btn-ghost mm-back-btn" onClick={() => navigate('/')} style={{ padding: '4px 10px' }}>
              {t('game.back')}
            </button>
            <PhaseBar
              phase={activePhase}
              timeRemaining={mmTimeRemaining}
              skipVotes={skipVotes}
              hasSkipVoted={hasSkipVoted}
              onSkip={sendSkipVote}
              gameMode={mmGameMode}
            />
            <div className="mm-conn-area">
              <LanguageToggle />
              <button
                className={`btn btn-ghost trace-setting-btn${showTraces ? ' trace-setting-btn--on' : ''}`}
                onClick={toggleTraces}
                title={showTraces ? 'Hide agent traces' : 'Show agent traces'}
              >
                ⚡
              </button>
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
                <div>{t('mm.no_char')}</div>
              </div>
            )}
            <PlayerList players={players} currentName={playerName} />
          </aside>

          {/* Center: chat */}
          <div className="mm-center">
            <WaitingBanner connectedCount={connectedCount} requiredPlayers={mmRequiredPlayers} />
            <div className="room-chat mm-chat">
              <MessageList msgs={messages} playerName={playerName} dmTyping={dmTyping} showTraces={showTraces} />
              <div ref={chatEndRef} />
            </div>
            <div className="chat-input-row">
              <input
                className="chat-input"
                type="text"
                placeholder={
                  !connected ? t('room.input_connecting')
                  : isReveal ? t('mm.end_placeholder')
                  : isVoting ? t('mm.voting_placeholder')
                  : isListenOnly ? t('mm.listen_placeholder')
                  : t('mm.chat_placeholder')
                }
                value={input}
                disabled={!connected || isReveal || isVoting || isListenOnly}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
                }}
              />
              <button
                className="btn btn-primary"
                onClick={handleSend}
                disabled={!input.trim() || !connected || isReveal || isVoting || isListenOnly}
              >
                {t('game.send')}
              </button>
            </div>
            {isReconstruction && (
              <div style={{ padding: '6px 8px', fontSize: 12, color: 'var(--text-dim)', textAlign: 'center' }}>
                {t('reconstruction.chat_hint')}
              </div>
            )}
          </div>

          {/* Right: clues + vote/reconstruction */}
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
            <ReconstructionPanel
              phase={activePhase}
              currentQuestion={reconstructionQuestion}
              results={reconstructionResults}
              complete={reconstructionComplete}
              onSubmitAnswer={sendReconstructionAnswer}
              connected={connected}
            />
            {isReveal && (
              <div style={{ textAlign: 'center', marginTop: 16 }}>
                <button className="btn btn-primary" onClick={() => navigate('/')}>
                  {t('mm.back_lobby')}
                </button>
              </div>
            )}
          </aside>
        </div>

        <TraceFeed roomId={roomId} showTraces={showTraces} />
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
            {t('game.back')}
          </button>
          <span className="game-header-title">
            {puzzle?.title ?? t('game.loading')}
            <span className="room-id-badge"> #{roomId}</span>
          </span>
          <div className="game-header-right">
            <LanguageToggle />
            <button
              className={`btn btn-ghost trace-setting-btn${showTraces ? ' trace-setting-btn--on' : ''}`}
              onClick={toggleTraces}
              title={showTraces ? 'Hide agent traces' : 'Show agent traces'}
            >
              ⚡
            </button>
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
              {t('room.public_chat_tab')}
            </button>
            <button
              className={`chat-mode-tab${chatMode === 'private' ? ' chat-mode-tab--active chat-mode-tab--private' : ''}`}
              onClick={() => setChatMode('private')}
              disabled={!privateClues.length}
            >
              {t('room.private_chat_tab')}
            </button>
          </div>
        )}

        <div className="room-chat">
          {chatMode === 'public' ? (
            <>
              <MessageList msgs={messages} playerName={playerName} dmTyping={dmTyping} showTraces={showTraces} />
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
                placeholder={connected ? t('room.input_placeholder') : t('room.input_connecting')}
                value={input}
                disabled={!connected || !!truth}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
                }}
              />
              <button className="btn btn-primary" onClick={handleSend} disabled={!input.trim() || !connected || !!truth}>
                {t('game.send')}
              </button>
            </>
          ) : (
            <>
              <input
                className="chat-input chat-input--private"
                type="text"
                placeholder={t('room.private_placeholder')}
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
                {t('game.private_send')}
              </button>
            </>
          )}
        </div>

        <div className="game-bottom">
          <HintBar hints={[]} progress={progress} />
        </div>

        <TraceFeed roomId={roomId} showTraces={showTraces} />
      </div>

      <aside className="game-sidebar room-sidebar">
        {privateClues.length > 0 && <PrivateCluePanel clues={privateClues} />}
        <PlayerList players={players} currentName={playerName} />
        <CluePanel clues={clues} panelRef={cluePanelRef} />
      </aside>
    </div>
  );
}
