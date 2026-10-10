import test from 'node:test';
import assert from 'node:assert/strict';
import { activityKind, activityHref, clockDuration, dashboardValue } from './activity.ts';

test('activity names and types select the matching symbol', () => {
  assert.equal(activityKind('Walk', 'WALKING'), 'walking');
  assert.equal(activityKind('Tempo Run', 'RUNNING'), 'running');
  assert.equal(activityKind('Weightlifting'), 'strength');
  assert.equal(activityKind('Bike', 'CYCLING'), 'cycling');
  assert.equal(activityKind('Other'), 'activity');
});
test('duration carries correctly and preserves unknowns and zeros', () => {
  assert.equal(clockDuration(59.99, true), '0:59:59');
  assert.equal(clockDuration(59.999, true), '1:00:00');
  assert.equal(clockDuration(null), '—');
  assert.equal(clockDuration(0, true), '0:00:00');
  assert.equal(dashboardValue(5038, 'steps'), '5,038');
  assert.equal(dashboardValue(5, 'strain'), '5.0');
});
test('activity links retain date and demo without changing the live tab', () => {
  assert.equal(activityHref('abc', '2026-10-09', true), '/activity?id=abc&date=2026-10-09&demo=true');
  assert.equal(activityHref('abc', '2026-10-09', false), '/activity?id=abc&date=2026-10-09');
});
