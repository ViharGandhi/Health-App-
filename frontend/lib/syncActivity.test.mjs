import test from 'node:test';
import assert from 'node:assert/strict';
import { getSyncActivity, subscribeSyncActivity, trackSyncActivity } from './syncActivity.ts';

test('animation stays active until overlapping syncs finish, including failure', async () => {
  const states = [];
  const unsubscribe = subscribeSyncActivity(() => states.push(getSyncActivity()));
  let finish;
  let fail;
  const first = trackSyncActivity(() => new Promise(resolve => { finish = resolve; }));
  const second = trackSyncActivity(() => new Promise((resolve, reject) => { fail = reject; }));
  assert.equal(getSyncActivity(), true);
  finish();
  await first;
  assert.equal(getSyncActivity(), true);
  const rejected = assert.rejects(second, /offline/);
  fail(new Error('offline'));
  await rejected;
  assert.equal(getSyncActivity(), false);
  unsubscribe();
  assert.deepEqual(states, [true, true, true, false]);
});
