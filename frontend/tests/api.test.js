import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiError, api, buildQuery, setUnauthorizedHandler } from '../src/lib/api.js';
import { describeCameraError } from '../src/lib/cameraErrors.js';

function mockFetch(handler) {
  const calls = [];
  globalThis.fetch = async (url, opts) => { calls.push({ url, opts }); return handler(url, opts); };
  return calls;
}
const json = (status, body, headers = {}) => ({ ok: status < 400, status, headers: { get: (k) => headers[k] ?? null }, text: async () => JSON.stringify(body), blob: async () => new Blob(['x']) });

test('buildQuery skips empty values', () => {
  assert.equal(buildQuery({ a: 1, b: '', c: null, d: undefined, e: 'x y' }), '?a=1&e=x+y');
  assert.equal(buildQuery({}), '');
});

test('sends credentials + CSRF header and JSON body', async () => {
  const calls = mockFetch(() => json(200, { user: { id: 1 } }));
  const r = await api.login('alice', 'pw');
  assert.equal(r.user.id, 1);
  const { url, opts } = calls[0];
  assert.equal(url, '/api/auth/login');
  assert.equal(opts.credentials, 'include');
  assert.equal(opts.headers['X-Requested-With'], 'XMLHttpRequest');
  assert.equal(opts.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(opts.body), { username: 'alice', password: 'pw' });
});

test('maps backend error payload to ApiError', async () => {
  mockFetch(() => json(409, { error: { code: 'duplicate_id', message: 'ID exists', details: { x: 1 } } }));
  await assert.rejects(() => api.people.create({}), (e) => e instanceof ApiError && e.status === 409 && e.code === 'duplicate_id' && e.details.x === 1 && e.message === 'ID exists');
});

test('network failure gives a friendly error', async () => {
  globalThis.fetch = async () => { throw new TypeError('fetch failed'); };
  await assert.rejects(() => api.me(), (e) => e.code === 'network' && /Cannot reach the server/.test(e.message));
});

test('401 not_authenticated triggers the unauthorized handler, bad login does not', async () => {
  let n = 0;
  setUnauthorizedHandler(() => { n += 1; });
  mockFetch(() => json(401, { error: { code: 'not_authenticated', message: 'Please sign in.' } }));
  await assert.rejects(() => api.dashboard());
  assert.equal(n, 1);
  mockFetch(() => json(401, { error: { code: 'invalid_credentials', message: 'Invalid username or password.' } }));
  await assert.rejects(() => api.login('a', 'b'));
  assert.equal(n, 1);
  setUnauthorizedHandler(null);
});

test('delete with purge flag and id encoding; export returns filename', async () => {
  const calls = mockFetch((url) => (url.includes('/export') ? json(200, {}, { 'Content-Disposition': 'attachment; filename="attendance_all_all.csv"' }) : json(200, { ok: true })));
  await api.people.remove('A/1', true);
  assert.equal(calls[0].url, '/api/people/A%2F1?purge_attendance=true');
  const ex = await api.attendance.export('csv', { q: 'ada', status: '' });
  assert.equal(calls[1].url, '/api/attendance/export?q=ada&format=csv');
  assert.equal(ex.filename, 'attendance_all_all.csv');
});

test('camera errors are explained', () => {
  assert.equal(describeCameraError({ name: 'NotAllowedError' }).title, 'Camera permission denied');
  assert.equal(describeCameraError({ name: 'NotFoundError' }).title, 'No camera found');
  assert.equal(describeCameraError({ name: 'NotReadableError' }).title, 'Camera is busy');
  assert.match(describeCameraError({}, false).message, /https/);
  assert.equal(describeCameraError({ code: 'unsupported' }).title, 'Camera not supported');
  assert.equal(describeCameraError({ name: 'Weird', message: 'boom' }).message, 'boom');
});
