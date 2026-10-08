import test from 'node:test';
import assert from 'node:assert/strict';
import { DynamicSyncSchedule } from './dynamicSyncSchedule.ts';

test('one Home visit, then automatic checks after 15 minutes; navigation is silent', async () => {
  let now = 0;
  const calls = [];
  const schedule = new DynamicSyncSchedule(async force => { calls.push(force); return true; }, () => now);
  await schedule.visit();
  now = 120000;
  await schedule.check();
  assert.deepEqual(calls, [true]);
  now = 900000;
  await schedule.check(false);
  assert.deepEqual(calls, [true]);
  await schedule.check(true);
  assert.deepEqual(calls, [true, false]);
  await schedule.check();
  assert.deepEqual(calls, [true, false]);
});

test('pending checks share work; failure leaves first visit eligible for retry', async () => {
  let release, count = 0;
  const schedule = new DynamicSyncSchedule(async () => {
    count++;
    await new Promise(resolve => { release = resolve; });
    return false;
  });
  const first = schedule.visit();
  await schedule.check();
  assert.equal(count, 1);
  release(); await first;
  assert.equal(schedule.started, false);
  const retry = schedule.visit();
  assert.equal(count, 2);
  release(); await retry;
});

test('skipped Home visits do not postpone automatic syncing', async () => {
  let now = 0;
  const calls = [];
  const schedule = new DynamicSyncSchedule(async force => {
    calls.push(force);
    return calls.length === 1 || !force;
  }, () => now);
  await schedule.visit();
  now = 600000;
  await schedule.visit(); // Backend declines a visit within the qualifying window.
  assert.equal(schedule.lastSuccess, 0);
  now = 900000;
  await schedule.check();
  assert.deepEqual(calls, [true, true, false]);
});

test('a Home return during automatic work is checked after that work finishes', async () => {
  let release;
  const calls = [];
  const schedule = new DynamicSyncSchedule(async force => {
    calls.push(force);
    if (!force) await new Promise(resolve => { release = resolve; });
    return true;
  });
  const automatic = schedule.check();
  await schedule.visit();
  await schedule.visit();
  release();
  await automatic;
  assert.deepEqual(calls, [false, true]);
});

test('reload forces once per document despite a recent sync, then resumes periodic syncing', async () => {
  let now = 1000;
  const calls = [];
  const schedule = new DynamicSyncSchedule(async (force, homeVisit) => {
    calls.push([force, homeVisit]); return true;
  }, () => now);
  schedule.lastSuccess = 500;
  await schedule.reload();
  await schedule.reload();
  assert.deepEqual(calls, [[true, false]]);
  now += 900000;
  await schedule.check();
  assert.deepEqual(calls, [[true, false], [false, false]]);
});
