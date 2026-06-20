import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import type { User } from '../types';
import { authApi } from '../services/api';

interface AuthContextType {
  user: User | null;
  login: (username: string, password: string) => Promise<void>;
  signup: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const token = localStorage.getItem('lexai_token');
    const username = localStorage.getItem('lexai_username');
    return token && username ? { access_token: token, username } : null;
  });

  const login = useCallback(async (username: string, password: string) => {
    const u = await authApi.login(username, password);
    localStorage.setItem('lexai_token', u.access_token);
    localStorage.setItem('lexai_username', u.username);
    setUser(u);
  }, []);

  const signup = useCallback(async (username: string, password: string) => {
    const u = await authApi.signup(username, password);
    localStorage.setItem('lexai_token', u.access_token);
    localStorage.setItem('lexai_username', u.username);
    setUser(u);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('lexai_token');
    localStorage.removeItem('lexai_username');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
