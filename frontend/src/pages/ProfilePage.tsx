import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Heart, Clock } from 'lucide-react';
import { getFavorites, getHistory, listPuzzles, listScripts, removeFavorite } from '../api';
import type { FavoriteItem, HistoryItem, PuzzleSummary, ScriptSummary } from '../api';
import { useAuth } from '../auth';
import { useT } from '../i18n';

function diffClass(d: string) {
  if (d === '简单' || d === 'beginner') return 'diff-easy';
  if (d === '困难' || d === 'hard') return 'diff-hard';
  return 'diff-mid';
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function ProfilePage() {
  const navigate = useNavigate();
  const { t, lang } = useT();
  const { user } = useAuth();

  const [activeTab, setActiveTab] = useState<'favorites' | 'history'>('favorites');
  const [favorites, setFavorites] = useState<FavoriteItem[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [puzzleMap, setPuzzleMap] = useState<Record<string, PuzzleSummary>>({});
  const [scriptMap, setScriptMap] = useState<Record<string, ScriptSummary>>({});

  useEffect(() => {
    getFavorites().then(setFavorites).catch(() => {});
    getHistory().then(setHistory).catch(() => {});
    listPuzzles(lang).then((ps) => setPuzzleMap(Object.fromEntries(ps.map((p) => [p.id, p])))).catch(() => {});
    listScripts(lang).then((ss) => setScriptMap(Object.fromEntries(ss.map((s) => [s.id, s])))).catch(() => {});
  }, [lang]);

  async function handleUnfavorite(itemType: 'puzzle' | 'script', itemId: string) {
    setFavorites((prev) => prev.filter((f) => !(f.item_id === itemId && f.item_type === itemType)));
    try { await removeFavorite(itemType, itemId); }
    catch { getFavorites().then(setFavorites).catch(() => {}); }
  }

  if (!user) return null;

  const gamesPlayed = history.length;
  const favCount = favorites.length;

  return (
    <div className="app-layout">
      <main className="main-content">
        <div style={{ padding: '20px 24px 0', display: 'flex', alignItems: 'center', gap: 10 }}>
          <button className="btn btn-ghost" onClick={() => navigate('/')} style={{ padding: '6px 10px' }}>
            <ArrowLeft size={16} />
          </button>
        </div>

        {/* Header */}
        <div className="profile-header">
          {user.avatar_url
            ? <img src={user.avatar_url} alt={user.name} className="profile-avatar" />
            : <div className="profile-avatar-fallback">{user.name[0]}</div>
          }
          <div>
            <div className="profile-name">{user.name}</div>
            <div className="profile-email">{user.email}</div>
            <div className="profile-stats">
              <span className="profile-stat-chip">{t('profile.games_played', { n: gamesPlayed })}</span>
              <span className="profile-stat-chip">{t('profile.favorites_count', { n: favCount })}</span>
              <span className="profile-stat-chip">{t('profile.member_since', { date: formatDate(user.created_at) })}</span>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="profile-tabs">
          <button className={`profile-tab${activeTab === 'favorites' ? ' profile-tab--active' : ''}`} onClick={() => setActiveTab('favorites')}>
            <Heart size={13} style={{ display: 'inline', marginRight: 5 }} />
            {t('profile.favorites')}
          </button>
          <button className={`profile-tab${activeTab === 'history' ? ' profile-tab--active' : ''}`} onClick={() => setActiveTab('history')}>
            <Clock size={13} style={{ display: 'inline', marginRight: 5 }} />
            {t('profile.history')}
          </button>
        </div>

        {/* Favorites */}
        {activeTab === 'favorites' && (
          favorites.length === 0
            ? <div className="profile-empty">{t('profile.no_favorites')}</div>
            : (
              <div className="cards-grid">
                {favorites.map((fav) => {
                  const isPuzzle = fav.item_type === 'puzzle';
                  const puzzle = isPuzzle ? puzzleMap[fav.item_id] : null;
                  const script = !isPuzzle ? scriptMap[fav.item_id] : null;
                  const title = puzzle?.title ?? script?.title ?? fav.item_id;
                  const difficulty = puzzle?.difficulty ?? script?.difficulty ?? '';
                  const tags = puzzle?.tags ?? [];
                  return (
                    <div key={`${fav.item_type}:${fav.item_id}`} className="game-card">
                      <div className="game-card-thumb" style={{ background: isPuzzle ? '#0e0a10' : '#080e14', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <span className={`game-card-badge ${isPuzzle ? 'badge-ts' : 'badge-mm'}`} style={{ position: 'static' }}>
                          {isPuzzle ? 'Turtle Soup' : 'Murder Mystery'}
                        </span>
                      </div>
                      <button
                        className="game-card-fav fav-active"
                        onClick={() => void handleUnfavorite(fav.item_type as 'puzzle' | 'script', fav.item_id)}
                        title="Remove from favorites"
                      >
                        <Heart size={14} fill="currentColor" />
                      </button>
                      <div className="game-card-body">
                        <div className="game-card-title">{title}</div>
                        <div className="game-card-meta">
                          {difficulty && <span className={`meta-pill ${diffClass(difficulty)}`}>{difficulty}</span>}
                          {tags.slice(0, 2).map((tag) => <span key={tag} className="meta-pill">{tag}</span>)}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )
        )}

        {/* History */}
        {activeTab === 'history' && (
          history.length === 0
            ? <div className="profile-empty">{t('profile.no_history')}</div>
            : (
              <div className="history-list">
                {history.map((h) => (
                  <div key={h.id} className="history-item">
                    <span className={`game-card-badge ${h.game_type === 'turtle_soup' ? 'badge-ts' : 'badge-mm'}`} style={{ position: 'static', flexShrink: 0 }}>
                      {h.game_type === 'turtle_soup' ? 'Turtle Soup' : 'Murder Mystery'}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div className="history-item-title">{h.title}</div>
                      <div className="history-item-meta">{h.player_count} players</div>
                    </div>
                    <div className="history-item-date">{formatDate(h.played_at)}</div>
                  </div>
                ))}
              </div>
            )
        )}
      </main>
    </div>
  );
}
