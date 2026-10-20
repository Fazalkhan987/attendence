import test from 'node:test';
import assert from 'node:assert/strict';
import { addDays, filenameFromDisposition, formatDate, formatTime, initials, percent, quickRange, statusMeta, todayISO } from '../src/lib/format.js';

test('date helpers', () => {
  assert.equal(formatDate('2026-03-02'), '02 Mar 2026');
  assert.equal(formatDate(''), '');
  assert.equal(formatTime('08:30:15'), '08:30');
  assert.equal(addDays('2026-03-01', -1), '2026-02-28');
  assert.equal(addDays('2026-12-31', 1), '2027-01-01');
  assert.equal(todayISO(new Date(2026, 0, 5)), '2026-01-05');
});

test('quick ranges', () => {
  const now = new Date(2026, 2, 15);
  assert.deepEqual(quickRange('today', now), { date_from: '2026-03-15', date_to: '2026-03-15' });
  assert.deepEqual(quickRange('week', now), { date_from: '2026-03-09', date_to: '2026-03-15' });
  assert.deepEqual(quickRange('month', now), { date_from: '2026-03-01', date_to: '2026-03-15' });
  assert.deepEqual(quickRange('all', now), { date_from: '', date_to: '' });
});

test('misc helpers', () => {
  assert.equal(initials('Ada Lovelace'), 'AL');
  assert.equal(initials('  grace '), 'G');
  assert.equal(initials(''), '?');
  assert.equal(percent(1, 4), 25);
  assert.equal(percent(1, 0), 0);
  assert.equal(statusMeta('late').label, 'Late');
  assert.equal(statusMeta('weird').label, 'weird');
  assert.equal(filenameFromDisposition('attachment; filename="attendance_a_b.csv"'), 'attendance_a_b.csv');
  assert.equal(filenameFromDisposition(null, 'x.csv'), 'x.csv');
});
