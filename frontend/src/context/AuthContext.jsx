import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, setUnauthorizedHandler } from '../lib/api.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api.me().then((r) => alive && setUser(r.user)).catch(() => alive && setUser(null)).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, []);

  // Any API call that comes back "not authenticated" (expired / revoked session) signs the UI out.
  useEffect(() => { setUnauthorizedHandler(() => setUser(null)); return () => setUnauthorizedHandler(null); }, []);

  const login = useCallback(async (username, password) => {
    const r = await api.login(username, password);
    setUser(r.user);
    return r.user;
  }, []);

  const logout = useCallback(async () => {
    try { await api.logout(); } catch { /* cookie cleared server-side or already invalid */ }
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
