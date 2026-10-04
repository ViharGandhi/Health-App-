type Point = { x: number; y: number };
type TimingPoint = { x: number; bed: number; wake: number; width: number; labelX?: number };

// Include the nearby portions of both lines, not just their values at this day.
// This keeps a steep neighboring segment out of a value label's horizontal span.
export function lineLabelPositions(first: (Point | null)[], second: (Point | null)[], radius = 18) {
  return first.map((point, index) => {
    const other = second[index];
    if (!point && !other) return { first: null, second: null };
    const center = (point ?? other)!.x;
    const heights: number[] = [];
    for (const series of [first, second]) {
      series.forEach((current, i) => {
        if (!current) return;
        if (Math.abs(current.x - center) <= radius) heights.push(current.y);
        const previous = series[i - 1];
        if (!previous || previous.x === current.x) return;
        const left = Math.max(previous.x, center - radius);
        const right = Math.min(current.x, center + radius);
        if (left > right) return;
        for (const x of [left, right]) heights.push(previous.y + (current.y - previous.y) * (x - previous.x) / (current.x - previous.x));
      });
    }
    const above = Math.min(...heights) - 8;
    const below = Math.max(...heights) + 18;
    const firstAbove = !other || (point != null && point.y < other.y);
    return { first: point ? firstAbove ? above : below : null,
             second: other ? firstAbove ? below : above : null };
  });
}

export function timingLabelPositions(points: (TimingPoint | null)[], radius = 18) {
  return points.map(point => {
    if (!point) return null;
    const center = point.labelX ?? point.x;
    const neighbors = points.filter((other): other is TimingPoint => other != null && Math.abs(other.x - center) <= radius + other.width / 2);
    return { bed: Math.min(...neighbors.map(other => other.bed)) - 7,
             wake: Math.max(...neighbors.map(other => other.wake)) + 15 };
  });
}
