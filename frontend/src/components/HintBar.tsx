import { useT } from '../i18n';

interface HintBarProps {
  hints: string[];
  progress: number; // 0.0 – 1.0
}

export function HintBar({ hints, progress }: HintBarProps) {
  const { t } = useT();
  const pct = Math.round(Math.min(progress, 1) * 100);

  return (
    <div className="hint-bar">
      <div className="progress-row">
        <div className="progress-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <span className="progress-label">{t('game.progress_label', { pct })}</span>
      </div>

      {hints.length > 0 && (
        <div className="hints-list">
          {hints.map((h, i) => (
            <div key={i} className="hint-item">
              <span className="hint-icon">💡</span>
              <span>{h}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
