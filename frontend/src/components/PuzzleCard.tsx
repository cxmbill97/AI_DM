import { useState } from 'react';

interface PuzzleCardProps {
  title: string;
  surface: string;
}

const COLLAPSE_THRESHOLD = 80; // characters — collapse if longer

export function PuzzleCard({ title, surface }: PuzzleCardProps) {
  const needsCollapse = surface.length > COLLAPSE_THRESHOLD;
  const [expanded, setExpanded] = useState(!needsCollapse);

  return (
    <div className="puzzle-card">
      <div
        className="puzzle-card-header"
        onClick={() => needsCollapse && setExpanded((v) => !v)}
        role={needsCollapse ? 'button' : undefined}
        aria-expanded={needsCollapse ? expanded : undefined}
      >
        <span className="puzzle-card-label">🍲 汤面</span>
        <span className="puzzle-card-title">{title}</span>
        {needsCollapse && (
          <span className="puzzle-card-toggle-text">
            {expanded ? '收起 ▲' : '展开 ▼'}
          </span>
        )}
      </div>

      {expanded && (
        <div className="puzzle-card-body">
          <p className="puzzle-surface">{surface}</p>
        </div>
      )}
    </div>
  );
}
