import { useEffect, useState } from 'react';
import { AlertTriangle, KeyRound } from 'lucide-react';
import { api } from '../lib/api.js';
import { useAuth } from '../context/AuthContext.jsx';
import { useToast } from '../context/ToastContext.jsx';
import { Field, PageHeader, Spinner } from '../components/ui.jsx';

export default function SettingsPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({ current: '', next: '', confirm: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { api.systemStatus().then(setStatus).catch(() => setStatus(false)); }, []);

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    if (form.next !== form.confirm) { setError('New password and confirmation do not match.'); return; }
    setBusy(true);
    try {
      await api.changePassword(form.current, form.next);
      toast.success('Password changed. Other sessions were signed out.');
      setForm({ current: '', next: '', confirm: '' });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const rows = status ? [
    ['Detector', status.detector], ['Recognition model', `${status.embedder} (${status.embedding_dim}-d)`],
    ['People with faces', `${status.people_with_faces} (${status.face_samples} samples)`],
    ['Match threshold', status.recognition_threshold], ['Photos needed to enrol a face', status.min_enrollment_samples],
    ['Late after', status.late_after || 'not set (nobody is marked late)'], ['Time zone', status.timezone],
  ] : [];

  return (
    <>
      <PageHeader title="Settings" subtitle={`Signed in as ${user?.display_name} (${user?.username})`} />
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card p-5">
          <h2 className="mb-4 flex items-center gap-2 font-semibold text-slate-900"><KeyRound className="h-5 w-5 text-slate-400" />Change password</h2>
          <form onSubmit={onSubmit} className="space-y-4">
            {error && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}
            <Field label="Current password" htmlFor="cur"><input id="cur" type="password" className="input" autoComplete="current-password" required value={form.current} onChange={set('current')} /></Field>
            <Field label="New password" htmlFor="new" hint="At least 10 characters."><input id="new" type="password" className="input" autoComplete="new-password" required value={form.next} onChange={set('next')} /></Field>
            <Field label="Confirm new password" htmlFor="conf"><input id="conf" type="password" className="input" autoComplete="new-password" required value={form.confirm} onChange={set('confirm')} /></Field>
            <button className="btn-primary" disabled={busy}>{busy && <Spinner className="h-4 w-4 !text-white" />}Update password</button>
          </form>
        </section>

        <section className="card p-5">
          <h2 className="mb-4 font-semibold text-slate-900">Recognition system</h2>
          {status === null && <div className="flex items-center gap-2 text-sm text-slate-500"><Spinner />Loading…</div>}
          {status === false && <p className="text-sm text-rose-600">Could not load system status.</p>}
          {status && (
            <>
              <dl className="divide-y divide-slate-100 text-sm">
                {rows.map(([k, v]) => <div key={k} className="flex justify-between gap-4 py-2"><dt className="text-slate-500">{k}</dt><dd className="text-right font-medium text-slate-800">{String(v)}</dd></div>)}
              </dl>
              <div className="mt-4 flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <p><strong>Anti-spoofing:</strong> {status.liveness_check}. Use supervision or an additional liveness solution where fraud matters.</p>
              </div>
            </>
          )}
        </section>
      </div>
    </>
  );
}
