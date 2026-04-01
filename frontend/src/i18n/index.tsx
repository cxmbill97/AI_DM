import { createContext, useContext, useEffect, useState } from 'react';
import zhStrings from './zh.json';
import enStrings from './en.json';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Lang = 'zh' | 'en';

type Translations = typeof zhStrings;

const STRINGS: Record<Lang, Translations> = {
  zh: zhStrings,
  en: enStrings as unknown as Translations,
};

// ---------------------------------------------------------------------------
// t() — dot-notation key lookup with {placeholder} interpolation
// ---------------------------------------------------------------------------

function lookup(obj: unknown, parts: string[]): string | undefined {
  let cur = obj;
  for (const part of parts) {
    if (cur && typeof cur === 'object') {
      cur = (cur as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return typeof cur === 'string' ? cur : undefined;
}

export function makeT(lang: Lang) {
  return function t(key: string, params?: Record<string, string | number>): string {
    const parts = key.split('.');
    const val = lookup(STRINGS[lang], parts) ?? lookup(STRINGS['zh'], parts) ?? key;
    if (!params) return val;
    return val.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? `{${k}}`));
  };
}

// ---------------------------------------------------------------------------
// Language detection + persistence
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'aidm_lang';

function detectLang(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'zh' || stored === 'en') return stored;
  return navigator.language.startsWith('zh') ? 'zh' : 'en';
}

// ---------------------------------------------------------------------------
// React context
// ---------------------------------------------------------------------------

interface LanguageContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: ReturnType<typeof makeT>;
}

export const LanguageContext = createContext<LanguageContextValue>({
  lang: 'zh',
  setLang: () => {},
  t: makeT('zh'),
});

export function useT() {
  return useContext(LanguageContext);
}

// ---------------------------------------------------------------------------
// Provider (to be placed in App.tsx)
// ---------------------------------------------------------------------------

import { type ReactNode } from 'react';

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectLang);

  function setLang(next: Lang) {
    setLangState(next);
    localStorage.setItem(STORAGE_KEY, next);
  }

  // Keep document lang attribute in sync for accessibility
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  return (
    <LanguageContext.Provider value={{ lang, setLang, t: makeT(lang) }}>
      {children}
    </LanguageContext.Provider>
  );
}
