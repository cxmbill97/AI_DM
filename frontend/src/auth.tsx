/**
 * AuthContext — Google OAuth + JWT state management.
 *
 * On mount:
 *   1. Check URL for ?token=<jwt> (Google callback redirect) → store + strip URL
 *   2. Load token from localStorage → call /api/me to validate
 *   3. Set user or clear bad token
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { AuthUser } from './api';
import { clearStoredToken, getMe, getStoredToken, setStoredToken } from './api';

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  logout: () => void;
}

// eslint-disable-next-line react-refresh/only-export-components
const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    clearStoredToken();
    setUser(null);
  }, []);

  useEffect(() => {
    // Step 1: handle ?token= from Google callback
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get('token');
    const urlError = params.get('error');

    if (urlToken) {
      setStoredToken(urlToken);
      // Strip token from URL without reload
      params.delete('token');
      const newSearch = params.toString();
      window.history.replaceState({}, '', newSearch ? `?${newSearch}` : window.location.pathname);
    }

    if (urlError) {
      params.delete('error');
      window.history.replaceState({}, '', window.location.pathname);
    }

    // Step 2: validate stored token
    const token = getStoredToken();
    if (!token) {
      setLoading(false);
      return;
    }

    getMe()
      .then(setUser)
      .catch(() => clearStoredToken())
      .finally(() => setLoading(false));
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
