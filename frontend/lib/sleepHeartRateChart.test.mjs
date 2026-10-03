import assert from 'node:assert/strict';
import test from 'node:test';
import { chartPosition, heartRatePaths, nearestReading, stageWindows } from './sleepHeartRateChart.ts';

test('stage highlights use actual UTC intervals, clip to the sleep, and preserve separate bouts', () => {
  const start = Date.parse('2026-10-25T00:00:00Z'), end = Date.parse('2026-10-25T03:00:00Z');
  const windows = stageWindows([
    { start: '2026-10-25T01:30:00+02:00', end: '2026-10-25T02:30:00+02:00' },
    { start: '2026-10-25T02:30:00+01:00', end: '2026-10-25T03:00:00+01:00' },
    { start: '2026-10-25T05:00:00Z', end: '2026-10-25T06:00:00Z' },
  ], start, end);
  assert.deepEqual(windows, [{ x: 28, width: 43 }, { x: 157, width: 43 }]);
  assert.deepEqual(stageWindows([], start, end), []);
});

test('hover chooses the actual nearest reading and leaves missing intervals blank', () => {
  const samples = [{ time: 0, bpm: 51 }, { time: 60_000, bpm: 63 }, { time: 900_000, bpm: 58 }];
  assert.equal(nearestReading(samples, 44_000), 1);
  assert.equal(nearestReading(samples, 480_000), null);
  assert.equal(nearestReading(samples, 900_000), 2);
  assert.equal(nearestReading(samples, 1_300_000), null);
  assert.equal(nearestReading([], 0), null);
  assert.equal(heartRatePaths(samples, 0, 1_000_000, 30, 110).length, 2);
  assert.match(heartRatePaths([samples[0]], 0, 1_000_000, 30, 110)[0], /M.+ L/); // Isolated sample is drawn as a round dot.
});

test('physical time positions repeated local DST times independently', () => {
  const start = Date.parse('2026-10-25T00:00:00Z'), end = Date.parse('2026-10-25T03:00:00Z');
  const first = chartPosition({ time: Date.parse('2026-10-25T02:30:00+02:00'), bpm: 50 }, start, end, 30, 110);
  const second = chartPosition({ time: Date.parse('2026-10-25T02:30:00+01:00'), bpm: 50 }, start, end, 30, 110);
  assert.ok(second.x > first.x);
  assert.equal(second.y, first.y);
});

test('dense one-second streams retain extrema while limiting SVG path size', () => {
  const samples = Array.from({ length: 30_000 }, (_, i) => ({ time: i * 1000, bpm: i === 15_003 ? 100 : 60 }));
  const [path] = heartRatePaths(samples, 0, 30_000_000, 30, 110);
  assert.ok(path.includes(',12.50')); // Observed 100 BPM peak survived decimation.
  assert.ok(path.split(' ').length < 1100);
  assert.equal(nearestReading(samples, 15_003_000), 15_003); // Tooltip still uses the full stream.
});
