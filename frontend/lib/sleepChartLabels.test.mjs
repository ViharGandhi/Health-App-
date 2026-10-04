import assert from 'node:assert/strict';
import test from 'node:test';
import { lineLabelPositions, timingLabelPositions } from './sleepChartLabels.ts';

test('needed labels move below asleep after the lines cross', () => {
  const asleep = [{ x: 60, y: 160 }, { x: 104, y: 60 }];
  const needed = [{ x: 60, y: 100 }, { x: 104, y: 98 }];
  const labels = lineLabelPositions(asleep, needed);
  assert.ok(labels[0].second < needed[0].y);
  assert.ok(labels[0].first > asleep[0].y);
  assert.ok(labels[1].second > needed[1].y);
  assert.ok(labels[1].first < asleep[1].y);
});

test('near-equal readings and steep nearby segments stay outside both labels', () => {
  const first = [{ x: 60, y: 32 }, { x: 104, y: 150 }];
  const second = [{ x: 60, y: 145 }, { x: 104, y: 150 }];
  const labels = lineLabelPositions(first, second);
  const segmentAtLeftEdge = 32 + (150 - 32) * (104 - 18 - 60) / 44;
  assert.ok(labels[1].second + 3 < segmentAtLeftEdge);
  assert.ok(labels[1].first - 10 > 150);
});

test('gaps are never bridged when checking neighboring line geometry', () => {
  assert.deepEqual(lineLabelPositions([{ x: 60, y: 180 }, null, { x: 80, y: 32 }], [null, null, null], 5),
    [{ first: 172, second: null }, { first: null, second: null }, { first: 24, second: null }]);
});

test('time labels clear adjacent bars in dense monthly charts', () => {
  const labels = timingLabelPositions([{ x: 60, bed: 80, wake: 160, width: 5 }, { x: 70, bed: 32, wake: 196, width: 5 }]);
  assert.deepEqual(labels[0], { bed: 25, wake: 211 });
  assert.ok(labels[0].bed < 32);
  assert.ok(labels[0].wake - 11 > 196);
});

test('isolated timing labels retain their local positions and missing nights stay blank', () => {
  assert.deepEqual(timingLabelPositions([{ x: 60, bed: 40, wake: 180, width: 15 }, null, { x: 150, bed: 60, wake: 160, width: 15 }]),
    [{ bed: 33, wake: 195 }, null, { bed: 53, wake: 175 }]);
});

test('an edge label shifted away from the axis clears plots at its new position', () => {
  const labels = timingLabelPositions([{ x: 40, labelX: 56, bed: 80, wake: 160, width: 5 }, { x: 73, bed: 32, wake: 196, width: 5 }]);
  assert.deepEqual(labels[0], { bed: 25, wake: 211 });
});
