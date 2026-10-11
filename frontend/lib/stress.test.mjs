import test from 'node:test';
import assert from 'node:assert/strict';
import { stressTime } from './stress.ts';

test('Fitbit offset labels match Sleep across midnight without shifting instants', () => {
  assert.equal(stressTime('2026-10-10T19:50:00Z', 'UTC+05:30'), '01:20');
  assert.equal(stressTime('2026-10-11T01:53:00Z', 'UTC+05:30'), '07:23');
  assert.equal(stressTime('2026-10-11T08:54:00Z', 'UTC+05:30'), '14:24');
  assert.equal(stressTime('2026-10-11T10:34:00Z', 'UTC+05:30'), '16:04');
  assert.equal(stressTime('2026-10-11T04:00:00Z', 'UTC-04:00'), '00:00');
});

test('browser fallback retains DST-aware time formatting', () => {
  assert.equal(stressTime('2026-10-11T01:53:00Z', 'Europe/Berlin'), '03:53');
  assert.equal(stressTime('2026-12-11T01:53:00Z', 'Europe/Berlin'), '02:53');
});
