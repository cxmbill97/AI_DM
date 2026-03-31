import { useEffect, useRef, useState } from 'react';

interface PhaseBarProps {
  phase: string;
  timeRemaining: number | null; // seconds; null = no timer
}

const PHASE_ORDER = [
  'opening',
  'reading',
  'investigation_1',
  'discussion',
  'voting',
  'reveal',
];

const PHASE_LABELS: Record<string, string> = {
  opening:         '开场',
  reading:         '阅读',
  investigation_1: '调查',
  discussion:      '讨论',
  voting:          '投票',
  reveal:          '揭晓',
};

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function PhaseBar({ phase, timeRemaining }: PhaseBarProps) {
  const [localTime, setLocalTime] = useState<number | null>(timeRemaining);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Sync when server pushes a new timeRemaining (phase change event)
  useEffect(() => {
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
              <div className="phase-step-label">{PHASE_LABELS[p] ?? p}</div>
            </div>
          );
        })}
      </div>

      {localTime !== null && phase !== 'reveal' && (
        <div className={`phase-timer${isWarning ? ' phase-timer--warning' : ''}`}>
          <span className="phase-timer-icon">⏱</span>
          <span className="phase-timer-value">{formatTime(localTime)}</span>
        </div>
      )}
    </div>
  );
}
