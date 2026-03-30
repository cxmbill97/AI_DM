import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createRoom, listPuzzles } from '../api';
import type { PuzzleSummary } from '../api';
import { useEffect } from 'react';

function difficultyClass(d: string) {
  if (d === '简单') return 'easy';
  if (d === '困难') return 'hard';
  return 'medium';
}

export function LobbyPage() {
  const navigate = useNavigate();

  const [puzzles, setPuzzles] = useState<PuzzleSummary[]>([]);
  const [loadingPuzzles, setLoadingPuzzles] = useState(true);
  const [loadError, setLoadError] = useState('');

  // Room join state
  const [joinCode, setJoinCode] = useState('');
  const [playerName, setPlayerName] = useState('');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    listPuzzles()
      .then(setPuzzles)
      .catch((e: Error) => setLoadError(e.message))
      .finally(() => setLoadingPuzzles(false));
  }, []);

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
        <div className="start-logo">🍲</div>
        <h1 className="start-title">海龟汤</h1>
        <p className="start-subtitle">用是非问题推断故事的隐藏真相</p>
      </header>

      {/* Player name (shared for all actions) */}
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
          <button
            className="btn btn-primary"
            onClick={handleJoinRoom}
            disabled={busy}
          >
            加入
          </button>
        </div>
      </section>

      <div className="lobby-divider"><span>或选择谜题</span></div>

      {loadingPuzzles && <p className="loading-text">加载谜题中…</p>}
      {loadError && <p className="error-text">加载失败：{loadError}</p>}

      {!loadingPuzzles && !loadError && (
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
                  title="单人模式"
                >
                  单人
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => handleCreateRoom(p.id)}
                  disabled={busy}
                  title="创建多人房间"
                >
                  建房
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="start-actions">
        <button
          className="btn btn-ghost"
          onClick={() => handleSinglePlayer()}
          disabled={busy}
        >
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
    </div>
  );
}
