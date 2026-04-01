import type { PrivateClue } from '../api';
import { useT } from '../i18n';

interface PrivateCluePanelProps {
  clues: PrivateClue[];
  panelRef?: React.Ref<HTMLDivElement>;
}

export function PrivateCluePanel({ clues, panelRef }: PrivateCluePanelProps) {
  const { t } = useT();
  if (clues.length === 0) return null;

  return (
    <div className="private-clue-panel" ref={panelRef}>
      <div className="private-clue-panel-header">
        <span className="private-clue-panel-icon">🔐</span>
        <span className="private-clue-panel-title">{t('private_clue.title')}</span>
        <span className="private-clue-only-badge">{t('private_clue.only_you')}</span>
      </div>
      <p className="private-clue-panel-hint">
        {t('private_clue.hint')}
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
