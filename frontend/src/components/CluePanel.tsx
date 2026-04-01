import { useEffect, useRef, useState } from 'react';
import type { Clue } from '../api';
import { useT } from '../i18n';

interface CluePanelProps {
  clues: Clue[];
  /** Forwarded ref so parent can scroll this panel into view */
  panelRef?: React.Ref<HTMLDivElement>;
}

export function CluePanel({ clues, panelRef }: CluePanelProps) {
  const { t } = useT();
  // Track which clue id was most recently added so we can animate it
  const [newClueId, setNewClueId] = useState<string | null>(null);
  const prevLenRef = useRef(0);

  useEffect(() => {
    if (clues.length > prevLenRef.current) {
      const newest = clues[clues.length - 1];
      setNewClueId(newest.id);
      const t = setTimeout(() => setNewClueId(null), 2200);
      prevLenRef.current = clues.length;
      return () => clearTimeout(t);
    }
    prevLenRef.current = clues.length;
  }, [clues]);

  return (
    <div className="clue-panel" ref={panelRef}>
      <div className="clue-panel-header">
        <span className="clue-panel-icon">🔍</span>
        <span className="clue-panel-title">{t('clue.board_title')}</span>
        {clues.length > 0 && (
          <span className="clue-count-badge">{t('clue.found_count', { n: clues.length })}</span>
        )}
      </div>

      {clues.length === 0 ? (
        <p className="clue-panel-empty" style={{ whiteSpace: 'pre-line' }}>
          {t('clue.empty')}
        </p>
      ) : (
        <div className="clue-list">
          {clues.map((clue) => (
            <div
              key={clue.id}
              className={`clue-card${newClueId === clue.id ? ' clue-card--new' : ''}`}
            >
              <div className="clue-card-title">{clue.title}</div>
              <div className="clue-card-content">{clue.content}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
