import test from 'node:test';
import assert from 'node:assert/strict';
import { strainFormat, strainValue, strainSummary, strainMonths, strainBreakdown, weekBuckets } from './strain.ts';

const days = (length, value = 10) => Array.from({ length }, (_, i) => ({
  date: `2026-09-${String(i + 1).padStart(2, '0')}`, score: value, strength_minutes: value, steps: value,
  zones: { zone1: value, zone2: 0, zone3: 0, zone4: 0, zone5: 0 }, strength_activities: { Weights: value }, activities: [],
}));

test('duration formatting rounds total minutes before carrying hours', () => {
  assert.equal(strainFormat(59.9, 'strength'), '1:00');
  assert.equal(strainFormat(0, 'strength'), '0:00');
  assert.equal(strainFormat(null, 'steps'), '—');
  assert.equal(strainFormat(10047, 'steps'), '10,047');
});
test('missing heart rate stays missing while zero steps remain real', () => {
  const day = { ...days(1)[0], score: null, zones: null, steps: 0 };
  assert.equal(strainValue(day, 'strain'), null);
  assert.equal(strainValue(day, 'zones_1_3'), null);
  assert.equal(strainValue(day, 'steps'), 0);
});
test('weekly durations sum days; month durations average weekly totals', () => {
  assert.equal(strainSummary(days(7), 'strength', 'W', ''), 70);
  const period = days(28); period[7].strength_minutes = 80;
  assert.equal(strainSummary(period, 'strength', 'M', ''), 87.5);
  assert.equal(weekBuckets(period, 'strength').length, 4);
});
test('incomplete zone weeks do not fabricate a full weekly total', () => {
  const period = days(14); period[0].zones = null;
  assert.equal(strainSummary(period.slice(0, 7), 'zones_1_3', 'W', ''), null);
  assert.equal(strainSummary(period, 'zones_1_3', 'M', ''), 70);
});
test('six-month average excludes partial weeks and includes true zero weeks', () => {
  const period = days(16); period.slice(0, 7).forEach(day => { day.strength_minutes = 0; });
  period[14].strength_minutes = 900;
  assert.equal(strainSummary(period, 'strength', '6M', ''), 35);
  assert.equal(strainMonths(period, 'strength')[0].value, 35);
});
test('only actual today is excluded from Strain averages, including historical navigation', () => {
  const period = days(7); period[6].score = 1;
  assert.equal(strainSummary(period, 'strain', 'W', '2026-09-07'), 10);
  assert.equal(strainSummary(period, 'strain', 'W', '2026-10-06'), 61 / 7);
  assert.equal(strainSummary(period, 'steps', 'W', '2026-09-07'), 10);
});
test('strain breakdown boundaries include every recorded day and skip missing scores', () => {
  const period = [null, 0, 10, 10.1, 14, 14.1, 18, 18.1].map(score => ({ score }));
  assert.deepEqual(strainBreakdown(period), [2, 2, 2, 1]);
});
