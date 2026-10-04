import test from 'node:test';
import assert from 'node:assert/strict';
import { axisBounds, changeColor, lineSegments, nextPeriod, recoveryColor, relativeChange, shiftDay } from './recovery.ts';

test('date navigation crosses years and clamps calendar month ends', () => {
  assert.equal(shiftDay('2026-01-01', -1), '2025-12-31');
  assert.equal(nextPeriod('2025-08-31', '6M', '2026-12-01'), '2026-02-28');
  assert.equal(nextPeriod('2026-10-01', 'W', '2026-10-04'), '2026-10-04');
  assert.equal(nextPeriod('2026-03-01', 'M', '2026-10-04'), '2026-03-31');
});
test('missing readings split the trace and zero remains a reading', () => {
  const days = [20, null, 0, 30, null, 40].map(recovery => ({ recovery }));
  assert.deepEqual(lineSegments(days, 'recovery'), [[{ index: 0, value: 20 }], [{ index: 2, value: 0 }, { index: 3, value: 30 }], [{ index: 5, value: 40 }]]);
});
test('bars keep a zero baseline and vital axes include personal ranges', () => {
  assert.deepEqual(axisBounds([55, 70], 'recovery'), [0, 100]);
  const [low, high] = axisBounds([44, 48], 'hrv', { low: 35, high: 52 });
  assert.ok(low < 35 && high > 52);
});
test('comparison does not invent a percent when the previous period is zero or missing', () => {
  assert.equal(relativeChange(40, 0), null);
  assert.equal(relativeChange(null, 40), null);
  assert.ok(Math.abs(relativeChange(45, 50) + 10) < 1e-10);
  assert.equal(changeColor('hrv', 0), '#B6BCC2');
  assert.equal(changeColor('rhr', -3), '#00DCA0');
});
test('Recovery uses backend zones rather than assigning a zone to missing data', () => {
  assert.equal(recoveryColor(null), '#77818B');
  assert.equal(recoveryColor('normal'), '#FFDE00');
  assert.equal(recoveryColor('above_normal'), '#16EC06');
});
