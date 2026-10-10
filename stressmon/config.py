from pathlib import Path
from datetime import timedelta, timezone
import re
import yaml


DEFAULT_CONFIG = Path(__file__).with_name('config.yaml')


def load_config(path=DEFAULT_CONFIG):
    with Path(path).open(encoding='utf-8') as stream:
        cfg = yaml.safe_load(stream)
    choices = [(cfg['time']['hrv_window_anchor'], ('start', 'end', 'unverified')),
               (cfg['baselines']['mode'], ('auto', 'causal', 'retrospective')),
               (cfg['smoothing']['mode'], ('retrospective', 'live')),
               (cfg['smoothing']['method'], ('savgol', 'gaussian'))]
    if any(value not in allowed for value, allowed in choices):
        raise ValueError('config.yaml contains an invalid time, baseline or smoothing mode')
    if cfg['hr']['window_minutes'] != 5:
        raise ValueError('This export/model requires five-minute scoring windows')
    if cfg['hr']['hampel_samples'] < 3 or cfg['hr']['hampel_samples'] % 2 != 1:
        raise ValueError('hampel_samples must be odd and at least 3')
    if not 0 < cfg['smoothing']['ema_alpha'] <= 1:
        raise ValueError('ema_alpha must be in (0, 1]')
    if cfg['score']['w_hr_s'] + cfg['score']['w_hrv'] <= 0:
        raise ValueError('At least one sleep score weight must be positive')
    if cfg['physiology']['age'] is not None and not 0 < cfg['physiology']['age'] <= 120:
        raise ValueError('age must be a positive age in years or null')
    return cfg


def fixed_timezone(offset):
    if not isinstance(offset, str) or not re.fullmatch(r'[+-]\d{2}:\d{2}', offset):
        raise ValueError('UTC offset must be written as +HH:MM or -HH:MM')
    hour, minute = map(int, offset[1:].split(':'))
    if hour > 14 or minute > 59 or hour == 14 and minute:
        raise ValueError('UTC offset outside the supported ±14 hour range')
    sign = 1 if offset[0] == '+' else -1
    return timezone(sign * timedelta(hours=hour, minutes=minute))
