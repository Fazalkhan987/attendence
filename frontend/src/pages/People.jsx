import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Camera, CheckCircle2, Clock3, Pencil, Search, Trash2, UserPlus } from 'lucide-react';
import { api } from '../lib/api.js';
import useDebounce from '../hooks/useDebounce.js';
import { useToast } from '../context/ToastContext.jsx';
import FaceEnrollModal from '../components/FaceEnrollModal.jsx';
import PersonFormModal from '../components/PersonFormModal.jsx';
import { Badge, ConfirmDialog, EmptyState, ErrorBanner, PageHeader, Pagination, Spinner } from '../components/ui.jsx';
import { initials } from '../lib/format.js';

const PAGE_SIZE = 15;

export default function People() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState('');
  const dq = useDebounce(q, 300);
  const type = params.get('type') || '';
  const faceStatus = params.get('face_status') || '';
  const department = params.get('department') || '';
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ items: [], total: 0 });
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ open: false, person: null });
  const [enroll, setEnroll] = useState({ open: false, person: null });
  const [del, setDel] = useState({ person: null, purge: false, busy: false });

  const setFilter = (k, v) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p, { replace: true }); setPage(1); };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.people.list({ q: dq, type, face_status: faceStatus, department, page, page_size: PAGE_SIZE }));
      setError('');
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  }, [dq, type, faceStatus, department, page]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [dq]);
  useEffect(() => { api.people.departments().then((r) => setDepartments(r.items)).catch(() => {}); }, [data.total]);

  async function confirmDelete() {
    setDel((d) => ({ ...d, busy: true }));
    try {
      const r = await api.people.remove(del.person.person_id, del.purge);
      toast.success(`${del.person.full_name} deleted (${r.face_samples_removed} face samples removed).`);
      setDel({ person: null, purge: false, busy: false });
      if (data.items.length === 1 && page > 1) setPage(page - 1); else load();
    } catch (e) { toast.error(e.message); setDel((d) => ({ ...d, busy: false })); }
  }

  const onSaved = (saved, created) => {
    setForm({ open: false, person: null });
    load();
    if (created) setEnroll({ open: true, person: saved });
  };

  return (
    <>
      <PageHeader title="People" subtitle="Students and employees, and their registered faces.">
        <button className="btn-primary" onClick={() => setForm({ open: true, person: null })}><UserPlus className="h-4 w-4" />Add person</button>
      </PageHeader>

      <div className="card mb-4 flex flex-wrap items-center gap-3 p-3">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input className="input pl-9" placeholder="Search by name, ID, department, email…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search people" />
        </div>
        <select className="input w-auto" value={type} onChange={(e) => setFilter('type', e.target.value)} aria-label="Filter by type">
          <option value="">All types</option><option value="student">Students</option><option value="employee">Employees</option>
        </select>
        <select className="input w-auto" value={department} onChange={(e) => setFilter('department', e.target.value)} aria-label="Filter by department">
          <option value="">All departments</option>{departments.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <select className="input w-auto" value={faceStatus} onChange={(e) => setFilter('face_status', e.target.value)} aria-label="Filter by face status">
          <option value="">Any face status</option><option value="registered">Face registered</option><option value="pending">Face pending</option>
        </select>
      </div>

      <ErrorBanner message={error} onRetry={load} />
      <div className="card overflow-hidden">
        {loading && data.items.length === 0 ? (
          <div className="flex justify-center py-16"><Spinner /></div>
        ) : data.items.length === 0 ? (
          <EmptyState title={dq || type || faceStatus || department ? 'No matching people' : 'No people yet'}
            description={dq || type || faceStatus || department ? 'Try changing your search or filters.' : 'Add your first student or employee, then register their face.'}>
            {!(dq || type || faceStatus || department) && <button className="btn-primary" onClick={() => setForm({ open: true, person: null })}><UserPlus className="h-4 w-4" />Add person</button>}
          </EmptyState>
        ) : (
          <div className={`overflow-x-auto ${loading ? 'opacity-60' : ''}`}>
            <table className="min-w-full divide-y divide-slate-100">
              <thead className="bg-slate-50"><tr><th className="th">Person</th><th className="th">Type</th><th className="th">Department / class</th><th className="th">Contact</th><th className="th">Face</th><th className="th text-right">Actions</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((p) => (
                  <tr key={p.person_id} className="hover:bg-slate-50">
                    <td className="td">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600">{initials(p.full_name)}</div>
                        <div><p className="font-medium text-slate-900">{p.full_name}</p><p className="text-xs text-slate-500">{p.person_id}</p></div>
                      </div>
                    </td>
                    <td className="td capitalize">{p.type}</td>
                    <td className="td">{[p.department, p.class_name].filter(Boolean).join(' · ') || '—'}</td>
                    <td className="td"><p>{p.email || '—'}</p><p className="text-xs text-slate-500">{p.phone || ''}</p></td>
                    <td className="td">{p.face_status === 'registered'
                      ? <Badge tone="green"><CheckCircle2 className="h-3 w-3" />Registered ({p.face_samples})</Badge>
                      : <Badge tone="amber"><Clock3 className="h-3 w-3" />Pending</Badge>}</td>
                    <td className="td">
                      <div className="flex justify-end gap-1">
                        <button className="btn-ghost btn-sm" onClick={() => setEnroll({ open: true, person: p })} title="Register face"><Camera className="h-4 w-4" /><span className="hidden xl:inline">Face</span></button>
                        <button className="btn-ghost btn-sm" onClick={() => setForm({ open: true, person: p })} title="Edit" aria-label={`Edit ${p.full_name}`}><Pencil className="h-4 w-4" /></button>
                        <button className="btn-ghost btn-sm text-rose-600 hover:bg-rose-50" onClick={() => setDel({ person: p, purge: false, busy: false })} title="Delete" aria-label={`Delete ${p.full_name}`}><Trash2 className="h-4 w-4" /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} />
      </div>

      <PersonFormModal open={form.open} person={form.person} onClose={() => setForm({ open: false, person: null })} onSaved={onSaved} />
      <FaceEnrollModal open={enroll.open} person={enroll.person} onClose={() => { setEnroll({ open: false, person: null }); load(); }} onDone={(p) => { setEnroll((e) => ({ ...e, person: p })); load(); }} />
      <ConfirmDialog open={Boolean(del.person)} danger busy={del.busy} title="Delete person?" confirmLabel="Delete permanently"
        message={`This deletes ${del.person?.full_name} (${del.person?.person_id}) and all stored face data. This cannot be undone.`}
        onConfirm={confirmDelete} onClose={() => setDel({ person: null, purge: false, busy: false })}>
        <label className="mt-4 flex items-start gap-2 text-sm text-slate-700">
          <input type="checkbox" className="mt-0.5 h-4 w-4 rounded border-slate-300 text-rose-600" checked={del.purge} onChange={(e) => setDel((d) => ({ ...d, purge: e.target.checked }))} />
          <span>Also delete this person&apos;s attendance history (otherwise past records are kept for reporting).</span>
        </label>
      </ConfirmDialog>
    </>
  );
}
