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

const RESULT_LABELS: Record<string, string> = {
  true:  '🎉 你们找到了凶手！',
  false: '😱 凶手逍遥法外……',
};

export function VotePanel({
  phase,
  candidates,
  hasVoted,
  voteResult,
  onVote,
  voteCount,
  totalPlayers,
}: VotePanelProps) {
  if (phase !== 'voting' && !voteResult) return null;

  // Results view
  if (voteResult) {
    return (
      <div className="vote-panel vote-panel--result">
        <div className="vote-result-headline">
          {RESULT_LABELS[String(voteResult.is_correct)] ?? '投票结束'}
        </div>
        {voteResult.winner_name && (
          <div className="vote-result-winner">
            凶手：<strong>{voteResult.winner_name}</strong>
          </div>
        )}
        {!voteResult.winner_name && voteResult.runoff && (
          <div className="vote-result-tie">平局，进入加时投票…</div>
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
                {voteResult.vote_counts[c.id] ?? 0}票
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
        选出你认为的凶手
        <span className="vote-progress">({voteCount}/{totalPlayers} 已投票)</span>
      </div>

      {hasVoted ? (
        <div className="vote-waiting">
          <span>✅ 已投票，等待其他玩家…</span>
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
