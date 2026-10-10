import test from 'node:test';
import assert from 'node:assert/strict';
import { watchDayChange } from './dayRollover.ts';

function browser(t, hidden = false) {
  globalThis.window = new EventTarget();
  globalThis.document = Object.assign(new EventTarget(), { hidden });
  t.after(() => { delete globalThis.window; delete globalThis.document; });
}

test('an open page refreshes at local midnight and cleans up its timer', t => {
  t.mock.timers.enable({ apis: ['Date', 'setTimeout'], now: new Date(2026, 9, 9, 23, 59, 59).getTime() });
  browser(t);
  let changes = 0;
  const stop = watchDayChange(() => changes++);
  t.mock.timers.tick(999);
  assert.equal(changes, 0);
  t.mock.timers.tick(1);
  assert.equal(changes, 1);
  window.dispatchEvent(new Event('focus'));
  assert.equal(changes, 1);
  stop();
  t.mock.timers.tick(24 * 3600000);
  assert.equal(changes, 1);
});

test('a tab sleeping across midnight refreshes on return before its timer runs', t => {
  t.mock.timers.enable({ apis: ['Date', 'setTimeout'], now: new Date(2026, 9, 9, 23, 55).getTime() });
  browser(t, true);
  let changes = 0;
  const stop = watchDayChange(() => changes++);
  t.mock.timers.setTime(new Date(2026, 9, 10, 8).getTime());
  document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(changes, 0);
  document.hidden = false;
  document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(changes, 1);
  stop();
});
