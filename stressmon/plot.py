"""Offline plot; vector activity symbols need no emoji font or map service."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.offsetbox import AnnotationBbox, DrawingArea
from matplotlib.lines import Line2D
from matplotlib.patches import Circle


def _athlete(running, size, color):
    drawing = DrawingArea(size, size)
    drawing.add_artist(Circle((size * .53, size * .87), size * .07, color=color))
    points = ([[.5, .75], [.4, .49], [.64, .32], [.8, .08]],
              [[.4, .49], [.28, .27], [.05, .27]],
              [[.48, .69], [.68, .61], [.78, .72]],
              [[.48, .69], [.26, .63], [.15, .48]]) if running else (
              [[.52, .75], [.48, .43], [.65, .05]],
              [[.48, .43], [.28, .05]],
              [[.5, .67], [.28, .44]], [[.5, .67], [.69, .45]])
    for segment in points:
        p = np.asarray(segment) * size
        drawing.add_artist(Line2D(p[:, 0], p[:, 1], color=color, linewidth=2))
    return drawing


def plot_day(frame, data, date, cfg, path):
    p = cfg['plot']
    day = frame[frame['date'].eq(date)]
    if day.empty:
        raise ValueError(f'No HR observations on display date {date}')
    start = pd.Timestamp(date).tz_localize(data.timezone).tz_convert('UTC')
    end = start + pd.Timedelta(days=1)
    def hour(stamp):
        return (stamp - start).total_seconds() / 3600
    with plt.rc_context({'font.family': p['font_family'], 'font.size': p['font_size'],
                         'text.color': p['foreground'], 'axes.labelcolor': p['foreground'],
                         'xtick.color': p['foreground'], 'ytick.color': p['foreground']}):
        fig, ax = plt.subplots(figsize=(p['width_pixels'] / p['dpi'], p['height_pixels'] / p['dpi']), dpi=p['dpi'])
        fig.patch.set_facecolor(p['background'])
        ax.set_facecolor(p['background'])
        spans = []
        for s in data.sleeps.sort_values('start').itertuples():
            if s.end > start and s.start < end:
                left, right = max(0, hour(s.start)), min(24, hour(s.end))
                if spans and left <= spans[-1][1]:
                    spans[-1][1] = max(right, spans[-1][1])
                else:
                    spans.append([left, right])
        for left, right in spans:
            ax.axvspan(left, right, color=p['sleep_color'], alpha=p['sleep_alpha'])
        missing = day['score'].isna().to_numpy()
        cuts = np.r_[0, np.flatnonzero(missing[1:] != missing[:-1]) + 1, len(day)]
        for lo, hi in zip(cuts[:-1], cuts[1:]):
            if missing[lo]:
                ax.axvspan(hour(day.index[lo]), hour(day['end'].iloc[hi - 1]),
                           color=p['gap_color'], alpha=p['gap_alpha'], hatch=p['gap_hatch'])
        x = np.array([hour(t) for t in day.index + pd.Timedelta(minutes=cfg['hr']['window_minutes'] / 2)])
        y = day['score'].to_numpy()
        # Break both missing windows and sleep/wake transitions.
        same = day['state'].eq('SLEEP').to_numpy()
        good = np.isfinite(y[:-1]) & np.isfinite(y[1:]) & (same[:-1] == same[1:])
        points = np.c_[x, y]
        segments = np.stack([points[:-1], points[1:]], axis=1)[good]
        means = ((y[:-1] + y[1:]) / 2)[good]
        colors = np.where(means < cfg['score']['medium_threshold'], p['low_color'],
                          np.where(means < cfg['score']['high_threshold'], p['medium_color'], p['high_color']))
        ax.add_collection(LineCollection(segments, colors=colors, linewidths=p['line_width']))
        ax.scatter(x[np.isfinite(y)], y[np.isfinite(y)], s=p['line_width'], color=[
            p['low_color'] if v < cfg['score']['medium_threshold'] else p['medium_color'] if v < cfg['score']['high_threshold'] else p['high_color']
            for v in y[np.isfinite(y)]])
        for e in data.exercises.itertuples():
            if start <= e.start < end:
                name = str(e.activity_name).lower()
                label = 'Run' if 'run' in name else 'Walk' if 'walk' in name else 'Activity'
                if label in ('Run', 'Walk'):
                    symbol = _athlete(label == 'Run', p['icon_size'], p['foreground'])
                    ax.add_artist(AnnotationBbox(symbol, (hour(e.start), p['icon_position']), frameon=False))
                else:
                    ax.plot(hour(e.start), p['icon_position'], marker='D', color=p['foreground'])
                ax.annotate(label, (hour(e.start), p['icon_position']), xytext=(0, -p['icon_size']),
                            textcoords='offset points', ha='center', fontsize=p['font_size'] * .75)
        cutoff = data.hr['timestamp'].max()
        if start <= cutoff < end - pd.Timedelta(minutes=p['incomplete_tolerance_minutes']):
            ax.axvline(hour(cutoff), color=p['foreground'], linestyle='--', alpha=.6)
            ax.annotate('Data through ' + cutoff.tz_convert(data.timezone).strftime('%H:%M'),
                        (hour(cutoff), 0), xytext=(-5, -35), textcoords='offset points', ha='right')
        ax.set(xlim=(0, 24), ylim=(0, cfg['score']['max_score']), ylabel='Estimated stress')
        ticks = np.arange(0, 25, p['x_tick_hours'])
        ax.set_xticks(ticks, [f'{int(t):02d}:00' for t in ticks])
        ax.set_yticks(np.arange(0, cfg['score']['max_score'] + p['y_tick_step'], p['y_tick_step']))
        ax.grid(color=p['grid'], alpha=p['grid_alpha'])
        for spine in ax.spines.values():
            spine.set_visible(False)
        fig.suptitle(f'{p["title"]}  ·  {date}', x=.08, ha='left', fontweight='bold')
        mode = day['baseline_mode'].iloc[0]
        confidence = 'Low confidence' if day['low_confidence'].any() else 'Unvalidated'
        fig.text(.08, .91, f'{confidence} · {mode} baseline · {int(day["baseline_days"].iloc[0])} reference days')
        fig.text(.08, .025, 'Independent wellness estimate · Awake: HR + previous-night context · Hatched: unavailable / masked')
        fig.subplots_adjust(left=.08, right=.96, bottom=.13, top=p['margin_top'])
        fig.savefig(path, dpi=p['dpi'], facecolor=fig.get_facecolor())
        plt.close(fig)
    return path
