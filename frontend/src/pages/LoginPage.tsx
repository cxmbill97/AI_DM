import { useEffect, useState } from 'react';
import { useT } from '../i18n';

export function LoginPage() {
  const { t } = useT();
  const [error, setError] = useState(false);
  const [devName, setDevName] = useState('');
  const [devAvailable, setDevAvailable] = useState(false);
  const [configLoaded, setConfigLoaded] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('error') === 'oauth_failed') setError(true);
    fetch('/auth/config')
      .then((r) => r.json())
      .then((cfg) => { if (cfg.dev) setDevAvailable(true); })
      .catch(() => {})
      .finally(() => setConfigLoaded(true));
  }, []);

  function devLogin() {
    const name = devName.trim();
    if (name) window.location.href = `/auth/dev-login?name=${encodeURIComponent(name)}`;
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-logo-mark">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
        </div>
        <h1 className="login-title">AI DM</h1>
        <p className="login-subtitle">{t('auth.tagline')}</p>

        {error && <p className="login-error">{t('auth.oauth_failed')}</p>}

        {!devAvailable && (
          <a className="login-google-btn" href="/auth/google">
            <svg className="login-google-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            {t('auth.sign_in_google')}
          </a>
        )}

        {devAvailable && (
          <div className="login-dev-section">
            <p className="login-dev-label">Dev login (no Google credentials)</p>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                className="login-dev-input"
                placeholder="Your name"
                value={devName}
                onChange={(e) => setDevName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') devLogin(); }}
              />
              <button className="login-dev-btn" disabled={!devName.trim()} onClick={devLogin}>
                Go
              </button>
            </div>
          </div>
        )}

        <p className="login-note">{t('auth.login_note')}</p>
      </div>
    </div>
  );
}
