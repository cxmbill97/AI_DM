import { useState } from 'react';

interface ScriptCardProps {
  charName: string;
  publicBio: string;
  secretBio?: string;       // only passed to the owning player
  personalScript?: string;  // reading-phase full script
  phase: string;
}

const PHASE_LABELS: Record<string, string> = {
  opening:         '开场叙事',
  reading:         '角色阅读',
  investigation_1: '调查阶段',
  discussion:      '讨论阶段',
  voting:          '投票阶段',
  reveal:          '真相揭晓',
};

const PHASE_DESC: Record<string, string> = {
  opening:         '聆听案件背景',
  reading:         '阅读你的角色剧本',
  investigation_1: '搜查线索，询问NPC，向DM提问',
  discussion:      '与其他玩家分享推理',
  voting:          '选出你认为的凶手',
  reveal:          '案件真相大白',
};

export function ScriptCard({ charName, publicBio, secretBio, personalScript, phase }: ScriptCardProps) {
  const [showSecret, setShowSecret] = useState(false);
  const [showScript, setShowScript] = useState(false);

  return (
    <div className="script-card">
      {/* Phase badge */}
      <div className="script-card-phase">
        <span className="script-phase-label">{PHASE_LABELS[phase] ?? phase}</span>
        <span className="script-phase-desc">{PHASE_DESC[phase] ?? ''}</span>
      </div>

      {/* Character public info */}
      <div className="script-card-char">
        <div className="script-char-avatar">{charName[0]}</div>
        <div className="script-char-body">
          <div className="script-char-name">{charName}</div>
          <div className="script-char-bio">{publicBio}</div>
        </div>
      </div>

      {/* Secret bio — only shown to this player */}
      {secretBio && (
        <div className="script-secret-section">
          <button
            className="script-secret-toggle"
            onClick={() => setShowSecret((v) => !v)}
          >
            🔐 {showSecret ? '隐藏我的秘密' : '查看我的秘密'}
          </button>
          {showSecret && (
            <div className="script-secret-content">
              <div className="script-secret-badge">仅你可见</div>
              <p>{secretBio}</p>
            </div>
          )}
        </div>
      )}

      {/* Personal script — shown during reading phase or on demand */}
      {personalScript && (
        <div className="script-personal-section">
          <button
            className="script-secret-toggle"
            onClick={() => setShowScript((v) => !v)}
            style={{ marginTop: showSecret ? 6 : 0 }}
          >
            📜 {showScript ? '收起剧本' : '查看角色剧本'}
          </button>
          {showScript && (
            <div className="script-personal-content">
              <pre className="script-personal-text">{personalScript}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
