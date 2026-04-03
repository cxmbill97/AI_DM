import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createRoom, likeScript, listCommunityScripts, listPuzzles, listScripts } from '../api';
import type { CommunityScript, PuzzleSummary, ScriptSummary } from '../api';
import { useT } from '../i18n';
import { LanguageToggle } from '../components/LanguageToggle';
import { ScriptUploadModal } from '../components/ScriptUploadModal';
import { PuzzleUploadModal } from '../components/PuzzleUploadModal';

function difficultyClass(d: string) {
  if (d === '简单' || d === 'beginner') return 'easy';
  if (d === '困难' || d === 'hard') return 'hard';
  return 'medium';
}

const PLAYER_NAME_KEY = 'ai_dm_player_name';

export function LobbyPage() {
  const navigate = useNavigate();
  const { t, lang } = useT();

  const [mode, setMode] = useState<'turtle_soup' | 'murder_mystery'>('turtle_soup');

  // Turtle soup state
  const [puzzles, setPuzzles] = useState<PuzzleSummary[]>([]);
  const [loadingPuzzles, setLoadingPuzzles] = useState(true);
  const [puzzleError, setPuzzleError] = useState('');

  // Murder mystery state
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [loadingScripts, setLoadingScripts] = useState(false);
  const [scriptError, setScriptError] = useState('');
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [puzzleUploadModalOpen, setPuzzleUploadModalOpen] = useState(false);

  // Turtle soup search (client-side filter)
  const [puzzleSearch, setPuzzleSearch] = useState('');

  // Community scripts + search
  const [communityScripts, setCommunityScripts] = useState<CommunityScript[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [likedIds, setLikedIds] = useState<Set<string>>(new Set());
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Shared state
  const [joinCode, setJoinCode] = useState('');
  const [playerName, setPlayerName] = useState(() => localStorage.getItem(PLAYER_NAME_KEY) ?? '');
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');

  // Persist player name to localStorage
  useEffect(() => {
    if (playerName) localStorage.setItem(PLAYER_NAME_KEY, playerName);
  }, [playerName]);

  function refreshPuzzles() {
    setLoadingPuzzles(true);
    setPuzzleError('');
    listPuzzles(lang)
      .then(setPuzzles)
      .catch((e: Error) => setPuzzleError(e.message))
      .finally(() => setLoadingPuzzles(false));
  }

  useEffect(() => {
    refreshPuzzles();
  }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps

  function refreshScripts() {
    setLoadingScripts(true);
    setScriptError('');
    listScripts(lang)
      .then(setScripts)
      .catch((e: Error) => setScriptError(e.message))
      .finally(() => setLoadingScripts(false));
  }

  function loadCommunity(search = searchQuery) {
    listCommunityScripts({ lang, search: search || undefined })
      .then(setCommunityScripts)
      .catch(() => setCommunityScripts([]));
  }

  useEffect(() => {
    if (mode !== 'murder_mystery') return;
    refreshScripts();
    loadCommunity('');
  }, [mode, lang]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleSearchChange(value: string) {
    setSearchQuery(value);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => loadCommunity(value), 400);
  }

  async function handleLike(scriptId: string) {
    if (likedIds.has(scriptId)) return;
    setLikedIds((prev) => new Set([...prev, scriptId]));
    try {
      const res = await likeScript(scriptId);
      setCommunityScripts((prev) =>
        prev.map((s) => s.script_id === scriptId ? { ...s, likes: res.likes } : s),
      );
    } catch {
      setLikedIds((prev) => { const n = new Set(prev); n.delete(scriptId); return n; });
    }
  }

  function validateName(): boolean {
    if (!playerName.trim()) {
      setFormError(t('lobby.name_required'));
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
      const { room_id } = await createRoom({ game_type: 'turtle_soup', puzzle_id: puzzleId, language: lang });
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
      const { room_id } = await createRoom({ game_type: 'murder_mystery', script_id: scriptId, language: lang });
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
      setFormError(t('lobby.room_code_required'));
      return;
    }
    navigate(`/room/${code}`, { state: { playerName: playerName.trim() } });
  }

  return (
    <div className="lobby-screen">
      <div className="lobby-lang-toggle"><LanguageToggle /></div>
      <header className="start-header">
        <div className="start-logo">🎭</div>
        <h1 className="start-title">{t('lobby.title')}</h1>
        <p className="start-subtitle">{t('lobby.subtitle')}</p>
      </header>

      {/* Player name */}
      <section className="lobby-section">
        <label className="lobby-label" htmlFor="player-name">{t('lobby.player_name')}</label>
        <input
          id="player-name"
          className="lobby-input"
          type="text"
          placeholder={t('lobby.player_name_placeholder')}
          maxLength={16}
          value={playerName}
          onChange={(e) => setPlayerName(e.target.value)}
        />
      </section>

      {formError && <p className="error-text">{formError}</p>}

      {/* Join existing room */}
      <section className="lobby-section lobby-join">
        <label className="lobby-label" htmlFor="room-code">{t('lobby.join_room')}</label>
        <div className="lobby-join-row">
          <input
            id="room-code"
            className="lobby-input lobby-input--code"
            type="text"
            placeholder={t('lobby.room_code_placeholder')}
            maxLength={6}
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === 'Enter' && handleJoinRoom()}
          />
          <button className="btn btn-primary" onClick={handleJoinRoom} disabled={busy}>
            {t('lobby.join_btn')}
          </button>
        </div>
      </section>

      <div className="lobby-divider"><span>{t('lobby.or_mode')}</span></div>

      {/* Mode tabs */}
      <div className="lobby-mode-tabs">
        <button
          className={`lobby-mode-tab${mode === 'turtle_soup' ? ' lobby-mode-tab--active' : ''}`}
          onClick={() => setMode('turtle_soup')}
        >
          {t('lobby.turtle_soup')}
        </button>
        <button
          className={`lobby-mode-tab${mode === 'murder_mystery' ? ' lobby-mode-tab--active' : ''}`}
          onClick={() => setMode('murder_mystery')}
        >
          {t('lobby.murder_mystery')}
        </button>
      </div>

      {/* Turtle soup puzzle list */}
      {mode === 'turtle_soup' && (
        <>
          <div className="lobby-section-header">
            <input
              className="lobby-input lobby-search"
              type="text"
              placeholder={t('lobby.search_placeholder')}
              value={puzzleSearch}
              onChange={(e) => setPuzzleSearch(e.target.value)}
            />
            <button className="btn btn-outline btn-sm" onClick={() => setPuzzleUploadModalOpen(true)}>
              {t('upload.puzzle_btn')}
            </button>
          </div>
          {loadingPuzzles && <p className="loading-text">{t('lobby.loading_puzzles')}</p>}
          {puzzleError && <p className="error-text">{t('lobby.load_error', { msg: puzzleError })}</p>}

          {!loadingPuzzles && !puzzleError && (
            <div className="puzzle-list">
              {puzzles.filter((p) => {
                if (!puzzleSearch.trim()) return true;
                const q = puzzleSearch.toLowerCase();
                return p.title.toLowerCase().includes(q) || p.tags.some((tag) => tag.toLowerCase().includes(q));
              }).map((p) => (
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
                      {t('lobby.solo')}
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={() => handleCreateRoom(p.id)}
                      disabled={busy}
                    >
                      {t('lobby.create')}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="start-actions">
            <button className="btn btn-ghost" onClick={() => handleSinglePlayer()} disabled={busy}>
              {t('lobby.random_solo')}
            </button>
            <button
              className="btn btn-primary"
              onClick={() => handleCreateRoom()}
              disabled={busy}
              style={{ minWidth: 140 }}
            >
              {busy ? t('lobby.preparing') : t('lobby.random_room')}
            </button>
          </div>
        </>
      )}

      {/* Murder mystery script list */}
      {mode === 'murder_mystery' && (
        <>
          <div className="lobby-section-header">
            <input
              className="lobby-input lobby-search"
              type="text"
              placeholder={t('lobby.search_placeholder')}
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
            />
            <button className="btn btn-outline btn-sm" onClick={() => setUploadModalOpen(true)}>
              {t('upload.btn')}
            </button>
          </div>
          {loadingScripts && <p className="loading-text">{t('lobby.loading_scripts')}</p>}
          {scriptError && <p className="error-text">{t('lobby.load_error', { msg: scriptError })}</p>}

          {!loadingScripts && !scriptError && scripts.length === 0 && communityScripts.length === 0 && (
            <p className="loading-text">{t('lobby.no_scripts')}</p>
          )}

          {/* Built-in scripts */}
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
                      <span className="tag-badge">{t('lobby.players_count', { n: s.player_count })}</span>
                    </div>
                  </div>
                  <div className="puzzle-item-actions">
                    <button
                      className="btn btn-primary"
                      onClick={() => handleCreateMMRoom(s.id)}
                      disabled={busy}
                    >
                      {busy ? t('lobby.preparing') : t('lobby.create')}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Community-uploaded scripts */}
          {communityScripts.length > 0 && (
            <>
              <p className="lobby-section-label">{t('lobby.community_scripts')}</p>
              <div className="puzzle-list">
                {communityScripts.map((s) => (
                  <div key={s.script_id} className="puzzle-list-item">
                    <div className="puzzle-list-item-body">
                      <h3 className="puzzle-item-title">{s.title}</h3>
                      <div className="puzzle-item-meta">
                        <span className={`difficulty-badge ${difficultyClass(s.difficulty)}`}>
                          {s.difficulty}
                        </span>
                        <span className="tag-badge">{t('lobby.players_count', { n: s.player_count })}</span>
                        {s.author && <span className="tag-badge tag-badge--author">{s.author}</span>}
                      </div>
                    </div>
                    <div className="puzzle-item-actions">
                      <button
                        className={`btn btn-ghost like-btn${likedIds.has(s.script_id) ? ' like-btn--liked' : ''}`}
                        onClick={() => handleLike(s.script_id)}
                        title={t('lobby.like')}
                        aria-label={t('lobby.like')}
                      >
                        ♥ {s.likes > 0 ? s.likes : ''}
                      </button>
                      <button
                        className="btn btn-primary"
                        onClick={() => handleCreateMMRoom(s.script_id)}
                        disabled={busy}
                      >
                        {busy ? t('lobby.preparing') : t('lobby.create')}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
      {puzzleUploadModalOpen && (
        <PuzzleUploadModal
          lang={lang}
          onClose={() => setPuzzleUploadModalOpen(false)}
          onSuccess={(_puzzleId, title) => {
            setPuzzleUploadModalOpen(false);
            refreshPuzzles();
            setFormError(t('upload.puzzle_success', { title }));
            setTimeout(() => setFormError(''), 3000);
          }}
        />
      )}
      {uploadModalOpen && (
        <ScriptUploadModal
          lang={lang}
          author={playerName.trim()}
          onClose={() => setUploadModalOpen(false)}
          onSuccess={(_scriptId, title) => {
            setUploadModalOpen(false);
            refreshScripts();
            loadCommunity('');
            setFormError(t('upload.success', { title }));
            setTimeout(() => setFormError(''), 3000);
          }}
        />
      )}
    </div>
  );
}
