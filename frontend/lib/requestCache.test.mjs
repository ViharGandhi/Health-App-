import test from 'node:test';
import assert from 'node:assert/strict';
import { RequestCache } from './requestCache.ts';

test('duplicate reads share one request and different settings stay separate', async () => {
  const cache = new RequestCache();
  let calls = 0;
  const fetcher = async () => ++calls;
  assert.deepEqual(await Promise.all([cache.get('age22', fetcher), cache.get('age22', fetcher)]), [1, 1]);
  assert.equal(await cache.get('age23', fetcher), 2);
  assert.equal(await cache.get('age22', fetcher), 1);
});

test('failed and expired reads can retry', async () => {
  const cache = new RequestCache();
  await assert.rejects(cache.get('a', async () => { throw Error('offline'); }));
  assert.equal(await cache.get('a', async () => 1, -1), 1);
  assert.equal(await cache.get('a', async () => 2), 2);
});

test('disconnect or refresh cannot be undone by a late previous request', async () => {
  const cache = new RequestCache();
  let finish;
  const old = cache.get('same', () => new Promise(resolve => { finish = resolve; }));
  cache.clear();
  assert.equal(await cache.get('same', async () => 'new account'), 'new account');
  finish('old account');
  await old;
  assert.equal(await cache.get('same', async () => 'unexpected'), 'new account');
});
