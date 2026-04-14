import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Heart, LayoutGrid, Clock, User, Search, Plus, LogOut } from 'lucide-react';
import {
  addFavorite, createRoom, getFavorites, likeScript,
  listCommunityScripts, listPuzzles, listScripts, removeFavorite,
} from '../api';
import type { CommunityScript, FavoriteItem, PuzzleSummary, ScriptSummary } from '../api';
import { useAuth } from '../auth';
import { useT } from '../i18n';
import { ScriptUploadModal } from '../components/ScriptUploadModal';
import { PuzzleUploadModal } from '../components/PuzzleUploadModal';

const THEMES = [
  { key: 'dark',    color: '#c4a35a', label: 'Dark' },
  { key: 'warm',    color: '#d4a05a', label: 'Warm' },
  { key: 'eerie',   color: '#6adc6a', label: 'Eerie' },
  { key: 'cold',    color: '#60a5fa', label: 'Cold' },
  { key: 'natural', color: '#a3c45a', label: 'Natural' },
] as const;

function diffClass(d: string) {
  if (d === '简单' || d === 'beginner') return 'diff-easy';
  if (d === '困难' || d === 'hard') return 'diff-hard';
  return 'diff-mid';
}

// Abstract SVG thumb — unique per puzzle/script id
function CardThumb({ id, type }: { id: string; type: 'ts' | 'mm' }) {
  const hue = [...id].reduce((h, c) => (h * 31 + c.charCodeAt(0)) & 0xffff, 0) % 360;
  const color = type === 'ts' ? `hsl(${hue},45%,55%)` : `hsl(${(hue + 140) % 360},40%,55%)`;
  const bg = type === 'ts' ? '#0e0a10' : '#080e14';
  const shape = hue % 3;
  return (
    <div className="game-card-thumb" style={{ background: bg }}>
      <svg width="100%" height="100%" viewBox="0 0 240 96" preserveAspectRatio="xMidYMid slice">
        <defs>
          <radialGradient id={`g-${id}`} cx="35%" cy="40%" r="65%">
            <stop offset="0%" stopColor={color} stopOpacity="0.22" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width="240" height="96" fill={`url(#g-${id})`} />
        {shape === 0 && <circle cx="180" cy="20" r="58" fill="none" stroke={color} strokeWidth="0.6" strokeOpacity="0.2" />}
        {shape === 1 && <rect x="140" y="-10" width="80" height="80" rx="6" fill="none" stroke={color} strokeWidth="0.6" strokeOpacity="0.2" transform="rotate(15 180 30)" />}
        {shape === 2 && <polygon points="190,5 235,90 145,90" fill="none" stroke={color} strokeWidth="0.6" strokeOpacity="0.2" />}
        <line x1="0" y1="60" x2="240" y2="40" stroke={color} strokeWidth="0.4" strokeOpacity="0.07" />
      </svg>
      <span className={`game-card-badge ${type === 'ts' ? 'badge-ts' : 'badge-mm'}`}>
        {type === 'ts' ? 'Turtle Soup' : 'Murder Mystery'}
      </span>
    </div>
  );
}

