// Pure helpers (no React / DOM) so they can be unit-tested with `node --test`.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function pad(n) { return String(n).padStart(2, '0'); }

export function toISODate(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }

export function todayISO(now = new Date()) { return toISODate(now); }

export function addDays(iso, days) {
  const [y, m, d] = iso.split('-').map(Number);
  return toISODate(new Date(y, m - 1, d + days));
}

export function startOfMonthISO(now = new Date()) { return toISODate(new Date(now.getFullYear(), now.getMonth(), 1)); }

export function formatDate(iso) {
  if (!iso || !/^\d{4}-\d{2}-\d{2}/.test(iso)) return iso || '';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return `${pad(d)} ${MONTHS[m - 1]} ${y}`;
}

export function formatShortDay(iso) {
  if (!iso) return '';
  const [, m, d] = iso.split('-').map(Number);
  return `${MONTHS[m - 1]} ${d}`;
}

export function formatTime(t) { return t ? String(t).slice(0, 5) : ''; }

export function initials(name = '') {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

export function percent(part, total) { return total ? Math.round((part / total) * 100) : 0; }

export const STATUS_META = {
  present: { label: 'Present', cls: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20' },
  late: { label: 'Late', cls: 'bg-amber-50 text-amber-700 ring-amber-600/20' },
  absent: { label: 'Absent', cls: 'bg-rose-50 text-rose-700 ring-rose-600/20' },
  excused: { label: 'Excused', cls: 'bg-sky-50 text-sky-700 ring-sky-600/20' },
};

export function statusMeta(status) {
  return STATUS_META[status] || { label: status || 'Unknown', cls: 'bg-slate-100 text-slate-700 ring-slate-500/20' };
}

export function filenameFromDisposition(header, fallback = 'download') {
  if (!header) return fallback;
  const m = /filename="?([^";]+)"?/i.exec(header);
  return m ? m[1] : fallback;
}

export function quickRange(kind, now = new Date()) {
  const today = todayISO(now);
  switch (kind) {
    case 'today': return { date_from: today, date_to: today };
    case 'week': return { date_from: addDays(today, -6), date_to: today };
    case 'month': return { date_from: startOfMonthISO(now), date_to: today };
    default: return { date_from: '', date_to: '' };
  }
}
