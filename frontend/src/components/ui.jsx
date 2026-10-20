import { useEffect } from 'react';
import { ChevronLeft, ChevronRight, Inbox, Loader2, X } from 'lucide-react';
import { statusMeta } from '../lib/format.js';

export function Spinner({ className = 'h-5 w-5' }) {
  return <Loader2 className={`animate-spin text-indigo-600 ${className}`} aria-label="Loading" />;
}

export function PageLoader({ label = 'Loading…' }) {
  return <div className="flex items-center justify-center gap-3 py-20 text-slate-500"><Spinner />{label}</div>;
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export function StatCard({ icon: Icon, label, value, hint, tone = 'indigo' }) {
  const tones = {
    indigo: 'bg-indigo-50 text-indigo-600', emerald: 'bg-emerald-50 text-emerald-600',
    rose: 'bg-rose-50 text-rose-600', amber: 'bg-amber-50 text-amber-600', sky: 'bg-sky-50 text-sky-600',
  };
  return (
    <div className="card flex items-center gap-4 p-5">
      <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${tones[tone]}`}><Icon className="h-6 w-6" /></div>
      <div className="min-w-0">
        <p className="text-sm text-slate-500">{label}</p>
        <p className="text-2xl font-semibold text-slate-900">{value}</p>
        {hint && <p className="truncate text-xs text-slate-500">{hint}</p>}
      </div>
    </div>
  );
}

export function StatusBadge({ status }) {
  const m = statusMeta(status);
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${m.cls}`}>{m.label}</span>;
}

export function Badge({ children, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-700 ring-slate-500/20', green: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
    amber: 'bg-amber-50 text-amber-700 ring-amber-600/20', indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-600/20',
    rose: 'bg-rose-50 text-rose-700 ring-rose-600/20',
  };
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}>{children}</span>;
}

export function EmptyState({ title, description, children }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400"><Inbox className="h-6 w-6" /></div>
      <p className="font-medium text-slate-800">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-slate-500">{description}</p>}
      {children && <div className="mt-4">{children}</div>}
    </div>
  );
}

export function ErrorBanner({ message, onRetry }) {
  if (!message) return null;
  return (
    <div role="alert" className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
      <span>{message}</span>
      {onRetry && <button className="btn-secondary btn-sm" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Field({ label, error, hint, children, htmlFor }) {
  return (
    <div>
      <label className="label" htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      {error && <p className="mt-1 text-xs text-rose-600" role="alert">{error}</p>}
    </div>
  );
}

export function Modal({ open, title, onClose, children, footer, size = 'md', closeDisabled = false }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape' && !closeDisabled) onClose(); };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev; };
  }, [open, onClose, closeDisabled]);
  if (!open) return null;
  const widths = { sm: 'max-w-md', md: 'max-w-xl', lg: 'max-w-3xl', xl: 'max-w-5xl' };
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-slate-900/50" onClick={closeDisabled ? undefined : onClose} />
      <div className={`relative flex max-h-[92vh] w-full flex-col rounded-t-2xl bg-white shadow-xl sm:rounded-2xl ${widths[size]}`}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          <button onClick={onClose} disabled={closeDisabled} aria-label="Close" className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-40"><X className="h-5 w-5" /></button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3 sm:rounded-b-2xl">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel = 'Confirm', danger = false, busy = false, onConfirm, onClose, children }) {
  return (
    <Modal open={open} title={title} onClose={onClose} size="sm" closeDisabled={busy}
      footer={<>
        <button className="btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
        <button className={danger ? 'btn-danger' : 'btn-primary'} onClick={onConfirm} disabled={busy}>
          {busy && <Spinner className="h-4 w-4 !text-white" />}{confirmLabel}
        </button>
      </>}>
      <p className="text-sm text-slate-600">{message}</p>
      {children}
    </Modal>
  );
}

export function Pagination({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return (
    <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm text-slate-600">
      <span>{from}–{to} of {total}</span>
      <div className="flex items-center gap-1">
        <button className="btn-secondary btn-sm" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Previous page"><ChevronLeft className="h-4 w-4" /></button>
        <span className="px-2">Page {page} / {pages}</span>
        <button className="btn-secondary btn-sm" onClick={() => onPage(page + 1)} disabled={page >= pages} aria-label="Next page"><ChevronRight className="h-4 w-4" /></button>
      </div>
    </div>
  );
}
