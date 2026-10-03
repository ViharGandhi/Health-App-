// Five minutes is a display gap limit, not a claim about device sampling cadence.
export const MAX_GAP_MS = 5 * 60 * 1000;
export const LEFT = 28;
export const RIGHT = 286;

export interface ChartReading { time: number; bpm: number }

export function stageWindows(intervals: { start: string; end: string }[], start: number, end: number) {
  return intervals.flatMap(interval => {
    const left = Math.max(start, Date.parse(interval.start)), right = Math.min(end, Date.parse(interval.end));
    if (!Number.isFinite(left) || !Number.isFinite(right) || right <= left || end <= start) return [];
    return [{ x: LEFT + (left - start) / (end - start) * (RIGHT - LEFT),
              width: (right - left) / (end - start) * (RIGHT - LEFT) }];
  });
}

export function nearestReading(samples: ChartReading[], time: number): number | null {
  if (!samples.length) return null;
  let lo = 0, hi = samples.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (samples[mid].time < time) lo = mid + 1;
    else hi = mid;
  }
  const index = lo === 0 ? 0 : lo === samples.length ? lo - 1
    : time - samples[lo - 1].time <= samples[lo].time - time ? lo - 1 : lo;
  // Never snap across a missing-data interval or an unobserved session edge.
  if ((lo > 0 && lo < samples.length && time > samples[lo - 1].time && time < samples[lo].time
       && samples[lo].time - samples[lo - 1].time > MAX_GAP_MS)
      || Math.abs(samples[index].time - time) > MAX_GAP_MS) return null;
  return index;
}

export function chartPosition(sample: ChartReading, start: number, end: number, min: number, max: number) {
  return { x: LEFT + (sample.time - start) / (end - start) * (RIGHT - LEFT),
           y: (max - sample.bpm) / (max - min) * 100 };
}

export function heartRatePaths(samples: ChartReading[], start: number, end: number, min: number, max: number): string[] {
  const segments: ChartReading[][] = [];
  for (const sample of samples) {
    const last = segments[segments.length - 1];
    if (!last || sample.time - last[last.length - 1].time > MAX_GAP_MS) segments.push([sample]);
    else last.push(sample);
  }
  return segments.map(segment => {
    // Preserve first/last and extremes per horizontal SVG column. Hover still uses all raw readings.
    const columns = new Map<number, number[]>();
    segment.forEach((sample, i) => {
      const column = Math.floor(chartPosition(sample, start, end, min, max).x);
      const group = columns.get(column);
      if (!group) columns.set(column, [i, i, i, i]);
      else {
        group[1] = i;
        if (sample.bpm < segment[group[2]].bpm) group[2] = i;
        if (sample.bpm > segment[group[3]].bpm) group[3] = i;
      }
    });
    const path = [...new Set([...columns.values()].flat())].sort((a, b) => a - b).map((index, i) => {
      const { x, y } = chartPosition(segment[index], start, end, min, max);
      return `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ');
    return segment.length === 1 ? `${path} ${path.replace('M', 'L')}` : path;
  });
}
