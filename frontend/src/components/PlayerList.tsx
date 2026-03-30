import type { RoomPlayer } from '../api';

interface PlayerListProps {
  players: RoomPlayer[];
  currentName: string;
}

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

export function PlayerList({ players, currentName }: PlayerListProps) {
  const connected = players.filter((p) => p.connected).length;

  return (
    <div className="player-list">
      <div className="player-list-header">
        <span className="player-list-title">玩家</span>
        <span className="player-list-count">{connected}/{players.length}</span>
      </div>
      <ul className="player-list-items">
        {players.map((p) => (
          <li key={p.id} className={`player-item${p.connected ? '' : ' player-item--offline'}`}>
            <span className="player-avatar player-avatar--sm" style={avatarStyle(p.name)}>
              {p.name[0]}
            </span>
            <span className="player-name">
              {p.name}
              {p.name === currentName && <span className="player-you"> (你)</span>}
            </span>
            <span className={`player-dot${p.connected ? ' player-dot--online' : ''}`} style={{ marginLeft: 'auto' }} />
          </li>
        ))}
      </ul>
    </div>
  );
}
