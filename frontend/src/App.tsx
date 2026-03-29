import { useEffect, useState } from 'react';
import { listPuzzles, startGame } from './api';
import type { PuzzleSummary, StartResponse } from './api';
import { ChatPanel } from './components/ChatPanel';
import { HintBar } from './components/HintBar';
import { PuzzleCard } from './components/PuzzleCard';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Screen = 'start' | 'game' | 'end';

interface GameState {
  session: StartResponse;
  hints: string[];
  progress: number;
  questionCount: number;
  hintCount: number;
  truth: string;
}

// ---------------------------------------------------------------------------
// Difficulty badge helper
// ---------------------------------------------------------------------------

function difficultyClass(d: string) {
  if (d === '简单') return 'easy';
  if (d === '困难') return 'hard';
  return 'medium';
}

// ---------------------------------------------------------------------------
// Start Screen
// ---------------------------------------------------------------------------

interface StartScreenProps {
  onStart: (puzzleId?: string) => void;
}

function StartScreen({ onStart }: StartScreenProps) {
  const [puzzles, setPuzzles] = useState<PuzzleSummary[]>([]);
  const [loadingPuzzles, setLoadingPuzzles] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    listPuzzles()
      .then(setPuzzles)
      .catch((e: Error) => setLoadError(e.message))
      .finally(() => setLoadingPuzzles(false));
  }, []);

  async function handleStart(puzzleId?: string) {
    setStarting(true);
    try {
      await onStart(puzzleId);
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="start-screen">
      <header className="start-header">
        <div className="start-logo">🍲</div>
        <h1 className="start-title">海龟汤</h1>
        <p className="start-subtitle">用是非问题推断故事的隐藏真相</p>
      </header>

      {loadingPuzzles && <p className="loading-text">加载谜题中…</p>}
      {loadError && <p className="error-text">加载失败：{loadError}</p>}

      {!loadingPuzzles && !loadError && (
        <>
          <div className="puzzle-list">
            {puzzles.map((p) => (
              <div key={p.id} className="puzzle-list-item">
                <div className="puzzle-list-item-body">
                  <h3 className="puzzle-item-title">{p.title}</h3>
                  <div className="puzzle-item-meta">
                    <span className={`difficulty-badge ${difficultyClass(p.difficulty)}`}>
                      {p.difficulty}
                    </span>
                    {p.tags.slice(0, 3).map((tag) => (
                      <span key={tag} className="tag-badge">{tag}</span>
                    ))}
                  </div>
                </div>
                <div className="puzzle-item-actions">
                  <button
                    className="btn btn-outline"
                    onClick={() => handleStart(p.id)}
                    disabled={starting}
                  >
                    开始
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="start-actions">
            <button
              className="btn btn-primary"
              onClick={() => handleStart()}
              disabled={starting}
              style={{ minWidth: 140 }}
            >
              {starting ? '准备中…' : '🎲 随机开始'}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// End Screen
// ---------------------------------------------------------------------------

interface EndScreenProps {
  truth: string;
  title: string;
  questionCount: number;
  hintCount: number;
  onRestart: () => void;
}

function EndScreen({ truth, title, questionCount, hintCount, onRestart }: EndScreenProps) {
  return (
    <div className="end-screen">
      <div className="end-celebration">
        <div className="end-emoji">🎉</div>
        <h2 className="end-title">真相大白！</h2>
        <p className="end-subtitle">你揭开了《{title}》的谜底</p>
      </div>

      <div className="end-section">
        <p className="end-section-label">🍜 汤底（真相）</p>
        <p className="end-truth-text">{truth}</p>
      </div>

      <div className="end-section">
        <p className="end-section-label">📊 本局统计</p>
        <div className="end-stats">
          <div className="stat-item">
            <div className="stat-value">{questionCount}</div>
            <div className="stat-label">共提问次数</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">{hintCount}</div>
            <div className="stat-label">使用提示数</div>
          </div>
        </div>
      </div>

      <div className="end-actions">
        <button className="btn btn-primary" onClick={onRestart} style={{ minWidth: 160 }}>
          再玩一局
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [screen, setScreen] = useState<Screen>('start');
  const [game, setGame] = useState<GameState | null>(null);
  const [startError, setStartError] = useState('');

  async function handleStart(puzzleId?: string) {
    setStartError('');
    try {
      const session = await startGame(puzzleId);
      setGame({
        session,
        hints: [],
        progress: 0,
        questionCount: 0,
        hintCount: 0,
        truth: '',
      });
      setScreen('game');
    } catch (e) {
      setStartError(e instanceof Error ? e.message : '启动失败，请重试');
    }
  }

  function handleFinish(truth: string) {
    setGame((g) => g ? { ...g, truth, progress: 1 } : g);
    setScreen('end');
  }

  function handleRestart() {
    setGame(null);
    setScreen('start');
  }

  // ------------------------------------------------------------------
  // Start screen
  // ------------------------------------------------------------------
  if (screen === 'start') {
    return (
      <>
        {startError && (
          <div style={{ textAlign: 'center', padding: '16px', color: 'var(--no)' }}>
            ⚠️ {startError}
          </div>
        )}
        <StartScreen onStart={handleStart} />
      </>
    );
  }

  // ------------------------------------------------------------------
  // End screen
  // ------------------------------------------------------------------
  if (screen === 'end' && game) {
    return (
      <EndScreen
        truth={game.truth}
        title={game.session.title}
        questionCount={game.questionCount}
        hintCount={game.hintCount}
        onRestart={handleRestart}
      />
    );
  }

  // ------------------------------------------------------------------
  // Game screen
  // ------------------------------------------------------------------
  if (!game) return null;

  return (
    <div className="game-screen">
      {/* Header */}
      <header className="game-header">
        <button className="btn btn-ghost" onClick={handleRestart} style={{ padding: '4px 10px' }}>
          ← 返回
        </button>
        <span className="game-header-title">{game.session.title}</span>
      </header>

      {/* Puzzle surface */}
      <PuzzleCard title={game.session.title} surface={game.session.surface} />

      {/* Messages + input */}
      <ChatPanel
        sessionId={game.session.session_id}
        disabled={screen !== 'game'}
        onHint={(hint) =>
          setGame((g) => g ? { ...g, hints: [...g.hints, hint], hintCount: g.hintCount + 1 } : g)
        }
        onProgress={(p) => setGame((g) => g ? { ...g, progress: p } : g)}
        onFinish={handleFinish}
        onQuestionAsked={() =>
          setGame((g) => g ? { ...g, questionCount: g.questionCount + 1 } : g)
        }
      />

      {/* Progress + hints (sticky bottom, above input) */}
      <div className="game-bottom">
        <HintBar hints={game.hints} progress={game.progress} />
      </div>
    </div>
  );
}
