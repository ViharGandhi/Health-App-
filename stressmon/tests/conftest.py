from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stressmon.config import load_config, fixed_timezone
from stressmon.io import COLUMNS


def synthetic_export(root, days=5):
    rng = np.random.default_rng(47)
    tz = fixed_timezone('+05:30')
    start = pd.Timestamp('2026-10-01', tz=tz)
    stamps = pd.date_range(start, periods=days * 24 * 60 * 30, freq='2s')
    minute = stamps.hour * 60 + stamps.minute
    sleeping = minute < 7 * 60
    running = (minute >= 10 * 60) & (minute < 10 * 60 + 35)
    walking = (minute >= 14 * 60) & (minute < 14 * 60 + 30)
    means = np.where(sleeping, 56, np.where(running, 170, np.where(walking, 105, 70)))
    noise = np.where(sleeping, 3, 5)
    hr = pd.DataFrame({'timestamp': stamps.tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ'),
                       'beats per minute': means + rng.normal(0, noise), 'data source': 'Google Fitbit Air'})
    def csv(relative, frame):
        path = Path(root) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
    csv('Physical Activity_GoogleData/Heart Rate/heart_rate_2026-10-01.csv', hr)
    stages, exercise, variability = [], [], []
    for d in range(days):
        day = start + pd.Timedelta(days=d)
        def z(value):
            return value.tz_convert('UTC').isoformat().replace('+00:00', 'Z')
        stages.append([f'night{d}', 'LIGHT', '+05:30', z(day), z(day + pd.Timedelta(hours=7))])
        for name, hour, duration, bpm in [('Outdoor Run', 10, 35, 170), ('Outdoor Walk', 14, 30, 105)]:
            exercise.append([z(day + pd.Timedelta(hours=hour)), z(day + pd.Timedelta(hours=hour, minutes=duration)),
                             '+05:30', name, bpm, bpm + 10, 3000])
        for t in pd.date_range(day + pd.Timedelta(minutes=5), day + pd.Timedelta(hours=7), freq='5min', inclusive='left'):
            variability.append([t.strftime('%Y-%m-%d %H:%M:%S'), 50 + rng.normal(0, 2), 1, 100, 100])
    csv('Health Fitness Data_GoogleData/UserSleepStages_synthetic.csv', pd.DataFrame(stages, columns=COLUMNS['sleep']))
    csv('Health Fitness Data_GoogleData/UserExercises_synthetic.csv', pd.DataFrame(exercise, columns=COLUMNS['exercises']))
    csv('Heart Rate Variability/Heart Rate Variability Details - 2026-10-01.csv', pd.DataFrame(variability, columns=COLUMNS['hrv']))
    minutes = pd.date_range(start, periods=days * 1440, freq='1min')
    m = minutes.hour * 60 + minutes.minute
    active = ((m >= 600) & (m < 635)) | ((m >= 840) & (m < 870))
    csv('Physical Activity_GoogleData/Activity Level/activity_level_2026-10-01.csv',
        pd.DataFrame({'timestamp': minutes.tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ'),
                      'level': np.where(active, 'ACTIVE', 'SEDENTARY')}))
    return Path(root)


@pytest.fixture(scope='session')
def takeout(tmp_path_factory):
    return synthetic_export(tmp_path_factory.mktemp('takeout'))


@pytest.fixture
def cfg():
    result = load_config()
    result['time']['hrv_window_anchor'] = 'end'
    return result
