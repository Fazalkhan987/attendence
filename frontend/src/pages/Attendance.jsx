import { useCallback, useEffect, useState } from 'react';
import { Download, FileSpreadsheet, Pencil, Plus, Search, Trash2 } from 'lucide-react';
import { api } from '../lib/api.js';
import useDebounce from '../hooks/useDebounce.js';
import { useToast } from '../context/ToastContext.jsx';
import { ConfirmDialog, EmptyState, ErrorBanner, Field, Modal, PageHeader, Pagination, Spinner, StatusBadge } from '../components/ui.jsx';
import { formatDate, formatTime, quickRange } from '../lib/format.js';

const PAGE_SIZE = 25;
const STATUSES = ['present', 'late', 'absent', 'excused'];
const RANGES = [['today', 'Today'], ['week', 'Last 7 days'], ['month', 'This month'], ['all', 'All time']];

function RecordModal({ open, record, onClose, onSaved }) {
  const editing = Boolean(record);
  const toast = useToast();
  const [people, setPeople] = useState([]);
  const [form, setForm] = useState({ person_id: '', status: 'present', date: '', time: '', note: '' });
  const [search, setSearch] = useState('');
  const dsearch = useDebounce(search, 250);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setError(''); setSearch('');
    setForm(record ? { person_id: record.person_id, status: record.status, date: record.att_date, time: formatTime(record.att_time), note: record.note || '' }
      : { person_id: '', status: 'present', date: quickRange('today').date_from, time: '', note: '' });
  }, [open, record]);
  useEffect(() => {
    if (!open || editing) return;
    api.people.list({ q: dsearch, page_size: 50 }).then((r) => setPeople(r.items)).catch(() => {});
  }, [open, editing, dsearch]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  async function submit(e) {
    e.preventDefault();
    if (!editing && !form.person_id) { setError('Choose a person.'); return; }
    setBusy(true); setError('');
    try {
      if (editing) await api.attendance.update(record.id, { status: form.status, time: form.time || undefined, note: form.note });
      else await api.attendance.create({ person_id: form.person_id, status: form.status, date: form.date || undefined, time: form.time || undefined, note: form.note || undefined });
      toast.success(editing ? 'Record updated.' : 'Record added.');
      onSaved();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  return (
    <Modal open={open} onClose={onClose} title={editing ? `Edit record: ${record?.person_name}` : 'Add attendance record'} closeDisabled={busy}
      footer={<><button className="btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
        <button className="btn-primary" type="submit" form="att-form" disabled={busy}>{busy && <Spinner className="h-4 w-4 !text-white" />}{editing ? 'Save' : 'Add record'}</button></>}>
      <form id="att-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        {error && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 sm:col-span-2">{error}</div>}
        {!editing && (
          <div className="sm:col-span-2">
            <Field label="Person" htmlFor="ar-person">
              <input className="input mb-2" placeholder="Search people…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search people" />
              <select id="ar-person" className="input" size={5} value={form.person_id} onChange={set('person_id')}>
                {people.map((p) => <option key={p.person_id} value={p.person_id}>{p.full_name} ({p.person_id})</option>)}
              </select>
            </Field>
          </div>
        )}
        <Field label="Status" htmlFor="ar-status"><select id="ar-status" className="input" value={form.status} onChange={set('status')}>{STATUSES.map((s) => <option key={s} value={s} className="capitalize">{s}</option>)}</select></Field>
        <Field label="Date" htmlFor="ar-date"><input id="ar-date" type="date" className="input" value={form.date} onChange={set('date')} disabled={editing} /></Field>
        <Field label="Time" htmlFor="ar-time" hint="Leave empty for the current time."><input id="ar-time" type="time" className="input" value={form.time} onChange={set('time')} /></Field>
        <Field label="Note" htmlFor="ar-note"><input id="ar-note" className="input" value={form.note} maxLength={300} onChange={set('note')} /></Field>
      </form>
    </Modal>
  );
}

export default function Attendance() {
  const toast = useToast();
  const [range, setRange] = useState('today');
  const [dates, setDates] = useState(quickRange('today'));
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const dq = useDebounce(q, 300);
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modal, setModal] = useState({ open: false, record: null });
  const [del, setDel] = useState({ record: null, busy: false });
  const [exporting, setExporting] = useState('');

  const filters = { date_from: dates.date_from, date_to: dates.date_to, status, q: dq };

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await api.attendance.list({ ...filters, page, page_size: PAGE_SIZE })); setError(''); }
    catch (e) { setError(e.message); } finally { setLoading(false); }
  }, [dates.date_from, dates.date_to, status, dq, page]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [dates.date_from, dates.date_to, status, dq]);

  const pickRange = (k) => { setRange(k); setDates(quickRange(k)); };
  const setDate = (k) => (e) => { setRange('custom'); setDates((d) => ({ ...d, [k]: e.target.value })); };

  async function doExport(format) {
    setExporting(format);
    try {
      const { blob, filename } = await api.attendance.export(format, filters);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(`Exported ${data.total} record${data.total === 1 ? '' : 's'} as ${format.toUpperCase()}.`);
    } catch (e) { toast.error(e.message); } finally { setExporting(''); }
  }

  async function confirmDelete() {
    setDel((d) => ({ ...d, busy: true }));
    try {
      await api.attendance.remove(del.record.id);
      toast.success('Record deleted.');
      setDel({ record: null, busy: false });
      if (data.items.length === 1 && page > 1) setPage(page - 1); else load();
    } catch (e) { toast.error(e.message); setDel((d) => ({ ...d, busy: false })); }
  }

  return (
    <>
      <PageHeader title="Attendance history" subtitle="Filter, review, correct and export attendance records.">
        <button className="btn-secondary" onClick={() => doExport('csv')} disabled={Boolean(exporting) || data.total === 0}>{exporting === 'csv' ? <Spinner className="h-4 w-4" /> : <Download className="h-4 w-4" />}CSV</button>
        <button className="btn-secondary" onClick={() => doExport('xlsx')} disabled={Boolean(exporting) || data.total === 0}>{exporting === 'xlsx' ? <Spinner className="h-4 w-4" /> : <FileSpreadsheet className="h-4 w-4" />}Excel</button>
        <button className="btn-primary" onClick={() => setModal({ open: true, record: null })}><Plus className="h-4 w-4" />Add record</button>
      </PageHeader>

      <div className="card mb-4 space-y-3 p-3">
        <div className="flex flex-wrap gap-2">
          {RANGES.map(([k, label]) => (
            <button key={k} onClick={() => pickRange(k)} className={`rounded-full px-3 py-1 text-sm font-medium ${range === k ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>{label}</button>
          ))}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div><label className="label" htmlFor="f-from">From</label><input id="f-from" type="date" className="input" value={dates.date_from} max={dates.date_to || undefined} onChange={setDate('date_from')} /></div>
          <div><label className="label" htmlFor="f-to">To</label><input id="f-to" type="date" className="input" value={dates.date_to} min={dates.date_from || undefined} onChange={setDate('date_to')} /></div>
          <div><label className="label" htmlFor="f-status">Status</label>
            <select id="f-status" className="input" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option>{STATUSES.map((s) => <option key={s} value={s} className="capitalize">{s}</option>)}</select></div>
          <div className="relative min-w-[220px] flex-1"><label className="label" htmlFor="f-q">Search</label>
            <Search className="pointer-events-none absolute left-3 top-[34px] h-4 w-4 text-slate-400" />
            <input id="f-q" className="input pl-9" placeholder="Name, ID or department" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        </div>
      </div>

      <ErrorBanner message={error} onRetry={load} />
      <div className="card overflow-hidden">
        {loading && data.items.length === 0 ? <div className="flex justify-center py-16"><Spinner /></div>
          : data.items.length === 0 ? <EmptyState title="No attendance records" description="Nothing matches these filters. Try a wider date range or add a record manually." />
          : (
            <div className={`overflow-x-auto ${loading ? 'opacity-60' : ''}`}>
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50"><tr><th className="th">Date</th><th className="th">Time</th><th className="th">Person</th><th className="th">Department</th><th className="th">Status</th><th className="th">Source</th><th className="th">Note</th><th className="th text-right">Actions</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((r) => (
                    <tr key={r.id} className="hover:bg-slate-50">
                      <td className="td whitespace-nowrap">{formatDate(r.att_date)}</td><td className="td">{formatTime(r.att_time)}</td>
                      <td className="td"><p className="font-medium text-slate-900">{r.person_name}</p><p className="text-xs text-slate-500">{r.person_id}</p></td>
                      <td className="td">{r.department || '—'}</td><td className="td"><StatusBadge status={r.status} /></td>
                      <td className="td capitalize">{r.source}{r.confidence != null && <span className="ml-1 text-xs text-slate-400">({r.confidence.toFixed(2)})</span>}</td>
                      <td className="td max-w-[200px] truncate" title={r.note || ''}>{r.note || '—'}</td>
                      <td className="td"><div className="flex justify-end gap-1">
                        <button className="btn-ghost btn-sm" onClick={() => setModal({ open: true, record: r })} aria-label={`Edit record of ${r.person_name}`}><Pencil className="h-4 w-4" /></button>
                        <button className="btn-ghost btn-sm text-rose-600 hover:bg-rose-50" onClick={() => setDel({ record: r, busy: false })} aria-label={`Delete record of ${r.person_name}`}><Trash2 className="h-4 w-4" /></button>
                      </div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPage={setPage} />
        {data.total > 0 && <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">{data.total} record{data.total === 1 ? '' : 's'} match the filters; exports include all of them.</p>}
      </div>

      <RecordModal open={modal.open} record={modal.record} onClose={() => setModal({ open: false, record: null })} onSaved={() => { setModal({ open: false, record: null }); load(); }} />
      <ConfirmDialog open={Boolean(del.record)} danger busy={del.busy} title="Delete record?" confirmLabel="Delete"
        message={del.record ? `Delete the ${del.record.status} record of ${del.record.person_name} on ${formatDate(del.record.att_date)}? The person can then be marked again that day.` : ''}
        onConfirm={confirmDelete} onClose={() => setDel({ record: null, busy: false })} />
    </>
  );
}
