/** Home visits and the automatic 15-minute timer use separate server rules. */
export class DynamicSyncSchedule {
  started = false;
  pending = false;
  lastSuccess: number | null = null;
  reloadHandled = false;
  private sync: (force: boolean, homeVisit: boolean) => Promise<boolean>;
  private now: () => number;
  private runningForce = false;
  private homeQueued = false;
  constructor(sync: (force: boolean, homeVisit: boolean) => Promise<boolean>, now = Date.now) {
    this.sync = sync;
    this.now = now;
  }
  async check(visible = true) {
    if (!visible || this.pending) return;
    if (this.lastSuccess != null && this.now() - this.lastSuccess < 900000) return;
    await this.run(false);
  }
  async visit(visible = true) {
    if (!visible) return;
    if (this.pending) {
      if (!this.runningForce) this.homeQueued = true;
      return;
    }
    // The durable backend visit timestamp decides whether a force is eligible.
    await this.run(true);
  }
  async reload(visible = true) {
    if (!visible || this.pending || this.reloadHandled) return;
    this.reloadHandled = true;
    try { await this.run(true, false); }
    catch (error) { this.reloadHandled = false; throw error; }
  }
  private async run(force: boolean, homeVisit = force) {
    this.pending = true;
    this.runningForce = force;
    try {
      if (await this.sync(force, homeVisit)) {
        this.started = true;
        this.lastSuccess = this.now();
      }
    } finally {
      this.pending = false;
      if (this.homeQueued) {
        this.homeQueued = false;
        await this.visit();
      }
    }
  }
}
