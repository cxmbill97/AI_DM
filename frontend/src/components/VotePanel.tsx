import { useT } from '../i18n';

interface VoteCandidate {
  id: string;
  name: string;
}

interface VoteResult {
  winner: string | null;       // character id, null = tie unresolved
  winner_name: string | null;
  is_correct: boolean;
  vote_counts: Record<string, number>; // char_id → count
  runoff: boolean;
}

interface VotePanelProps {
  phase: string;
  candidates: VoteCandidate[];
  hasVoted: boolean;
  voteResult: VoteResult | null;
  onVote: (targetId: string) => void;
  voteCount: number;
  totalPlayers: number;
}

export function VotePanel({
  phase,
  candidates,
  hasVoted,
  voteResult,
  onVote,
  voteCount,
  totalPlayers,
}: VotePanelProps) {
  const { t } = useT();
  if (phase !== 'voting' && !voteResult) return null;

  // Results view
  if (voteResult) {
    return (
      <div className="vote-panel vote-panel--result">
        <div className="vote-result-headline">
          {voteResult.is_correct ? t('voting.result_correct') : t('voting.result_wrong')}
        </div>
        {voteResult.winner_name && (
          <div className="vote-result-winner">
            {voteResult.is_correct ? t('voting.winner_label') : t('voting.accused_label')}<strong>{voteResult.winner_name}</strong>
          </div>
        )}
        {!voteResult.winner_name && voteResult.runoff && (
          <div className="vote-result-tie">{t('voting.runoff_tie')}</div>
        )}
        <div className="vote-result-tally">
          {candidates.map((c) => (
            <div key={c.id} className="vote-tally-row">
              <span className="vote-tally-name">{c.name}</span>
              <div className="vote-tally-bar-wrap">
                <div
                  className="vote-tally-bar"
                  style={{
                    width: `${Math.round(
                      ((voteResult.vote_counts[c.id] ?? 0) / Math.max(totalPlayers, 1)) * 100,
                    )}%`,
                  }}
                />
              </div>
              <span className="vote-tally-count">
                {t('voting.tally_votes', { n: voteResult.vote_counts[c.id] ?? 0 })}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Voting view
  return (
    <div className="vote-panel vote-panel--open">
      <div className="vote-panel-title">
        {t('voting.select_suspect')}
        <span className="vote-progress">({t('voting.votes_count', { count: voteCount, total: totalPlayers })})</span>
      </div>

      {hasVoted ? (
        <div className="vote-waiting">
          <span>{t('voting.voted')}</span>
        </div>
      ) : (
        <div className="vote-candidates">
          {candidates.map((c) => (
            <button
              key={c.id}
              className="vote-candidate-btn"
              onClick={() => onVote(c.id)}
            >
              <span className="vote-candidate-avatar">{c.name[0]}</span>
              <span className="vote-candidate-name">{c.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
