/**
 * Single-player game page — lifted from the original App.tsx game/end screens.
 */

import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { startGame } from '../api';
import type { Clue, StartResponse } from '../api';
import { ChatPanel } from '../components/ChatPanel';
import { CluePanel } from '../components/CluePanel';
import { HintBar } from '../components/HintBar';
import { PuzzleCard } from '../components/PuzzleCard';
import { LanguageToggle } from '../components/LanguageToggle';
import { useTraceSetting } from '../hooks/useTraceSetting';
import { useTTS, useTTSSetting } from '../hooks/useTTS';
import { useT } from '../i18n';

interface GameState {
  session: StartResponse;
  hints: string[];
  progress: number;
  questionCount: number;
  hintCount: number;
  truth: string;
  unlockedClues: Clue[];
}

// ---------------------------------------------------------------------------
// End Screen
// ---------------------------------------------------------------------------

interface EndScreenProps {
  truth: string;
  title: string;
  questionCount: number;
  hintCount: number;
  unlockedClues: Clue[];
  onRestart: () => void;
}

function EndScreen({ truth, title, questionCount, hintCount, unlockedClues, onRestart }: EndScreenProps) {
  const { t } = useT();
  return (
    <div className="end-screen">
      <div className="end-celebration">
        <div className="end-emoji">🎉</div>
        <h2 className="end-title">{t('game.truth_revealed')}</h2>
        <p className="end-subtitle">{t('game.solved_subtitle', { title })}</p>
      </div>

      <div className="end-section">
        <p className="end-section-label">{t('game.truth_label')}</p>
        <p className="end-truth-text">{truth}</p>
      </div>

      {unlockedClues.length > 0 && (
        <div className="end-section">
          <p className="end-section-label">{t('game.clues_found_section', { n: unlockedClues.length })}</p>
          <div className="end-clues">
            {unlockedClues.map((clue) => (
              <div key={clue.id} className="end-clue-card">
                <div className="end-clue-title">{clue.title}</div>
                <div className="end-clue-content">{clue.content}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="end-section">
        <p className="end-section-label">{t('game.stats_label')}</p>
        <div className="end-stats">
          <div className="stat-item">
            <div className="stat-value">{questionCount}</div>
            <div className="stat-label">{t('game.stats_questions')}</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">{hintCount}</div>
            <div className="stat-label">{t('game.stats_hints')}</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">{unlockedClues.length}</div>
            <div className="stat-label">{t('game.stats_clues')}</div>
          </div>
        </div>
      </div>

      <div className="end-actions">
        <button className="btn btn-primary" onClick={onRestart} style={{ minWidth: 160 }}>
          {t('game.play_again')}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SinglePlayerPage
// ---------------------------------------------------------------------------

export function SinglePlayerPage() {
  const { t, lang } = useT();
  const { showTraces, toggleTraces } = useTraceSetting();
  const { ttsEnabled, toggleTTS } = useTTSSetting();
  const { speak, stop: stopTTS } = useTTS(lang);
  const navigate = useNavigate();
  const location = useLocation();
  const puzzleId: string | undefined = (location.state as { puzzleId?: string })?.puzzleId;

  const [screen, setScreen] = useState<'loading' | 'game' | 'end'>('loading');
  const [game, setGame] = useState<GameState | null>(null);
  const [startError, setStartError] = useState('');
  const [showCluePanel, setShowCluePanel] = useState(false);
  const cluePanelRef = useRef<HTMLDivElement>(null);

  useEffect(() => { return () => stopTTS(); }, [stopTTS]);

  useEffect(() => {
    startGame(puzzleId, lang)
      .then((session) => {
        setGame({
          session,
          hints: [],
          progress: 0,
          questionCount: 0,
          hintCount: 0,
          truth: '',
          unlockedClues: [],
        });
        setScreen('game');
      })
      .catch((e: Error) => {
        setStartError(e.message);
        setScreen('game'); // show error inline
      });
  }, [puzzleId]);

  function handleClueUnlocked(clue: Clue) {
    setGame((g) => {
      if (!g) return g;
      if (g.unlockedClues.some((c) => c.id === clue.id)) return g;
      return { ...g, unlockedClues: [...g.unlockedClues, clue] };
    });
    setShowCluePanel(true);
  }

  function handleFinish(truth: string) {
    setGame((g) => g ? { ...g, truth, progress: 1 } : g);
    setScreen('end');
  }

  if (screen === 'loading') {
    return <div className="loading-text" style={{ textAlign: 'center', paddingTop: 80 }}>{t('game.loading')}</div>;
  }

  if (startError) {
    return (
      <div className="lobby-screen" style={{ textAlign: 'center', paddingTop: 80 }}>
        <p className="error-text">{t('game.start_failed', { msg: startError })}</p>
        <button className="btn btn-primary" onClick={() => navigate('/')}>{t('game.back_lobby')}</button>
      </div>
    );
  }

  if (screen === 'end' && game) {
    return (
      <EndScreen
        truth={game.truth}
        title={game.session.title}
        questionCount={game.questionCount}
        hintCount={game.hintCount}
        unlockedClues={game.unlockedClues}
        onRestart={() => navigate('/')}
      />
    );
  }

  if (!game) return null;

  const clueCount = game.unlockedClues.length;

  return (
    <div className="game-screen">
      <div className="game-main">
        <header className="game-header">
          <button className="btn btn-ghost" onClick={() => navigate('/')} style={{ padding: '4px 10px' }}>
            {t('game.back')}
          </button>
          <span className="game-header-title">{game.session.title}</span>
          <LanguageToggle />
          <button
            className="btn btn-ghost"
            onClick={toggleTTS}
            title={ttsEnabled ? 'Mute voice' : 'Unmute voice'}
            style={{ fontSize: 16 }}
          >
            {ttsEnabled ? '🔊' : '🔇'}
          </button>
          <button
            className={`btn btn-ghost trace-setting-btn${showTraces ? ' trace-setting-btn--on' : ''}`}
            onClick={toggleTraces}
            title={showTraces ? 'Hide agent traces' : 'Show agent traces'}
          >
            ⚡
          </button>
          <button
            className={`btn btn-ghost clue-toggle-btn${clueCount > 0 ? ' clue-toggle-btn--active' : ''}`}
            onClick={() => {
              setShowCluePanel((v) => !v);
              if (!showCluePanel) setTimeout(() => cluePanelRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
            }}
            aria-label={t('clue.board_title')}
          >
            🔍{clueCount > 0 && <span className="clue-toggle-count">{clueCount}</span>}
          </button>
        </header>

        <PuzzleCard title={game.session.title} surface={game.session.surface} />

        <div className={`clue-panel-mobile${showCluePanel ? ' clue-panel-mobile--open' : ''}`}>
          <CluePanel clues={game.unlockedClues} panelRef={cluePanelRef} />
        </div>

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
          onClueUnlocked={handleClueUnlocked}
          onDmResponse={(text) => { if (ttsEnabled) speak(text); }}
          cluePanelRef={cluePanelRef}
          showTraces={showTraces}
        />

        <div className="game-bottom">
          <HintBar hints={game.hints} progress={game.progress} />
        </div>
      </div>

      <aside className="game-sidebar">
        <CluePanel clues={game.unlockedClues} panelRef={cluePanelRef} />
      </aside>
    </div>
  );
}