export function LobbyPage() {
  const navigate = useNavigate();
  const { t, lang } = useT();
  const { user, logout } = useAuth();

  const [mode, setMode] = useState<'turtle_soup' | 'murder_mystery'>('turtle_soup');
  const [puzzles, setPuzzles] = useState<PuzzleSummary[]>([]);
  const [scripts, setScripts] = useState<ScriptSummary[]>([]);
  const [communityScripts, setCommunityScripts] = useState<CommunityScript[]>([]);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [loadingPuzzles, setLoadingPuzzles] = useState(true);
  const [loadingScripts, setLoadingScripts] = useState(false);
  const [puzzleSearch, setPuzzleSearch] = useState('');
  const [scriptSearch, setScriptSearch] = useState('');
  const [likedIds, setLikedIds] = useState<Set<string>>(new Set());
  const [uploadPuzzleOpen, setUploadPuzzleOpen] = useState(false);
  const [uploadScriptOpen, setUploadScriptOpen] = useState(false);
  const [joinCode, setJoinCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [theme, setTheme] = useState(() => localStorage.getItem('ai_dm_theme') ?? 'dark');
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Apply theme
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('ai_dm_theme', theme);
  }, [theme]);

  // Load favorites
  useEffect(() => {
    getFavorites().then((favs: FavoriteItem[]) => {
      setFavorites(new Set(favs.map((f) => `${f.item_type}:${f.item_id}`)));
    }).catch(() => {});
  }, []);

  function refreshPuzzles() {
    setLoadingPuzzles(true);
    listPuzzles(lang).then(setPuzzles).catch(() => {}).finally(() => setLoadingPuzzles(false));
  }

  function refreshScripts() {
    setLoadingScripts(true);
    listScripts(lang).then(setScripts).catch(() => {}).finally(() => setLoadingScripts(false));
    listCommunityScripts({ lang }).then(setCommunityScripts).catch(() => {});
  }

  useEffect(() => { refreshPuzzles(); }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (mode === 'murder_mystery') refreshScripts();
  }, [mode, lang]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleScriptSearch(value: string) {
    setScriptSearch(value);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      listCommunityScripts({ lang, search: value || undefined }).then(setCommunityScripts).catch(() => {});
    }, 400);
  }

  async function toggleFavorite(itemType: 'puzzle' | 'script', itemId: string) {
    const key = `${itemType}:${itemId}`;
    const isFaved = favorites.has(key);
    setFavorites((prev) => { const n = new Set(prev); isFaved ? n.delete(key) : n.add(key); return n; });
    try {
      if (isFaved) await removeFavorite(itemType, itemId);
      else await addFavorite(itemType, itemId);
    } catch {
      setFavorites((prev) => { const n = new Set(prev); isFaved ? n.add(key) : n.delete(key); return n; });
    }
  }

  async function handleCreateRoom(puzzleId?: string) {
    setBusy(true);
    setCreateError(null);
    try {
      const { room_id } = await createRoom({ game_type: 'turtle_soup', puzzle_id: puzzleId, language: lang });
      const token = localStorage.getItem('ai_dm_token') ?? '';
      navigate(`/room/${room_id}`, { state: { token } });
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Failed to create room. Is the server running?');
    } finally { setBusy(false); }
  }

  async function handleCreateMMRoom(scriptId: string) {
    setBusy(true);
    setCreateError(null);
    try {
      const { room_id } = await createRoom({ game_type: 'murder_mystery', script_id: scriptId, language: lang });
      const token = localStorage.getItem('ai_dm_token') ?? '';
      navigate(`/room/${room_id}`, { state: { token } });
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : 'Failed to create room. Is the server running?');
    } finally { setBusy(false); }
  }

  async function handleLike(scriptId: string) {
    if (likedIds.has(scriptId)) return;
    setLikedIds((prev) => new Set([...prev, scriptId]));
    try {
      const res = await likeScript(scriptId);
      setCommunityScripts((prev) => prev.map((s) => s.script_id === scriptId ? { ...s, likes: res.likes } : s));
    } catch { setLikedIds((prev) => { const n = new Set(prev); n.delete(scriptId); return n; }); }
  }

  const filteredPuzzles = puzzles.filter((p) => {
    if (!puzzleSearch.trim()) return true;
    const q = puzzleSearch.toLowerCase();
    return p.title.toLowerCase().includes(q) || p.tags.some((tag) => tag.toLowerCase().includes(q));
  });

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="sidebar-logo-mark">
            <Clock size={16} />
          </div>
          <div className="sidebar-logo-text">
            <div className="sidebar-logo-name">AI DM</div>
            <div className="sidebar-logo-sub">Mystery Club</div>
          </div>
        </div>

        {user && (
          <div className="sidebar-user">
            {user.avatar_url
              ? <img src={user.avatar_url} alt={user.name} className="sidebar-avatar" />
              : <div className="sidebar-avatar">{user.name[0]}</div>
            }
            <div>
              <div className="sidebar-user-name">{user.name}</div>
            </div>
          </div>
        )}

        <nav className="sidebar-nav">
          <div className="sidebar-section-label">Play</div>
          <button className="sidebar-nav-item active">
            <LayoutGrid size={15} />
            Lobby
          </button>

          <div className="sidebar-section-label" style={{ marginTop: 8 }}>Account</div>
          <button className="sidebar-nav-item" onClick={() => navigate('/profile')}>
            <User size={15} />
            {t('profile.title')}
          </button>
          <button className="sidebar-nav-item" onClick={() => navigate('/profile')}>
            <Heart size={15} />
            {t('profile.favorites')}
          </button>
          <button className="sidebar-nav-item" onClick={() => navigate('/profile')}>
            <Clock size={15} />
            {t('profile.history')}
          </button>

          <div className="sidebar-section-label" style={{ marginTop: 8 }}>Theme</div>
          <div className="sidebar-theme-row">
            {THEMES.map((th) => (
              <div
                key={th.key}
                className={`theme-swatch${theme === th.key ? ' active' : ''}`}
                style={{ background: th.color }}
                title={th.label}
                onClick={() => setTheme(th.key)}
              />
            ))}
          </div>
        </nav>

        <div className="sidebar-footer">
          <button className="sidebar-google-btn" onClick={logout}>
            <LogOut size={14} />
            {t('auth.logout')}
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="main-content">
        {/* Join strip */}
        <div className="join-strip">
          <span className="join-strip-label">Join Room</span>
          <input
            className="join-strip-input"
            placeholder="ABC123"
            maxLength={6}
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && joinCode.trim()) {
                const token = localStorage.getItem('ai_dm_token') ?? '';
                navigate(`/room/${joinCode.trim()}`, { state: { token } });
              }
            }}
          />
          <button
            className="btn btn-primary"
            style={{ padding: '7px 16px', fontSize: 12 }}
            onClick={() => {
              if (joinCode.trim()) {
                const token = localStorage.getItem('ai_dm_token') ?? '';
                navigate(`/room/${joinCode.trim()}`, { state: { token } });
              }
            }}
          >
            Join
          </button>
          <div className="join-strip-divider" />
          <span className="join-strip-hint">or browse below</span>
        </div>

        {/* Room creation error */}
        {createError && (
          <div style={{ margin: '0 0 12px', padding: '10px 14px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, color: '#f87171', fontSize: 13 }}>
            {createError}
          </div>
        )}

        {/* Section header */}
        <div className="section-hdr">
          <div className="section-hdr-left">
            <div className="section-hdr-title">Browse Games</div>
            <div className="section-hdr-sub">Select a game to start or join a room</div>
          </div>
          <div className="section-hdr-right">
            <div className="search-wrap">
              <Search size={13} className="search-wrap-icon" />
              <input
                className="search-input-field"
                placeholder={t('lobby.search_placeholder')}
                value={mode === 'turtle_soup' ? puzzleSearch : scriptSearch}
                onChange={(e) => mode === 'turtle_soup' ? setPuzzleSearch(e.target.value) : handleScriptSearch(e.target.value)}
              />
            </div>
            <button
              className="btn btn-outline"
              style={{ padding: '7px 12px', fontSize: 12, display: 'flex', alignItems: 'center', gap: 5 }}
              onClick={() => mode === 'turtle_soup' ? setUploadPuzzleOpen(true) : setUploadScriptOpen(true)}
            >
              <Plus size={13} />
              Upload
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="lobby-tabs">
          <button className={`lobby-tab${mode === 'turtle_soup' ? ' lobby-tab--active' : ''}`} onClick={() => setMode('turtle_soup')}>
            Turtle Soup
          </button>
          <button className={`lobby-tab${mode === 'murder_mystery' ? ' lobby-tab--active' : ''}`} onClick={() => setMode('murder_mystery')}>
            Murder Mystery
          </button>
        </div>

        {/* Turtle soup grid */}
        {mode === 'turtle_soup' && (
          <div className="cards-grid">
            {loadingPuzzles && <p className="loading-text" style={{ gridColumn: '1/-1' }}>Loading…</p>}
            {filteredPuzzles.map((p) => (
              <div key={p.id} className="game-card">
                <CardThumb id={p.id} type="ts" />
                <button
                  className={`game-card-fav${favorites.has(`puzzle:${p.id}`) ? ' fav-active' : ''}`}
                  onClick={(e) => { e.stopPropagation(); void toggleFavorite('puzzle', p.id); }}
                >
                  <Heart size={14} fill={favorites.has(`puzzle:${p.id}`) ? 'currentColor' : 'none'} />
                </button>
                <div className="game-card-body">
                  <div className="game-card-title">{p.title}</div>
                  <div className="game-card-meta">
                    <span className={`meta-pill ${diffClass(p.difficulty)}`}>{p.difficulty}</span>
                    {p.tags.slice(0, 3).map((tag) => <span key={tag} className="meta-pill">{tag}</span>)}
                  </div>
                  <div className="game-card-actions">
                    <button className="game-card-btn game-card-btn--ghost" onClick={() => navigate('/play', { state: { puzzleId: p.id } })}>Solo</button>
                    <button className="game-card-btn game-card-btn--primary" disabled={busy} onClick={() => void handleCreateRoom(p.id)}>Create Room</button>
                  </div>
                </div>
              </div>
            ))}
            <div className="game-card game-card-upload" onClick={() => setUploadPuzzleOpen(true)}>
              <Plus size={24} className="game-card-upload-icon" />
              <span className="game-card-upload-label">{t('upload.puzzle_btn')}</span>
            </div>
          </div>
        )}

        {/* Murder mystery grid */}
        {mode === 'murder_mystery' && (
          <div className="cards-grid">
            {loadingScripts && <p className="loading-text" style={{ gridColumn: '1/-1' }}>Loading…</p>}
            {[...scripts, ...communityScripts.filter((c) => !scripts.some((s) => s.id === c.script_id))].map((s) => {
              const id = 'id' in s ? s.id : s.script_id;
              const title = s.title;
              const difficulty = s.difficulty;
              const isCommunity = !('id' in s);
              return (
                <div key={id} className="game-card">
                  <CardThumb id={id} type="mm" />
                  <button
                    className={`game-card-fav${favorites.has(`script:${id}`) ? ' fav-active' : ''}`}
                    onClick={(e) => { e.stopPropagation(); void toggleFavorite('script', id); }}
                  >
                    <Heart size={14} fill={favorites.has(`script:${id}`) ? 'currentColor' : 'none'} />
                  </button>
                  <div className="game-card-body">
                    <div className="game-card-title">{title}</div>
                    <div className="game-card-meta">
                      <span className={`meta-pill ${diffClass(difficulty)}`}>{difficulty}</span>
                      {'player_count' in s && <span className="meta-pill">{s.player_count}p</span>}
                      {isCommunity && (s as CommunityScript).author && <span className="meta-pill">{(s as CommunityScript).author}</span>}
                    </div>
                    <div className="game-card-actions">
                      {isCommunity && (
                        <button className="game-card-btn game-card-btn--ghost" onClick={() => void handleLike(id)}>
                          ♥ {(s as CommunityScript).likes || ''}
                        </button>
                      )}
                      <button className="game-card-btn game-card-btn--primary" disabled={busy} onClick={() => void handleCreateMMRoom(id)}>
                        Create Room
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
            <div className="game-card game-card-upload" onClick={() => setUploadScriptOpen(true)}>
              <Plus size={24} className="game-card-upload-icon" />
              <span className="game-card-upload-label">{t('upload.btn')}</span>
            </div>
          </div>
        )}
      </main>

      {uploadPuzzleOpen && (
        <PuzzleUploadModal lang={lang} onClose={() => setUploadPuzzleOpen(false)} onSuccess={() => { setUploadPuzzleOpen(false); refreshPuzzles(); }} />
      )}
      {uploadScriptOpen && (
        <ScriptUploadModal lang={lang} author={user?.name ?? ''} onClose={() => setUploadScriptOpen(false)} onSuccess={() => { setUploadScriptOpen(false); refreshScripts(); }} />
      )}
    </div>
  );
}
