/** Short-lived browser memory only; never persist health responses in localStorage. */
export class RequestCache {
  private values = new Map<string, { expires: number; value: unknown }>();
  private pending = new Map<string, Promise<unknown>>();
  private generation = 0;

  clear() {
    this.generation++;
    this.values.clear();
    this.pending.clear();
  }

  async get<T>(key: string, fetcher: () => Promise<T>, ttl = 120000): Promise<T> {
    const cached = this.values.get(key);
    if (cached && cached.expires > Date.now()) return cached.value as T;
    const existing = this.pending.get(key);
    if (existing) return existing as Promise<T>;
    const generation = this.generation;
    const request = fetcher().then(value => {
      if (generation === this.generation) {
        this.values.delete(key);
        this.values.set(key, { expires: Date.now() + ttl, value });
        if (this.values.size > 64) this.values.delete(this.values.keys().next().value!);
      }
      return value;
    }).finally(() => {
      if (this.pending.get(key) === request) this.pending.delete(key);
    });
    this.pending.set(key, request);
    return request;
  }
}
