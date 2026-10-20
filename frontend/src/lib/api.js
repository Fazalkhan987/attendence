// Thin fetch wrapper. Auth is an httpOnly session cookie (never readable by JS); every request also sends
// X-Requested-With so the backend's CSRF guard passes.
import { filenameFromDisposition } from './format.js';

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'error', details = {} } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const BASE = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE) || '';

let onUnauthorized = null;
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

export function buildQuery(query = {}) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') p.append(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

async function request(method, path, { body, form, query, signal, raw = false } = {}) {
  const headers = { 'X-Requested-With': 'XMLHttpRequest' };
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }

  let res;
  try {
    res = await fetch(BASE + path + buildQuery(query), { method, headers, body: payload, credentials: 'include', signal });
  } catch (e) {
    if (e && e.name === 'AbortError') throw e;
    throw new ApiError('Cannot reach the server. Check your connection and that the backend is running.', { status: 0, code: 'network' });
  }
  if (res.ok && raw) return res;

  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* non-JSON body */ }
  if (!res.ok) {
    const err = data && data.error;
    const detail = data && typeof data.detail === 'string' ? data.detail : null;
    const e = new ApiError((err && err.message) || detail || `Request failed (${res.status})`,
      { status: res.status, code: (err && err.code) || 'error', details: (err && err.details) || {} });
    if (res.status === 401 && e.code === 'not_authenticated' && onUnauthorized) onUnauthorized();
    throw e;
  }
  return data;
}

export const api = {
  login: (username, password) => request('POST', '/api/auth/login', { body: { username, password } }),
  logout: () => request('POST', '/api/auth/logout'),
  me: () => request('GET', '/api/auth/me'),
  changePassword: (current_password, new_password) =>
    request('POST', '/api/auth/change-password', { body: { current_password, new_password } }),

  dashboard: (signal) => request('GET', '/api/dashboard', { signal }),
  systemStatus: () => request('GET', '/api/system/status'),

  people: {
    list: (query, signal) => request('GET', '/api/people', { query, signal }),
    departments: () => request('GET', '/api/departments'),
    create: (body) => request('POST', '/api/people', { body }),
    update: (id, body) => request('PUT', `/api/people/${encodeURIComponent(id)}`, { body }),
    remove: (id, purgeAttendance = false) =>
      request('DELETE', `/api/people/${encodeURIComponent(id)}`, { query: { purge_attendance: purgeAttendance ? 'true' : '' } }),
    enroll: (id, files, allowPossibleDuplicate = false) => {
      const form = new FormData();
      files.forEach((f, i) => form.append('files', f, f.name || `capture-${i + 1}.jpg`));
      form.append('allow_possible_duplicate', allowPossibleDuplicate ? 'true' : 'false');
      return request('POST', `/api/people/${encodeURIComponent(id)}/faces`, { form });
    },
    clearFaces: (id) => request('DELETE', `/api/people/${encodeURIComponent(id)}/faces`),
    checkFrame: (blob, signal) => {
      const form = new FormData();
      form.append('file', blob, 'frame.jpg');
      return request('POST', '/api/enrollment/check', { form, signal });
    },
  },

  attendance: {
    list: (query, signal) => request('GET', '/api/attendance', { query, signal }),
    create: (body) => request('POST', '/api/attendance', { body }),
    update: (id, body) => request('PATCH', `/api/attendance/${id}`, { body }),
    remove: (id) => request('DELETE', `/api/attendance/${id}`),
    export: async (format, query) => {
      const res = await request('GET', '/api/attendance/export', { query: { ...query, format }, raw: true });
      return { blob: await res.blob(), filename: filenameFromDisposition(res.headers.get('Content-Disposition'), `attendance.${format}`) };
    },
  },
};
