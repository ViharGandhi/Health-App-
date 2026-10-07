import assert from 'node:assert/strict';
import test from 'node:test';
import { healthBounds, healthChange, healthMetrics, healthMonths, healthSegments, monitorReading } from './health.ts';

test('Monitor temperature uses measured Celsius until a baseline supports a Fahrenheit difference', () => {
  const metric = healthMetrics.find(metric => metric.key === 'skin_temperature');
  assert.equal(monitorReading(metric, { value: 33, baseline: 33.5 }).formatted, '-0.9');
  assert.equal(monitorReading(metric, { value: 34, baseline: 33 }).formatted, '+1.8');
  assert.equal(monitorReading(metric, { value: 33.01, baseline: 33 }).formatted, '0.0');
  assert.equal(monitorReading(metric, { value: 33, baseline: 33.5 }).unit, '°F');
  assert.equal(monitorReading(metric, { value: 33, baseline: null }).formatted, '33.0');
  assert.equal(monitorReading(metric, { value: 33, baseline: null }).unit, '°C');
  assert.equal(monitorReading(metric, { value: 33, baseline: null }).comparison, 'Building baseline');
  assert.equal(monitorReading(metric, { value: null, baseline: 33 }).formatted, '—');
  assert.equal(monitorReading(metric, { value: 0, baseline: null }).formatted, '0.0');
});
test('Monitor badges describe medians without assigning normality or treating missing readings as zero', () => {
  assert.equal(monitorReading(healthMetrics[0], { value: 40, baseline: 45 }).comparison, '−5 ms vs. median');
  assert.equal(monitorReading(healthMetrics[0]).formatted, '—');
  assert.equal(monitorReading(healthMetrics[0]).comparison, 'No reading');
  assert.equal(monitorReading(healthMetrics[0], { value: 0, baseline: 45 }).formatted, '0');
});

test('missing readings split a trend; zero is preserved', () => {
  assert.deepEqual(healthSegments([44, null, 0, 46].map(value => ({ value }))),
    [[{ index: 0, value: 44 }], [{ index: 2, value: 0 }, { index: 3, value: 46 }]]);
});
test('monthly averages use recorded days only, including partial months', () => {
  const points = [
    { date: '2026-09-29', value: 40 }, { date: '2026-09-30', value: null },
    { date: '2026-10-01', value: 0 }, { date: '2026-10-02', value: 50 },
    { date: '2026-11-01', value: null },
  ];
  assert.deepEqual(healthMonths(points).map(({ value, count, days }) => ({ value, count, days })),
    [{ value: 40, count: 1, days: 2 }, { value: 25, count: 2, days: 2 }, { value: null, count: 0, days: 1 }]);
});
test('comparisons retain native units and do not invent missing history', () => {
  const oxygen = healthMetrics.find(metric => metric.key === 'spo2');
  const temperature = healthMetrics.find(metric => metric.key === 'skin_temperature');
  assert.equal(healthChange(97.2, 97.0, oxygen), '+0.2 percentage points');
  assert.equal(healthChange(32.5, 33, temperature), '−0.5 °C');
  assert.equal(healthChange(40, null, healthMetrics[0]), null);
  assert.equal(healthChange(0, 0, healthMetrics[0]), '0 ms');
  assert.equal(healthChange(40.1, 40, healthMetrics[0]), '0 ms');
});
test('constant vital traces have visible height and SpO2 axes stop at 100%', () => {
  const [low, high] = healthBounds([40, 40], 'hrv');
  assert.ok(low < 40 && high > 40);
  const oxygen = healthBounds([99.9, 100], 'spo2');
  assert.ok(oxygen[0] < 99.9);
  assert.equal(oxygen[1], 100);
});
