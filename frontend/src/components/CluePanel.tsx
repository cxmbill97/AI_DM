import { useEffect, useRef, useState } from 'react';
import type { Clue } from '../api';

interface CluePanelProps {
  clues: Clue[];
  /** Forwarded ref so parent can scroll this panel into view */
  panelRef?: React.Ref<HTMLDivElement>;
}

export function CluePanel({ clues, panelRef }: CluePanelProps) {
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
        <span className="clue-panel-title">线索板</span>
        {clues.length > 0 && (
          <span className="clue-count-badge">已发现 {clues.length} 条</span>
        )}
      </div>

      {clues.length === 0 ? (
        <p className="clue-panel-empty">
          提问时触及关键方向，<br />线索会自动解锁…
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
