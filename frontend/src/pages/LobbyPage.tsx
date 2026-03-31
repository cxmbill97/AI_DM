import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createRoom, listPuzzles, listScripts } from '../api';
import type { PuzzleSummary, ScriptSummary } from '../api';

function difficultyClass(d: string) {
  if (d === '简单' || d === 'beginner') return 'easy';
  if (d === '困难' || d === 'hard') return 'hard';
  return 'medium';
}

export function LobbyPage() {
  const navigate = useNavigate();

  const [mode, setMode] = useState<'turtle_soup' | 'murder_mystery'>('turtle_soup');

  // Turtle soup state
  const [puzzles, setPuzzles] = useState<PuzzleSummary[]>([]);
  const [loadingPuzzles, setLoadingPuzzles] = useState(true);
  const [puzzleError, setPuzzleError] = useState('');

  // Murder mystery state
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [loadingScripts, setLoadingScripts] = useState(false);
  const [scriptError, setScriptError] = useState('');

  // Shared state
  const [joinCode, setJoinCode] = useState('');
  const [playerName, setPlayerName] = useState('');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    listPuzzles()
      .then(setPuzzles)
      .catch((e: Error) => setPuzzleError(e.message))
      .finally(() => setLoadingPuzzles(false));
  }, []);

  useEffect(() => {
    if (mode !== 'murder_mystery' || scripts.length > 0) return;
    setLoadingScripts(true);
    listScripts()
      .then(setScripts)
      .catch((e: Error) => setScriptError(e.message))
      .finally(() => setLoadingScripts(false));
  }, [mode, scripts.length]);

  function validateName(): boolean {
    if (!playerName.trim()) {
      setFormError('请输入你的名字');
      return false;
    }
    return true;
  }

  async function handleSinglePlayer(puzzleId?: string) {
    navigate('/play', { state: { puzzleId } });
  }

  async function handleCreateRoom(puzzleId?: string) {
    setFormError('');
    if (!validateName()) return;
    setBusy(true);
    try {
      const { room_id } = await createRoom(puzzleId);
      navigate(`/room/${room_id}`, { state: { playerName: playerName.trim() } });
    } catch (e) {
      setFormError(e instanceof Error ? e.message : '创建房间失败');
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateMMRoom(scriptId: string) {
    setFormError('');
    if (!validateName()) return;
    setBusy(true);
    try {
      const { room_id } = await createRoom({ game_type: 'murder_mystery', script_id: scriptId });
      navigate(`/room/${room_id}`, { state: { playerName: playerName.trim() } });
    } catch (e) {
      setFormError(e instanceof Error ? e.message : '创建剧本杀房间失败');
    } finally {
      setBusy(false);
    }
  }

  async function handleJoinRoom() {
    setFormError('');
    if (!validateName()) return;
    const code = joinCode.trim().toUpperCase();
    if (!code) {
      setFormError('请输入房间号');
      return;
    }
    navigate(`/room/${code}`, { state: { playerName: playerName.trim() } });
  }

  return (
    <div className="lobby-screen">
      <header className="start-header">
        <div className="start-logo">🎭</div>
        <h1 className="start-title">AI 主持人</h1>
        <p className="start-subtitle">海龟汤 &amp; 剧本杀</p>
      </header>

      {/* Player name */}
      <section className="lobby-section">
        <label className="lobby-label" htmlFor="player-name">你的名字</label>
        <input
          id="player-name"
          className="lobby-input"
          type="text"
          placeholder="起个名字…"
          maxLength={16}
          value={playerName}
          onChange={(e) => setPlayerName(e.target.value)}
        />
      </section>

      {formError && <p className="error-text">{formError}</p>}

      {/* Join existing room */}
      <section className="lobby-section lobby-join">
        <label className="lobby-label" htmlFor="room-code">加入房间</label>
        <div className="lobby-join-row">
          <input
            id="room-code"
            className="lobby-input lobby-input--code"
            type="text"
            placeholder="6位房间码"
            maxLength={6}
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === 'Enter' && handleJoinRoom()}
          />
          <button className="btn btn-primary" onClick={handleJoinRoom} disabled={busy}>
            加入
          </button>
        </div>
      </section>

      <div className="lobby-divider"><span>或选择游戏模式</span></div>

      {/* Mode tabs */}
      <div className="lobby-mode-tabs">
        <button
          className={`lobby-mode-tab${mode === 'turtle_soup' ? ' lobby-mode-tab--active' : ''}`}
          onClick={() => setMode('turtle_soup')}
        >
          🍜 海龟汤
        </button>
        <button
          className={`lobby-mode-tab${mode === 'murder_mystery' ? ' lobby-mode-tab--active' : ''}`}
          onClick={() => setMode('murder_mystery')}
        >
          🔍 剧本杀
        </button>
      </div>

      {/* Turtle soup puzzle list */}
      {mode === 'turtle_soup' && (
        <>
          {loadingPuzzles && <p className="loading-text">加载谜题中…</p>}
          {puzzleError && <p className="error-text">加载失败：{puzzleError}</p>}

          {!loadingPuzzles && !puzzleError && (
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
                      onClick={() => handleSinglePlayer(p.id)}
                      disabled={busy}
                    >
                      单人
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={() => handleCreateRoom(p.id)}
                      disabled={busy}
                    >
                      建房
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="start-actions">
            <button className="btn btn-ghost" onClick={() => handleSinglePlayer()} disabled={busy}>
              🎲 随机单人
            </button>
            <button
              className="btn btn-primary"
              onClick={() => handleCreateRoom()}
              disabled={busy}
              style={{ minWidth: 140 }}
            >
              {busy ? '准备中…' : '🎮 随机建房'}
            </button>
          </div>
        </>
      )}

      {/* Murder mystery script list */}
      {mode === 'murder_mystery' && (
        <>
          {loadingScripts && <p className="loading-text">加载剧本中…</p>}
          {scriptError && <p className="error-text">加载失败：{scriptError}</p>}

          {!loadingScripts && !scriptError && scripts.length === 0 && (
            <p className="loading-text">暂无可用剧本</p>
          )}

          {!loadingScripts && !scriptError && scripts.length > 0 && (
            <div className="puzzle-list">
              {scripts.map((s) => (
                <div key={s.id} className="puzzle-list-item">
                  <div className="puzzle-list-item-body">
                    <h3 className="puzzle-item-title">{s.title}</h3>
                    <div className="puzzle-item-meta">
                      <span className={`difficulty-badge ${difficultyClass(s.difficulty)}`}>
                        {s.difficulty}
                      </span>
                      <span className="tag-badge">👥 {s.player_count}人</span>
                    </div>
                  </div>
                  <div className="puzzle-item-actions">
                    <button
                      className="btn btn-primary"
                      onClick={() => handleCreateMMRoom(s.id)}
                      disabled={busy}
                    >
                      {busy ? '准备中…' : '建房'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
