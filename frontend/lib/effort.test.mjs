import test from 'node:test';
import assert from 'node:assert/strict';
import { effortBand, estimateEffort } from './effort.ts';

test('effort numbers fall into the Apple-style bands', () => {
  assert.deepEqual([1, 3, 4, 6, 7, 8, 9, 10].map(n => effortBand(n).label),
    ['Easy', 'Easy', 'Moderate', 'Moderate', 'Hard', 'Hard', 'All Out', 'All Out']);
});

test('Strain bands map onto the matching effort bands', () => {
  assert.equal(estimateEffort(null), null);
  assert.equal(estimateEffort(Number.NaN), null);
  assert.deepEqual([0, 3.4, 6.7, 9.99].map(estimateEffort), [1, 2, 3, 3]);
  assert.deepEqual([10, 11.4, 12.7, 13.99].map(estimateEffort), [4, 5, 6, 6]);
  assert.deepEqual([14, 16, 17.99].map(estimateEffort), [7, 8, 8]);
  assert.deepEqual([18, 19.5, 21, 25].map(estimateEffort), [9, 10, 10, 10]);
  for (let strain = 0; strain <= 21; strain += .25) {
    assert.equal(effortBand(estimateEffort(strain)).label,
      strain < 10 ? 'Easy' : strain < 14 ? 'Moderate' : strain < 18 ? 'Hard' : 'All Out');
  }
});
