import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { Scale, Shield, Zap } from 'lucide-react';

export default function AuthPage() {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Client-side validation before hitting the API
  const validate = (): string | null => {
    if (mode === 'signup') {
      if (username.length < 3) return 'Username must be at least 3 characters';
      if (!/^[a-zA-Z0-9_]+$/.test(username)) return 'Username can only contain letters, numbers, and underscores';
      if (username.length > 50) return 'Username must be 50 characters or less';
      if (password.length < 8) return 'Password must be at least 8 characters';
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    try {
      if (mode === 'login') {
        await login(username, password);
      } else {
        await signup(username, password);
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      let msg = 'Something went wrong. Please try again.';
      if (typeof detail === 'string') {
        msg = detail;
      } else if (Array.isArray(detail)) {
        // Pydantic validation errors come as an array
        const first = detail[0];
        if (first?.msg) msg = first.msg.replace('Value error, ', '');
      }
      // Make error messages more user-friendly
      if (msg.includes('Username already taken')) msg = 'That username is already taken. Please choose another.';
      if (msg.includes('Incorrect username or password') || msg.includes('401')) msg = 'Incorrect username or password.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-root">
      <div className="auth-left">
        <div className="auth-brand">
          <div className="brand-icon">
            <Scale size={28} />
          </div>
          <span className="brand-name">LexAI</span>
        </div>

        <div className="auth-hero">
          <h1>Your AI-powered<br /><em>legal assistant</em></h1>
          <p>Describe your situation in plain language. LexAI researches federal law, state statutes, and case precedents then gives you a clear picture of where you stand.</p>
        </div>

        <div className="auth-features">
          <div className="auth-feature">
            <Shield size={16} />
            <span>Jurisdiction-aware analysis</span>
          </div>
          <div className="auth-feature">
            <Zap size={16} />
            <span>Real-time legal research</span>
          </div>
          <div className="auth-feature">
            <Scale size={16} />
            <span>Attorney referrals included</span>
          </div>
        </div>

        <p className="auth-disclaimer">
          LexAI provides legal information, not legal advice. Always consult a licensed attorney for your specific situation.
        </p>
      </div>

      <div className="auth-right">
        <div className="auth-card">
          <div className="auth-tabs">
            <button
              className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
              onClick={() => { setMode('login'); setError(''); }}
            >
              Sign in
            </button>
            <button
              className={`auth-tab ${mode === 'signup' ? 'active' : ''}`}
              onClick={() => { setMode('signup'); setError(''); }}
            >
              Create account
            </button>
          </div>

          <form onSubmit={handleSubmit} className="auth-form">
            <div className="field-group">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="your_username"
                autoComplete="username"
                required
              />
              {mode === 'signup' && (
                <span className="field-hint">3–50 characters, letters/numbers/underscores only</span>
              )}
            </div>
            <div className="field-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                required
              />
              {mode === 'signup' && (
                <span className="field-hint">Minimum 8 characters</span>
              )}
            </div>

            {error && <div className="auth-error">{error}</div>}

            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? (
                <span className="btn-spinner" />
              ) : mode === 'login' ? (
                'Sign in'
              ) : (
                'Create account'
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
