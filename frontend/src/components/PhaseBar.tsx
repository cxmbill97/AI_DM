import { useEffect, useRef, useState } from 'react';
import { useT } from '../i18n';

interface PhaseBarProps {
  phase: string;
  timeRemaining: number | null; // seconds; null = no timer
  skipVotes?: { voted: number; needed: number } | null;
  hasSkipVoted?: boolean;
  onSkip?: () => void;
}

const PHASE_ORDER = [
  'opening',
  'reading',
  'investigation_1',
  'discussion',
  'voting',
  'reveal',
];

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function PhaseBar({ phase, timeRemaining, skipVotes, hasSkipVoted, onSkip }: PhaseBarProps) {
  const { t } = useT();
  const [localTime, setLocalTime] = useState<number | null>(timeRemaining);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Sync when server pushes a new timeRemaining (phase change event)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLocalTime(timeRemaining);
  }, [timeRemaining, phase]);

  // Client-side countdown
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (localTime === null || localTime <= 0) return;

    intervalRef.current = setInterval(() => {
      setLocalTime((t) => {
        if (t === null || t <= 1) {
          clearInterval(intervalRef.current!);
          return 0;
        }
        return t - 1;
      });
    }, 1000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [timeRemaining, phase]); // restart on new server time

  const currentIdx = PHASE_ORDER.indexOf(phase);
  const isWarning = localTime !== null && localTime > 0 && localTime <= 30;
  const canSkip = phase !== 'reveal' && phase !== 'voting' && !!onSkip;

  return (
    <div className="phase-bar">
      <div className="phase-steps">
        {PHASE_ORDER.map((p, idx) => {
          const status =
            idx < currentIdx ? 'done' : idx === currentIdx ? 'active' : 'pending';
          return (
            <div key={p} className={`phase-step phase-step--${status}`}>
              <div className="phase-step-dot">
                {status === 'done' ? '✓' : idx + 1}
              </div>
              <div className="phase-step-label">{t(`phase.${p}`)}</div>
            </div>
          );
        })}
      </div>

      <div className="phase-bar-controls">
        {localTime !== null && phase !== 'reveal' && (
          <div className={`phase-timer${isWarning ? ' phase-timer--warning' : ''}`}>
            <span className="phase-timer-icon">⏱</span>
            <span className="phase-timer-value">{formatTime(localTime)}</span>
          </div>
        )}

        {canSkip && (
          <div className="phase-skip">
            <button
              className={`btn btn-skip${hasSkipVoted ? ' btn-skip--voted' : ''}`}
              onClick={onSkip}
              disabled={hasSkipVoted}
              title={t('phase.skip_hint')}
            >
              {hasSkipVoted ? t('phase.skip_voted') : t('phase.skip')}
            </button>
            {skipVotes && skipVotes.voted > 0 && (
              <span className="skip-vote-count">
                {skipVotes.voted}/{skipVotes.needed}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
