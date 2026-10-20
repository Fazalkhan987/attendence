import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Lock, ScanFace, ShieldCheck, User, Zap } from 'lucide-react';
import { useAuth } from '../context/AuthContext.jsx';
import { Spinner } from '../components/ui.jsx';

export default function Login() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (!loading && user) return <Navigate to={location.state?.from || '/'} replace />;

  async function onSubmit(e) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await login(username.trim(), password);
      navigate(location.state?.from || '/', { replace: true });
    } catch (err) {
      setError(err.message || 'Sign-in failed.');
      setPassword('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-indigo-700 via-indigo-600 to-violet-700 p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/15"><ShieldCheck className="h-6 w-6" /></div>
          <span className="text-lg font-semibold">Smart Attendance</span>
        </div>
        <div>
          <h2 className="text-4xl font-semibold leading-tight">Attendance that takes care of itself.</h2>
          <p className="mt-4 max-w-md text-indigo-100">Register people once, point a camera at the entrance, and attendance is recorded automatically with a full, auditable history.</p>
          <ul className="mt-8 space-y-4 text-sm text-indigo-50">
            <li className="flex items-center gap-3"><ScanFace className="h-5 w-5" />Deep-learning face recognition (ArcFace)</li>
            <li className="flex items-center gap-3"><Zap className="h-5 w-5" />Live multi-face recognition with instant feedback</li>
            <li className="flex items-center gap-3"><ShieldCheck className="h-5 w-5" />Administrator-only access, one record per person per day</li>
          </ul>
        </div>
        <p className="text-xs text-indigo-200">Authorised administrators only. Activity is logged.</p>
      </div>

      <div className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white"><ShieldCheck className="h-6 w-6" /></div>
            <span className="text-lg font-semibold">Smart Attendance</span>
          </div>
          <h1 className="text-2xl font-semibold text-slate-900">Administrator sign in</h1>
          <p className="mt-1 text-sm text-slate-500">Enter your credentials to open the dashboard.</p>

          <form onSubmit={onSubmit} className="mt-8 space-y-5" noValidate>
            {error && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}
            <div>
              <label htmlFor="username" className="label">Username</label>
              <div className="relative">
                <User className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                <input id="username" className="input pl-9" autoComplete="username" autoFocus required value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
            </div>
            <div>
              <label htmlFor="password" className="label">Password</label>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                <input id="password" className="input pl-9 pr-10" type={show ? 'text' : 'password'} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
                <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-2 top-2 rounded p-1 text-slate-400 hover:text-slate-600" aria-label={show ? 'Hide password' : 'Show password'}>
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <button className="btn-primary w-full py-2.5" disabled={busy || !username.trim() || !password}>
              {busy ? <><Spinner className="h-4 w-4 !text-white" />Signing in…</> : 'Sign in'}
            </button>
          </form>
          <p className="mt-6 text-center text-xs text-slate-400">Forgot your password? Ask the system owner to run <code className="rounded bg-slate-100 px-1">python -m app.manage set-password</code>.</p>
        </div>
      </div>
    </div>
  );
}
