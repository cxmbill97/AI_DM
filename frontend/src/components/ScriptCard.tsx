import { useState } from 'react';
import { useT } from '../i18n';

interface ScriptCardProps {
  charName: string;
  publicBio: string;
  secretBio?: string;       // only passed to the owning player
  personalScript?: string;  // reading-phase full script
  phase: string;
}

export function ScriptCard({ charName, publicBio, secretBio, personalScript, phase }: ScriptCardProps) {
  const { t } = useT();
  const [showSecret, setShowSecret] = useState(false);
  const [showScript, setShowScript] = useState(false);

  return (
    <div className="script-card">
      {/* Phase badge */}
      <div className="script-card-phase">
        <span className="script-phase-label">{t(`phase_label.${phase}`)}</span>
        <span className="script-phase-desc">{t(`phase_desc.${phase}`)}</span>
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
            {showSecret ? t('script.hide_secret') : t('script.show_secret')}
          </button>
          {showSecret && (
            <div className="script-secret-content">
              <div className="script-secret-badge">{t('script.only_you')}</div>
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
            {showScript ? t('script.hide_script') : t('script.show_script')}
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
