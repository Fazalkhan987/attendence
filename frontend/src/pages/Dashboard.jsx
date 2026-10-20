import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CalendarCheck, Clock, RefreshCw, ScanFace, TrendingUp, UserCheck, UserPlus, UserX, Users } from 'lucide-react';
import { api } from '../lib/api.js';
import { formatDate, formatShortDay, formatTime, percent } from '../lib/format.js';
import { EmptyState, ErrorBanner, PageHeader, PageLoader, StatCard, StatusBadge } from '../components/ui.jsx';

function TrendChart({ data }) {
  const max = Math.max(1, ...data.map((d) => d.present + d.late));
  return (
    <div className="flex h-44 items-end gap-3">
      {data.map((d) => {
        const total = d.present + d.late;
        return (
          <div key={d.date} className="flex h-full flex-1 flex-col items-center justify-end gap-1" title={`${formatDate(d.date)}: ${d.present} present, ${d.late} late`}>
            <span className="text-xs font-medium text-slate-600">{total}</span>
            <div className="flex w-full max-w-[44px] flex-col-reverse overflow-hidden rounded-t-md bg-slate-100" style={{ height: `${(total / max) * 100}%`, minHeight: total ? 4 : 2 }}>
              <div className="bg-emerald-500" style={{ height: `${total ? (d.present / total) * 100 : 0}%` }} />
              <div className="bg-amber-400" style={{ height: `${total ? (d.late / total) * 100 : 0}%` }} />
            </div>
            <span className="text-[11px] text-slate-500">{formatShortDay(d.date)}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (signal) => {
    setRefreshing(true);
    try {
      setData(await api.dashboard(signal));
      setError('');
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const ctl = new AbortController();
    load(ctl.signal);
    const t = setInterval(() => load(ctl.signal), 30000);
    return () => { ctl.abort(); clearInterval(t); };
  }, [load]);

  if (!data) return error ? <ErrorBanner message={error} onRetry={() => load()} /> : <PageLoader />;
  const d = data;

  return (
    <>
      <PageHeader title="Dashboard" subtitle={`Overview for ${formatDate(d.date)}`}>
        <button className="btn-secondary" onClick={() => load()} disabled={refreshing}><RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />Refresh</button>
        <Link to="/people" className="btn-secondary"><UserPlus className="h-4 w-4" />Add person</Link>
        <Link to="/live" className="btn-primary"><ScanFace className="h-4 w-4" />Open live camera</Link>
      </PageHeader>
      <ErrorBanner message={error} onRetry={() => load()} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon={Users} label="Total people" value={d.total_people} hint={`${d.students} students · ${d.employees} employees`} tone="indigo" />
        <StatCard icon={UserCheck} label="Present today" value={d.present_today} hint={`${d.late_today} late · ${d.attendance_rate}% attendance`} tone="emerald" />
        <StatCard icon={UserX} label="Absent today" value={d.absent_today} hint={d.excused_today ? `${d.excused_today} excused` : 'Not yet checked in'} tone="rose" />
        <StatCard icon={ScanFace} label="Faces registered" value={`${d.faces_registered}/${d.total_people}`} hint={d.faces_pending ? `${d.faces_pending} still need a face` : 'Everyone is enrolled'} tone={d.faces_pending ? 'amber' : 'sky'} />
      </div>

      {d.faces_pending > 0 && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <span>{d.faces_pending} {d.faces_pending === 1 ? 'person has' : 'people have'} no registered face and cannot be recognised automatically.</span>
          <Link to="/people?face_status=pending" className="btn-secondary btn-sm">Register faces</Link>
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <section className="card p-5 lg:col-span-2">
          <div className="mb-4 flex items-center gap-2"><TrendingUp className="h-5 w-5 text-slate-400" /><h2 className="font-semibold text-slate-900">Last 7 days</h2>
            <span className="ml-auto flex items-center gap-3 text-xs text-slate-500"><i className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-500" />Present<i className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-400" />Late</span>
          </div>
          <TrendChart data={d.trend} />
        </section>

        <section className="card p-5">
          <h2 className="mb-4 font-semibold text-slate-900">Today by department</h2>
          {d.by_department.length === 0 ? <p className="text-sm text-slate-500">No people registered yet.</p> : (
            <ul className="space-y-4">
              {d.by_department.map((x) => (
                <li key={x.department}>
                  <div className="mb-1 flex justify-between text-sm"><span className="text-slate-700">{x.department}</span><span className="text-slate-500">{x.present}/{x.total}</span></div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-500" style={{ width: `${percent(x.present, x.total)}%` }} /></div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="card mt-6 overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-2"><Clock className="h-5 w-5 text-slate-400" /><h2 className="font-semibold text-slate-900">Recent attendance</h2></div>
          <Link to="/attendance" className="text-sm font-medium text-indigo-600 hover:text-indigo-700">View all</Link>
        </div>
        {d.recent.length === 0 ? (
          <EmptyState title="No attendance yet" description="Open the live camera to start recognising registered people.">
            <Link to="/live" className="btn-primary"><CalendarCheck className="h-4 w-4" />Open live camera</Link>
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100">
              <thead className="bg-slate-50"><tr><th className="th">Person</th><th className="th">Department</th><th className="th">Date</th><th className="th">Time</th><th className="th">Status</th><th className="th">Source</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {d.recent.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50">
                    <td className="td"><p className="font-medium text-slate-900">{r.person_name}</p><p className="text-xs text-slate-500">{r.person_id}</p></td>
                    <td className="td">{r.department || '—'}</td><td className="td">{formatDate(r.att_date)}</td><td className="td">{formatTime(r.att_time)}</td>
                    <td className="td"><StatusBadge status={r.status} /></td>
                    <td className="td capitalize">{r.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
