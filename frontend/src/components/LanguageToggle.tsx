import { useT } from '../i18n';

export function LanguageToggle() {
  const { lang, setLang } = useT();

  return (
    <button
      className="lang-toggle"
      onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
      title={lang === 'zh' ? 'Switch to English' : '切换为中文'}
      aria-label={lang === 'zh' ? 'Switch to English' : '切换为中文'}
    >
      {lang === 'zh' ? 'EN' : '中'}
    </button>
  );
}
