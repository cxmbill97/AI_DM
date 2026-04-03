import { useState } from 'react';
import { useT } from '../i18n';
import type { ReconstructionComplete, ReconstructionQuestion, ReconstructionResult } from '../hooks/useRoom';

interface ReconstructionPanelProps {
  phase: string;
  currentQuestion: ReconstructionQuestion | null;
  results: ReconstructionResult[];
  complete: ReconstructionComplete | null;
  onSubmitAnswer: (answer: string) => void;
  connected: boolean;
}

export function ReconstructionPanel({
  phase,
  currentQuestion,
  results,
  complete,
  onSubmitAnswer,
  connected,
}: ReconstructionPanelProps) {
  const { t } = useT();
  const [answer, setAnswer] = useState('');
  const [submitted, setSubmitted] = useState<Set<string>>(new Set());

  // Show during reconstruction phase; also show summary during reveal (but not other phases)
  const isReveal = phase === 'reveal';
  if (phase !== 'reconstruction' && !(isReveal && complete)) return null;

  function handleSubmit() {
    if (!answer.trim() || !connected || !currentQuestion) return;
    onSubmitAnswer(answer.trim());
    setSubmitted((prev) => new Set(prev).add(currentQuestion.question_id));
    setAnswer('');
  }

  const hasSubmittedCurrent = currentQuestion ? submitted.has(currentQuestion.question_id) : false;

  return (
    <div className="reconstruction-panel">
      <div className="reconstruction-panel-title">
        {t('reconstruction.panel_title')}
      </div>

      {/* Score summary */}
      {results.length > 0 && (
        <div className="reconstruction-score-row">
          <span className="reconstruction-score-label">{t('reconstruction.score_label')}</span>
          <span className="reconstruction-score-value">
            {results.reduce((s, r) => s + r.score, 0)}
            {complete && `/${complete.max_score}`}
          </span>
        </div>
      )}

      {/* Completed state */}
      {complete && (
        <div className="reconstruction-complete">
          <div className="reconstruction-complete-pct">{complete.pct}%</div>
          <div className="reconstruction-complete-label">{t('reconstruction.complete_label')}</div>
        </div>
      )}

      {/* Current question */}
      {currentQuestion && !complete && (
        <div className="reconstruction-question-box">
          <div className="reconstruction-question-counter">
            {t('reconstruction.question_counter', {
              n: currentQuestion.index + 1,
              total: currentQuestion.total,
            })}
          </div>
          <div className="reconstruction-question-text">{currentQuestion.question}</div>

          {hasSubmittedCurrent ? (
            <div className="reconstruction-waiting">{t('reconstruction.waiting_result')}</div>
          ) : (
            <div className="reconstruction-input-row">
              <input
                className="chat-input reconstruction-input"
                type="text"
                placeholder={t('reconstruction.answer_placeholder')}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
                }}
                disabled={!connected}
              />
              <button
                className="btn btn-primary"
                onClick={handleSubmit}
                disabled={!answer.trim() || !connected}
              >
                {t('reconstruction.submit_btn')}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Previous results */}
      {results.length > 0 && (
        <div className="reconstruction-results-list">
          {results.map((r) => (
            <div key={r.question_id} className={`reconstruction-result-row reconstruction-result--${r.result}`}>
              <span className="reconstruction-result-icon">
                {r.result === 'correct' ? '✓' : r.result === 'partial' ? '△' : '✗'}
              </span>
              <span className="reconstruction-result-score">+{r.score}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
