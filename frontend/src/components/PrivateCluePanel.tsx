import type { PrivateClue } from '../api';

interface PrivateCluePanelProps {
  clues: PrivateClue[];
  panelRef?: React.Ref<HTMLDivElement>;
}

export function PrivateCluePanel({ clues, panelRef }: PrivateCluePanelProps) {
  if (clues.length === 0) return null;

  return (
    <div className="private-clue-panel" ref={panelRef}>
      <div className="private-clue-panel-header">
        <span className="private-clue-panel-icon">🔐</span>
        <span className="private-clue-panel-title">我的秘密线索</span>
        <span className="private-clue-only-badge">仅你可见</span>
      </div>
      <p className="private-clue-panel-hint">
        这些线索只有你能看到，请用自己的话与其他玩家分享
      </p>
      <div className="clue-list">
        {clues.map((clue) => (
          <div key={clue.id} className="private-clue-card">
            <div className="private-clue-card-title">🔒 {clue.title}</div>
            <div className="private-clue-card-content">{clue.content}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
